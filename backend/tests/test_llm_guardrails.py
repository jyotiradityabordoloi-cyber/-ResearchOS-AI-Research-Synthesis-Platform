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
