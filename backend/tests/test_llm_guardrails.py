"""Guardrails for real (imperfect) LLMs, found by running the pipeline on a local 3B model.

A scripted fake engine reproduces the observed behaviour: empty quotes, over-tagging of
sensitive topics, and complaints mislabelled as contradictions.
"""

from app.ai.embeddings import HashEmbedder
from app.ai.engine import DemoEngine
from app.ai.schemas import ContradictionCheck, ExtractedPainPoint, ExtractionResult
from app.services.pipeline import InterviewRecord, best_excerpt, looks_like_complaint, run_pipeline


def rec(pid, pain, behavior="Uses spreadsheets every week.", quote=""):
    return InterviewRecord(
        id=pid, participant_id=pid, participant_role="PM", company_size="50-200", plan_tier="Pro",
        pain=pain, behavior=behavior, verbatim_quote=quote,
        raw_content=f"Participant ID: {pid}\nPain: {pain}\nBehavior: {behavior}\nVerbatim Quote: {quote}",
    )


def test_best_excerpt_finds_matching_note_sentence():
    iv = rec("P1", "Dashboards are slow to refresh on Monday mornings. Exports to PDF break the layout.")
    assert best_excerpt("Slow dashboard refresh on Monday mornings", iv) == "Dashboards are slow to refresh on Monday mornings."
    assert best_excerpt("Pricing is confusing", iv) == ""  # nothing close: no fake evidence


def test_complaint_detector():
    assert looks_like_complaint("Connecting our warehouse took three days because the connector kept timing out.")
    assert looks_like_complaint("I spent most of the trial fighting the connector.")
    assert looks_like_complaint("My CEO is never going to create an account just to look at one chart.")
    assert not looks_like_complaint("Connecting our Snowflake warehouse was easy and took ten minutes.")
    assert not looks_like_complaint("Setup was painless; it's the speed that hurts.")


class SloppyLLM(DemoEngine):
    """Behaves like a small local model: paraphrases, no quotes, over-tags, eager contradictions."""

    name, model = "sloppy", "3b"

    def extract(self, interview, objectives):
        result = super().extract(interview, objectives)
        return ExtractionResult(
            pain_points=[
                ExtractedPainPoint(
                    pain=p.pain,
                    quote="",  # no quote
                    source_field="pain",
                    severity=p.severity,
                    sensitive_tags=["churn", "pricing"],  # over-tagging
                )
                for p in result.pain_points
            ]
        )

    def check_contradiction(self, theme_name, theme_description, candidate):
        first = candidate.split("\n")[0].split(". ")[0].rstrip(".") + "."
        return ContradictionCheck(contradicts=True, explanation="(model says so)", quote=first)


class _MixedTopicsJudge(DemoEngine):
    """Rates a cluster as incoherent when it mixes 'slow' and 'price' pain points."""

    name, model = "judge", "test"

    def name_theme(self, pain_points):
        naming = super().name_theme(pain_points)
        mixed = any("slow" in p for p in pain_points) and any("price" in p.lower() for p in pain_points)
        return naming.model_copy(update={"coherence": 0.2 if mixed else 0.9})


class _LooseEmbedder(HashEmbedder):
    cluster_threshold = -1.0  # merge everything first, so only the AI coherence check can split


def test_incoherent_cluster_is_split():
    interviews = [
        rec("P1", "Dashboards are slow to load every Monday morning."),
        rec("P2", "Heavy dashboards are slow to load at month end."),
        rec("P3", "The price jumps a lot when we add seats."),
        rec("P4", "The price keeps going up at every renewal."),
    ]
    res = run_pipeline(interviews, [], _MixedTopicsJudge(), _LooseEmbedder())
    assert res.stats["clusters_split"] == 1
    groups = sorted(sorted(t.participant_ids) for t in res.themes)
    assert ["P1", "P2"] in groups and ["P3", "P4"] in groups


def test_valid_partition_never_loses_or_duplicates_clusters():
    from app.services.pipeline import valid_partition

    assert valid_partition([[0, 2], [2, 3], [9], [1, 1]], 5) == [[0, 2], [3], [1], [4]]
    assert valid_partition([], 3) == [[0], [1], [2]]


class _GroupingEngine(DemoEngine):
    """Merges clusters the way an LLM would, by topic words, and returns a sloppy answer."""

    name, model = "grouper", "test"

    def group_clusters(self, clusters):
        from app.ai.schemas import ClusterGrouping

        slow = [i for i, c in enumerate(clusters) if any("slow" in p for p in c)]
        return ClusterGrouping(groups=[slow, slow, [99]])  # duplicates and an unknown number


class _TightEmbedder(HashEmbedder):
    cluster_threshold = 0.99  # every pain point starts in its own cluster


def test_ai_consolidation_merges_clusters_and_python_counts():
    interviews = [
        rec("P1", "Dashboards are slow to load every Monday morning."),
        rec("P2", "Reports are slow when the month closes."),
        rec("P3", "The price keeps going up at every renewal."),
    ]
    res = run_pipeline(interviews, [], _GroupingEngine(), _TightEmbedder())
    assert res.stats["clusters_merged_by_ai"] == 1
    slow = next(t for t in res.themes if "P1" in t.participant_ids)
    assert slow.participant_ids == ["P1", "P2"] and slow.participant_count == 2
    assert abs(slow.frequency - 2 / 3) < 1e-3  # computed in Python (rounded to 4 decimals)
    assert any(t.participant_ids == ["P3"] for t in res.themes)  # left-out cluster kept


def test_pipeline_grounds_quotes_tags_and_contradictions():
    interviews = [
        rec("P1", "Dashboards are slow to refresh on Monday mornings when everyone opens them."),
        rec("P2", "Heavy dashboards are slow to load during month-end reporting."),
        rec("P3", "Dashboards with a million rows are slow to load and time out."),
        rec("P4", "We plan to cancel at renewal because the price keeps going up."),
        rec("P5", "Connecting our warehouse was easy and took ten minutes. Dashboards are slow to load."),
    ]
    res = run_pipeline(interviews, [], SloppyLLM(), HashEmbedder())

    # Quotes: recovered verbatim from the notes even though the model gave none.
    assert res.stats["quotes_from_notes"] >= 4
    assert all(p.quote_verified for p in res.pain_points)

    # Sensitive tags: only where the participant actually talked about it.
    tagged = {p.interview.participant_id: set(p.sensitive_tags) for p in res.pain_points}
    assert tagged["P4"] >= {"churn", "pricing"}
    assert all(not tags for pid, tags in tagged.items() if pid != "P4")

    # Contradictions: complaints are rejected; the genuinely positive statement is kept.
    contra = [e for t in res.themes for e in t.evidence if e.stance == "contradicting"]
    assert all(not looks_like_complaint(e.quote) for e in contra)
