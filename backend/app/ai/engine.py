"""Semantic tasks used by the synthesis pipeline.

The pipeline depends only on `AIEngine`. Two implementations:
- `LLMEngine`: prompts an `LLMProvider` (Ollama / Groq) with Pydantic-validated JSON output.
- `DemoEngine`: deterministic, offline, rule-based. Labelled as demo everywhere in the UI.

The engine never sees participant IDs or decides counts: the pipeline feeds it one
interview or one cluster at a time and does all arithmetic itself.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass

from app.ai import lexicon
from app.ai.providers import LLMProvider, build_llm
from app.ai.schemas import (
    ClusterGrouping,
    ContradictionCheck,
    ExtractedPainPoint,
    ExtractionResult,
    InsightDraft,
    ThemeNaming,
)
from app.core.config import Settings


@dataclass
class InterviewText:
    pain: str
    behavior: str
    verbatim_quote: str
    participant_role: str = ""
    company_size: str = ""
    plan_tier: str = ""

    def as_prompt(self) -> str:
        return (
            f"Participant role: {self.participant_role or 'unknown'}\n"
            f"Company size: {self.company_size or 'unknown'}\n"
            f"Plan tier: {self.plan_tier or 'unknown'}\n"
            f"PAIN: {self.pain}\n"
            f"BEHAVIOR: {self.behavior}\n"
            f"VERBATIM QUOTE: {self.verbatim_quote}"
        )


class AIEngine(ABC):
    name: str
    model: str
    is_demo: bool = False

    @abstractmethod
    def extract(self, interview: InterviewText, objectives: list[str]) -> ExtractionResult: ...

    @abstractmethod
    def name_theme(self, pain_points: list[str]) -> ThemeNaming: ...

    def group_clusters(self, clusters: list[list[str]]) -> ClusterGrouping:
        """Which small clusters describe the same problem. Default: keep them all separate."""
        return ClusterGrouping(groups=[[i] for i in range(len(clusters))])

    @abstractmethod
    def check_contradiction(self, theme_name: str, theme_description: str, candidate: str) -> ContradictionCheck: ...

    @abstractmethod
    def draft_insight(
        self,
        theme_name: str,
        theme_description: str,
        evidence: list[str],
        participant_label: str,
        objectives: list[str],
    ) -> InsightDraft: ...


# ---------------------------------------------------------------------------
# LLM-backed engine
# ---------------------------------------------------------------------------

_RULES = (
    "You are a careful user-research analyst. Never invent facts, participants, numbers or quotes. "
    "Quotes must be copied EXACTLY, character for character, from the provided text; if no exact "
    "supporting text exists, return an empty string for the quote."
)


class LLMEngine(AIEngine):
    def __init__(self, provider: LLMProvider):
        self.provider = provider
        self.name = provider.name
        self.model = provider.model

    def extract(self, interview: InterviewText, objectives: list[str]) -> ExtractionResult:
        return self.provider.generate_json(
            ExtractionResult,
            system=_RULES
            + " Split the interview's problems into atomic pain points (one problem each). Ignore "
            "positive statements: they are not pain points. Merge restatements of the same problem. "
            "Tag sensitive_tags with pricing, churn or competitive_switching only when the text is "
            "about price/cost, cancelling/leaving, or moving to another product.",
            user=f"Research objectives: {'; '.join(objectives) or 'not specified'}\n\nINTERVIEW:\n"
            f"{interview.as_prompt()}",
        )

    def name_theme(self, pain_points: list[str]) -> ThemeNaming:
        listing = "\n".join(f"- {p}" for p in pain_points[:40])
        return self.provider.generate_json(
            ThemeNaming,
            system=_RULES
            + " Name the single underlying user problem these pain points share, in 3-8 words, as a "
            "problem statement (not a solution). Describe it in 1-2 sentences using only the given "
            "pain points. Rate coherence 0-1: low if they describe different problems.",
            user=f"Pain points from different participants:\n{listing}",
        )

    def group_clusters(self, clusters: list[list[str]]) -> ClusterGrouping:
        listing = "\n".join(
            f"Cluster {i}:\n" + "\n".join(f"  - {p}" for p in items[:6]) for i, items in enumerate(clusters)
        )
        return self.provider.generate_json(
            ClusterGrouping,
            system=_RULES
            + " You are grouping small clusters of user pain points into research themes. Put clusters in the "
            "same group ONLY if they describe the same underlying user problem (one problem a product team "
            "would fix with one initiative). Keep distinct problems apart, even if they share words such as "
            "'dashboard' or 'data'. Pricing, cancellation/churn, switching to competitors, security/compliance "
            "and performance are always separate problems from each other. Use every cluster number exactly once; "
            "a group may contain a single cluster.",
            user=listing,
        )

    def check_contradiction(self, theme_name: str, theme_description: str, candidate: str) -> ContradictionCheck:
        return self.provider.generate_json(
            ContradictionCheck,
            system=_RULES
            + " Decide whether the candidate interview directly CONTRADICTS the theme (the participant "
            "reports the opposite experience). Unrelated or merely different topics are NOT "
            "contradictions. If it contradicts, copy the exact sentence that shows it.",
            user=f"THEME: {theme_name}\n{theme_description}\n\nCANDIDATE INTERVIEW:\n{candidate}",
        )

    def draft_insight(self, theme_name, theme_description, evidence, participant_label, objectives) -> InsightDraft:
        listing = "\n".join(f"- {e}" for e in evidence[:20])
        return self.provider.generate_json(
            InsightDraft,
            system=_RULES
            + " Write a concise insight and a product implication grounded only in the evidence. "
            "Rate severity (impact on users, 1-5) independently of how many people mentioned it. "
            "Rate strategic_relevance (1-5) against the research objectives. Do not restate counts.",
            user=f"Research objectives: {'; '.join(objectives) or 'not specified'}\n"
            f"THEME: {theme_name}\n{theme_description}\nMentioned by: {participant_label}\n"
            f"EVIDENCE:\n{listing}",
        )


# ---------------------------------------------------------------------------
# Offline demo engine (deterministic, rule-based)
# ---------------------------------------------------------------------------

_THEME_NAMES = {
    "integration": ("Connecting data sources is slow and fragile",
                    "Participants struggle to connect their data sources, which delays or blocks evaluation.",
                    "Make the first data connection self-serve and resilient, with clear errors and trial-safe permissions."),
    "sharing": ("Sharing results with non-users is hard",
                "Stakeholders who don't use the product can't easily see dashboards.",
                "Offer lightweight read-only sharing for people who only consume results."),
    "export": ("Exports need manual rework",
               "Exported reports lose formatting or need rebuilding in other tools.",
               "Improve export fidelity (PDF, slides, spreadsheets) for recurring reporting."),
    "performance": ("Dashboards are too slow on real data",
                    "Dashboards load or refresh slowly with production-sized data.",
                    "Investigate query performance and caching for large datasets."),
    "pricing": ("Pricing is unclear or hard to justify",
                "Participants find the cost model confusing or poorly matched to how they use the product.",
                "Review the pricing model and make costs predictable (requires approval before sharing)."),
    "permissions": ("Access control is too coarse",
                    "Participants can't give the right people the right level of access.",
                    "Add granular roles and scoped access."),
    "compliance": ("Compliance requirements block adoption",
                   "Security or compliance requirements stop the product from being adopted.",
                   "Assess compliance gaps (e.g. certifications) that block larger customers."),
    "onboarding": ("Hard to reach value during the trial",
                   "Participants don't reach a meaningful result within the trial.",
                   "Shorten time-to-value in the first session of the trial."),
    "trust": ("Numbers aren't trusted",
              "Participants doubt the accuracy of reported figures.",
              "Make data lineage and reconciliation visible."),
    "churn": ("Risk of cancelling or downgrading",
              "Participants describe reasons they might stop using the product.",
              "Investigate retention risk (requires approval before sharing)."),
    "competitive_switching": ("Considering alternative products",
                              "Participants compare or move to alternative products.",
                              "Understand competitive gaps (requires approval before sharing)."),
}
_SENT_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")
# Split compound sentences into atomic clauses ("X is broken, and Y costs too much").
_CLAUSE_SPLIT = re.compile(r",\s+(?:and|but|while|plus)\s+|;\s*", re.IGNORECASE)
_NEGATION = re.compile(r"\b(?:no|not|never|nothing|without|nobody)\b|n't\b", re.IGNORECASE)
# Name priority when two topics are equally represented in a cluster: specific and
# sensitive topics first, broad ones (sharing, onboarding) last.
_CONCEPT_PRIORITY = [
    "churn", "competitive_switching", "pricing", "compliance", "integration", "performance",
    "export", "permissions", "trust", "sharing", "onboarding",
]


_BACK_REFERENCE = re.compile(r"\b(?:them|it|they|those|this|that|these|which)\b", re.IGNORECASE)


def split_sentences(text: str) -> list[str]:
    out = []
    for sentence in _SENT_SPLIT.split(text or ""):
        sentence = sentence.strip()
        parts = [p.strip() for p in _CLAUSE_SPLIT.split(sentence)]
        # Only split when every clause stands on its own (≥5 words, no pronoun pointing back).
        if len(parts) > 1 and all(len(p.split()) >= 5 for p in parts) and not any(
            _BACK_REFERENCE.search(p) for p in parts[1:]
        ):
            out.extend(parts)
        elif len(sentence.split()) >= 3:
            out.append(sentence)
    return out


def _is_positive(sentence: str) -> bool:
    return (
        bool(lexicon.match_terms(sentence, lexicon.POSITIVE_CUES))
        and not lexicon.match_terms(sentence, lexicon.NEGATIVE_CUES)
        and not _NEGATION.search(sentence)
    )


def _severity(text: str) -> int:
    sev = 3
    if lexicon.match_terms(text, lexicon.HIGH_SEVERITY_CUES):
        sev += 1
    if len(lexicon.match_terms(text, lexicon.NEGATIVE_CUES)) >= 2:
        sev += 1
    return max(1, min(5, sev))


class DemoEngine(AIEngine):
    name = "demo"
    model = "deterministic-demo"
    is_demo = True

    def extract(self, interview: InterviewText, objectives: list[str]) -> ExtractionResult:
        points: list[ExtractedPainPoint] = []
        quote_concepts = set(lexicon.concepts(interview.verbatim_quote))
        for sentence in split_sentences(interview.pain):
            if _is_positive(sentence):
                continue  # not a pain point; may still be contradicting evidence
            c = set(lexicon.concepts(sentence))
            use_quote = bool(interview.verbatim_quote and c & quote_concepts)
            quote = interview.verbatim_quote if use_quote else sentence
            points.append(
                ExtractedPainPoint(
                    pain=sentence[:500],
                    quote=quote,
                    source_field="verbatim_quote" if use_quote else "pain",
                    severity=_severity(sentence + " " + (quote if use_quote else "")),
                    sensitive_tags=lexicon.sensitive_tags(sentence),
                )
            )
        return ExtractionResult(pain_points=points[:12])

    def name_theme(self, pain_points: list[str]) -> ThemeNaming:
        counts = Counter(c for p in pain_points for c in set(lexicon.concepts(p)))
        if counts:
            best = max(counts.values())
            top = next(c for c in _CONCEPT_PRIORITY if counts.get(c) == best)
            n = best
            name, desc, _ = _THEME_NAMES[top]
            return ThemeNaming(name=name, description=desc, coherence=round(n / len(pain_points), 2))
        words = Counter(
            w for p in pain_points for w in re.findall(r"[a-z]{5,}", p.lower())
        ).most_common(3)
        label = ", ".join(w for w, _ in words) or "miscellaneous"
        return ThemeNaming(
            name=f"Other: {label}"[:120],
            description=f"Pain points mentioning {label}.",
            coherence=0.3,
        )

    def check_contradiction(self, theme_name: str, theme_description: str, candidate: str) -> ContradictionCheck:
        theme_concepts = set(lexicon.concepts(theme_name + " " + theme_description))
        for sentence in split_sentences(candidate):
            if _is_positive(sentence) and theme_concepts & set(lexicon.concepts(sentence)):
                return ContradictionCheck(
                    contradicts=True,
                    explanation="Describes a positive experience on the same topic.",
                    quote=sentence,
                )
        return ContradictionCheck(contradicts=False)

    def draft_insight(self, theme_name, theme_description, evidence, participant_label, objectives) -> InsightDraft:
        concept_counts = Counter(c for e in evidence for c in set(lexicon.concepts(e)))
        top = None
        if concept_counts:
            best = max(concept_counts.values())
            top = next(c for c in _CONCEPT_PRIORITY if concept_counts.get(c) == best)
        implication = _THEME_NAMES[top][2] if top else "Review the evidence with the team before acting."
        obj_words = {w for o in objectives for w in re.findall(r"[a-z]{4,}", o.lower())}
        ev_words = {w for e in evidence + [theme_name] for w in re.findall(r"[a-z]{4,}", e.lower())}
        relevance = 4 if obj_words & ev_words else 3
        if top in ("pricing", "churn", "competitive_switching", "compliance"):
            relevance = min(5, relevance + 1)
        return InsightDraft(
            statement=f"{theme_description}",
            implication=implication,
            severity=max((_severity(e) for e in evidence), default=3),
            strategic_relevance=relevance,
        )


def build_engine(settings: Settings) -> AIEngine:
    if settings.ai_provider == "demo":
        return DemoEngine()
    return LLMEngine(build_llm(settings))
