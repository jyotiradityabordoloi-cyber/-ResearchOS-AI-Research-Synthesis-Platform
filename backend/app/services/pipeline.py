"""Module D — the synthesis pipeline (pure computation, no database access).

Stages
  1. extraction        AI: atomic pain points + exact quotes per interview
  2. embeddings        embedder: one vector per pain point
  3. similarity        Python: cosine matrix; near-duplicates per participant collapsed
  4. clustering        Python: average-linkage agglomerative; AI names each cluster
  5. evidence          Python: every quote must exist verbatim in its interview
  6. frequency         Python: unique participants / total participants
  7. insights          AI: statement, implication, severity, strategic relevance
  8. contradictions    AI: opposing evidence; Python: outliers, sensitivity, fallbacks

The AI never sees or returns participant IDs, and never does arithmetic.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from app.ai import lexicon
from app.ai.embeddings import Embedder
from app.ai.engine import AIEngine, InterviewText, split_sentences

DUPLICATE_SIMILARITY = 0.9
# Split a cluster when the AI rates it as mixing problems (coherence below this).
SPLIT_COHERENCE = 0.6
SPLIT_STEP = 0.03
MIN_SPLIT_SIZE = 2
LOW_CONFIDENCE = 0.55
CONTRADICTION_CANDIDATES = 3
MAX_PAIN_POINTS = 400

STAGES = [
    "extraction",
    "embeddings",
    "similarity",
    "clustering",
    "evidence",
    "frequency",
    "insights",
    "contradictions",
]


@dataclass
class InterviewRecord:
    id: object
    participant_id: str
    participant_role: str
    company_size: str
    plan_tier: str
    pain: str
    behavior: str
    verbatim_quote: str
    raw_content: str

    @property
    def key(self) -> str:
        return self.participant_id.strip().lower()

    def text(self) -> InterviewText:
        return InterviewText(
            pain=self.pain,
            behavior=self.behavior,
            verbatim_quote=self.verbatim_quote,
            participant_role=self.participant_role,
            company_size=self.company_size,
            plan_tier=self.plan_tier,
        )

    def full_text(self) -> str:
        return f"{self.pain}\n{self.behavior}\n{self.verbatim_quote}"


@dataclass
class PainPointDraft:
    interview: InterviewRecord
    text: str
    quote: str
    quote_verified: bool
    source_field: str | None
    severity: int
    sensitive_tags: list[str]
    embedding: list[float] | None = None
    duplicate_count: int = 0


@dataclass
class EvidenceDraft:
    interview: InterviewRecord
    quote: str
    quote_verified: bool
    source_field: str | None
    stance: str  # supporting | contradicting
    note: str = ""
    pain_point: PainPointDraft | None = None


@dataclass
class ThemeDraft:
    name: str
    description: str
    pain_points: list[PainPointDraft]
    participant_ids: list[str]
    participant_count: int
    total_participants: int
    frequency: float
    cohesion: float
    coherence: float
    confidence: float = 0.0
    severity: int = 3
    strategic_relevance: int = 3
    statement: str = ""
    implication: str = ""
    evidence: list[EvidenceDraft] = field(default_factory=list)
    evidence_status: str = "sufficient"
    is_outlier: bool = False
    is_low_confidence: bool = False
    has_contradictions: bool = False
    sensitive_tags: list[str] = field(default_factory=list)
    embedding: list[float] | None = None
    code: str = ""

    @property
    def requires_approval(self) -> bool:
        return bool(self.sensitive_tags)

    @property
    def priority_score(self) -> float:
        # Kept separate in the UI; this is only a default sort order PMs can override.
        return round(
            0.35 * self.frequency
            + 0.25 * (self.severity - 1) / 4
            + 0.25 * (self.strategic_relevance - 1) / 4
            + 0.15 * self.confidence,
            3,
        )


@dataclass
class PipelineResult:
    pain_points: list[PainPointDraft]
    themes: list[ThemeDraft]
    warnings: list[dict[str, str]]
    stats: dict[str, object]


# ---------------------------------------------------------------------------
# Evidence validation (stage 5) — used throughout
# ---------------------------------------------------------------------------

_QUOTE_MAP = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'", " ": " "})


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").translate(_QUOTE_MAP).lower()).strip()


def clean_quote(quote: str) -> str:
    q = (quote or "").translate(_QUOTE_MAP).strip()
    q = q.strip("\"' ").strip()
    return re.sub(r"^(?:\.\.\.|…)\s*|\s*(?:\.\.\.|…)$", "", q).strip()


def verify_quote(quote: str, interview: InterviewRecord) -> tuple[str, bool]:
    """Return (cleaned quote, verified). A quote is verified only if it appears verbatim."""
    q = clean_quote(quote)
    if len(q) < 3:
        return "", False
    haystack = _norm(
        "\n".join([interview.raw_content, interview.pain, interview.behavior, interview.verbatim_quote])
    )
    return q, _norm(q) in haystack


def locate_field(quote: str, interview: InterviewRecord) -> str | None:
    nq = _norm(quote)
    for name in ("verbatim_quote", "pain", "behavior"):
        if nq and nq in _norm(getattr(interview, name)):
            return name
    return None


_WORD = re.compile(r"[a-z0-9]{3,}")
_STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "they", "their", "our", "are", "was", "were", "have", "has",
    "but", "not", "can", "too", "from", "when", "into", "just", "about", "them", "its", "it's", "you", "your",
}
EXCERPT_MIN_OVERLAP = 0.3


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS}


def best_excerpt(pain: str, interview: InterviewRecord) -> str:
    """The note sentence that best matches an AI-paraphrased pain point (or "" if none is close).

    Candidates come from the participant's own fields, so the result is verbatim text.
    The verbatim quote field is preferred on a tie.
    """
    target = _content_words(pain)
    if not target:
        return ""
    best, best_score = "", 0.0
    for field in ("verbatim_quote", "pain", "behavior"):
        for sentence in split_sentences(getattr(interview, field)):
            words = _content_words(sentence)
            if not words:
                continue
            score = len(target & words) / len(target | words)
            if score > best_score:
                best, best_score = sentence, score
    return clean_quote(best) if best_score >= EXCERPT_MIN_OVERLAP else ""


def valid_partition(groups: list[list[int]], n: int) -> list[list[int]]:
    """Turn an AI grouping into a partition of 0..n-1: unknown numbers are dropped, repeats keep
    their first group, and anything left out stays on its own. Never loses a cluster."""
    seen: set[int] = set()
    out: list[list[int]] = []
    for group in groups:
        clean = [j for j in dict.fromkeys(group) if isinstance(j, int) and 0 <= j < n and j not in seen]
        seen.update(clean)
        if clean:
            out.append(clean)
    out += [[j] for j in range(n) if j not in seen]
    return out


def looks_like_complaint(text: str) -> bool:
    """True for a pain statement with no positive signal (not valid counter-evidence)."""
    has_positive = bool(lexicon.match_terms(text, lexicon.POSITIVE_CUES))
    has_negative = bool(lexicon.match_terms(text, lexicon.NEGATIVE_CUES)) or bool(
        re.search(r"\b(?:no|not|never|nothing|without)\b|n't\b", text.lower())
    )
    return has_negative and not has_positive


# ---------------------------------------------------------------------------
# Clustering helpers
# ---------------------------------------------------------------------------


def agglomerate(vectors: np.ndarray, threshold: float) -> list[list[int]]:
    """Average-linkage agglomerative clustering on cosine similarity (vectors are normalised)."""
    n = len(vectors)
    if n == 0:
        return []
    sim = vectors @ vectors.T
    clusters: list[list[int]] = [[i] for i in range(n)]
    while len(clusters) > 1:
        best, pair = -1.0, None
        for a in range(len(clusters)):
            for b in range(a + 1, len(clusters)):
                s = float(sim[np.ix_(clusters[a], clusters[b])].mean())
                if s > best:
                    best, pair = s, (a, b)
        if pair is None or best < threshold:
            break
        a, b = pair
        clusters[a] = clusters[a] + clusters[b]
        del clusters[b]
    return clusters


def cohesion(vectors: np.ndarray) -> float:
    if len(vectors) < 2:
        return 1.0
    sim = vectors @ vectors.T
    n = len(vectors)
    return float((sim.sum() - n) / (n * (n - 1)))


def _centroid(vectors: np.ndarray) -> list[float]:
    c = vectors.mean(axis=0)
    n = np.linalg.norm(c)
    return (c / n if n else c).tolist()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(
    interviews: list[InterviewRecord],
    objectives: list[str],
    engine: AIEngine,
    embedder: Embedder,
    progress: Callable[[str], None] = lambda _stage: None,
) -> PipelineResult:
    warnings: list[dict[str, str]] = []
    total_participants = len({iv.key for iv in interviews})

    # 1. Extraction --------------------------------------------------------------
    progress("extraction")
    points: list[PainPointDraft] = []
    unverified = 0
    excerpts_used = 0
    for iv in interviews:
        result = engine.extract(iv.text(), objectives)
        interview_tags = set(lexicon.sensitive_tags(iv.full_text()))
        for p in result.pain_points:
            quote, ok = verify_quote(p.quote, iv)
            if p.quote and not ok:
                unverified += 1
            if not ok:
                # No usable quote from the AI: use the sentence from the notes that best matches
                # the pain point. It is copied from the notes, so it is still verbatim evidence.
                excerpt = best_excerpt(p.pain, iv)
                if excerpt:
                    quote, ok = verify_quote(excerpt, iv)
                    excerpts_used += int(ok)
            # Sensitive tags must be grounded in the participant's own words: keyword rules on the
            # pain + quote always apply; an AI tag is kept only if the interview text supports it.
            tags = set(lexicon.sensitive_tags(p.pain + " " + quote)) | (set(p.sensitive_tags) & interview_tags)
            points.append(
                PainPointDraft(
                    interview=iv,
                    text=p.pain.strip(),
                    quote=quote if ok else "",
                    quote_verified=ok,
                    source_field=(locate_field(quote, iv) or p.source_field) if ok else None,
                    severity=p.severity,
                    sensitive_tags=sorted(tags),
                )
            )
    if len(points) > MAX_PAIN_POINTS:
        warnings.append({"code": "truncated", "message": f"Only the first {MAX_PAIN_POINTS} pain points were clustered."})
        points = points[:MAX_PAIN_POINTS]
    if not points:
        raise ValueError("No pain points could be extracted from the valid interviews.")

    # 2. Embeddings --------------------------------------------------------------
    progress("embeddings")
    vectors = embedder.embed([p.text for p in points])
    for p, v in zip(points, vectors):
        p.embedding = v

    # 3. Similarity + per-participant dedupe (a participant is never counted twice) --
    progress("similarity")
    matrix = np.asarray(vectors, dtype=float)
    sim = matrix @ matrix.T
    keep: list[int] = []
    for i, p in enumerate(points):
        dup_of = next(
            (k for k in keep if points[k].interview.key == p.interview.key and sim[i, k] >= DUPLICATE_SIMILARITY),
            None,
        )
        if dup_of is None:
            keep.append(i)
        else:
            points[dup_of].duplicate_count += 1
            points[dup_of].severity = max(points[dup_of].severity, p.severity)
    duplicates_merged = len(points) - len(keep)
    points = [points[i] for i in keep]
    matrix = matrix[keep]

    # 4. Clustering + naming -----------------------------------------------------
    progress("clustering")
    clusters = agglomerate(matrix, embedder.cluster_threshold)
    # The AI may merge small clusters that describe the same problem. It only sees numbered
    # clusters of pain-point text; Python validates the grouping and does all the counting.
    initial_clusters = len(clusters)
    if len(clusters) > 1:
        grouping = engine.group_clusters([[points[i].text for i in c] for c in clusters])
        clusters = [sum((clusters[j] for j in group), []) for group in valid_partition(grouping.groups, len(clusters))]
    merged_by_ai = initial_clusters - len(clusters)
    themes: list[ThemeDraft] = []
    def add_theme(members: list[int], naming) -> None:
        pps = [points[i] for i in members]
        participants: dict[str, str] = {}
        for p in pps:
            participants.setdefault(p.interview.key, p.interview.participant_id)
        themes.append(
            ThemeDraft(
                name=naming.name.strip(),
                description=naming.description.strip(),
                pain_points=pps,
                participant_ids=sorted(participants.values(), key=str.lower),
                participant_count=len(participants),
                total_participants=total_participants,
                frequency=0.0,
                cohesion=cohesion(matrix[members]),
                coherence=naming.coherence,
                embedding=_centroid(matrix[members]),
            )
        )

    clusters_split = 0
    for members in clusters:
        naming = engine.name_theme([points[i].text for i in members])
        # The AI judges whether a cluster is one problem. If it says the cluster mixes problems,
        # re-cluster its members more tightly and name the parts separately (one level only).
        if len(members) >= MIN_SPLIT_SIZE and naming.coherence < SPLIT_COHERENCE:
            # Stricter than the cluster's own average similarity: pain points about different
            # problems fall below it, pain points about the same problem stay above.
            split_at = max(embedder.cluster_threshold + SPLIT_STEP, cohesion(matrix[members]) + 1e-6)
            parts = [[members[i] for i in part] for part in agglomerate(matrix[members], split_at)]
            if len(parts) > 1:
                clusters_split += 1
                for part in parts:
                    add_theme(part, engine.name_theme([points[i].text for i in part]))
                continue
        add_theme(members, naming)
    _dedupe_names(themes)

    # 5. Evidence (supporting) — verified quotes only, linked to the interview ------
    progress("evidence")
    for t in themes:
        seen: set[tuple[str, str]] = set()
        for p in t.pain_points:
            key = (p.interview.key, _norm(p.quote) or _norm(p.text))
            if key in seen:
                continue
            seen.add(key)
            t.evidence.append(
                EvidenceDraft(
                    interview=p.interview,
                    quote=p.quote,
                    quote_verified=p.quote_verified,
                    source_field=p.source_field,
                    stance="supporting",
                    note=p.text,
                    pain_point=p,
                )
            )
        if not any(e.quote_verified for e in t.evidence):
            t.evidence_status = "insufficient"

    # 6. Frequency — deterministic -------------------------------------------------
    progress("frequency")
    for t in themes:
        t.frequency = round(t.participant_count / total_participants, 4) if total_participants else 0.0

    # 7. Insights -------------------------------------------------------------------
    progress("insights")
    for t in themes:
        label = f"{t.participant_count} of {t.total_participants} participants"
        draft = engine.draft_insight(t.name, t.description, [p.text for p in t.pain_points], label, objectives)
        t.statement, t.implication = draft.statement.strip(), draft.implication.strip()
        t.severity = max(draft.severity, max(p.severity for p in t.pain_points))
        t.strategic_relevance = draft.strategic_relevance
        verified_ratio = sum(e.quote_verified for e in t.evidence) / max(1, len(t.evidence))
        conf = 0.4 * max(0.0, t.cohesion) + 0.3 * t.coherence + 0.3 * verified_ratio
        if t.participant_count == 1:
            conf = min(conf, 0.5)  # one voice is weak evidence, however clear
        t.confidence = round(min(1.0, conf), 2)
        t.is_low_confidence = t.participant_count > 1 and t.confidence < LOW_CONFIDENCE

    # 8. Contradictions, outliers, sensitivity ---------------------------------------
    progress("contradictions")
    iv_vectors = np.asarray(embedder.embed([iv.full_text() for iv in interviews]), dtype=float)
    for t in themes:
        in_theme = {p.interview.key for p in t.pain_points}
        centroid = np.asarray(t.embedding)
        ranked = sorted(
            (i for i, iv in enumerate(interviews) if iv.key not in in_theme),
            key=lambda i: float(iv_vectors[i] @ centroid),
            reverse=True,
        )[:CONTRADICTION_CANDIDATES]
        for i in ranked:
            iv = interviews[i]
            check = engine.check_contradiction(t.name, t.description, iv.full_text())
            if not check.contradicts:
                continue
            quote, ok = verify_quote(check.quote, iv)
            if ok and looks_like_complaint(quote):
                # Small models sometimes label another complaint as a "contradiction".
                # Counter-evidence must describe a positive experience, not another pain.
                continue
            t.evidence.append(
                EvidenceDraft(
                    interview=iv,
                    quote=quote if ok else "",
                    quote_verified=ok,
                    source_field=locate_field(quote, iv) if ok else None,
                    stance="contradicting",
                    note=check.explanation.strip(),
                )
            )
            t.has_contradictions = True

        t.is_outlier = t.participant_count == 1
        # Grounded in evidence only (pain-point tags + verified supporting quotes), never in the
        # AI-written theme name or description.
        tags = set().union(*(p.sensitive_tags for p in t.pain_points))
        tags |= set(
            lexicon.sensitive_tags(" ".join(e.quote for e in t.evidence if e.stance == "supporting" and e.quote_verified))
        )
        t.sensitive_tags = sorted(tags)

    # Order: most participants first, then confidence. Codes follow that order.
    themes.sort(key=lambda t: (-t.participant_count, -t.confidence, t.name))
    for n, t in enumerate(themes, start=1):
        t.code = f"T{n}"

    # Human fallback rules (B, C, F) -------------------------------------------------
    recurring = [t for t in themes if not t.is_outlier]
    if total_participants >= 8 and len(themes) < 3:
        warnings.append(
            {
                "code": "few_themes",
                "message": f"Only {len(themes)} theme(s) from {total_participants} participants. The notes may be "
                "inconsistent or too brief. Please review before relying on this synthesis.",
            }
        )
    outliers = [t for t in themes if t.is_outlier]
    high_impact = [t for t in outliers if t.severity >= 4]
    if outliers:
        warnings.append(
            {
                "code": "outliers",
                "message": f"{len(outliers)} theme(s) come from a single participant and were kept for review"
                + (f"; {len(high_impact)} look high-impact." if high_impact else "."),
            }
        )
    low = [t for t in themes if t.is_low_confidence]
    if low:
        warnings.append(
            {
                "code": "low_confidence",
                "message": f"{len(low)} theme(s) have low clustering confidence. Review and regroup if needed.",
            }
        )
    if unverified:
        warnings.append(
            {
                "code": "unverified_quotes",
                "message": f"{unverified} AI-suggested quote(s) did not match the original notes and were discarded.",
            }
        )

    stats = {
        "interviews": len(interviews),
        "participants": total_participants,
        "pain_points": len(points),
        "duplicates_merged": duplicates_merged,
        "themes": len(themes),
        "recurring_themes": len(recurring),
        "outliers": len(outliers),
        "high_impact_outliers": len(high_impact),
        "contradictions": sum(1 for t in themes for e in t.evidence if e.stance == "contradicting"),
        "sensitive_themes": sum(1 for t in themes if t.requires_approval),
        "unverified_quotes": unverified,
        "quotes_from_notes": excerpts_used,
        "clusters_split": clusters_split,
        "clusters_merged_by_ai": merged_by_ai,
    }
    return PipelineResult(pain_points=points, themes=themes, warnings=warnings, stats=stats)


def _dedupe_names(themes: list[ThemeDraft]) -> None:
    seen: dict[str, int] = {}
    for t in themes:
        k = t.name.lower()
        seen[k] = seen.get(k, 0) + 1
        if seen[k] > 1:
            t.name = f"{t.name} ({seen[k]})"
