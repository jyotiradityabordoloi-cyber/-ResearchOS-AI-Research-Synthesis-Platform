"""Research copilot: answers questions about one project, grounded in its own data.

How it stays honest
- The model only sees a context built here from the database: themes with their real
  participant counts, quotes with each participant's segment, insights, and segment
  coverage. Every item has a short key (T3, E12, I2, P) the answer must cite.
- Citations are checked against that key map; unknown keys are removed, never invented.
- With the offline demo engine, or when the provider fails, no model is called. The
  answer is then built by plain rules from the same data and labelled as such (`mode`
  is "demo" or "fallback"), so a rule-based summary is never presented as AI output.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.engine import AIEngine, LLMEngine
from app.ai.providers import LLMError
from app.models import Insight, Interview, ResearchProject, Theme, ThemeEvidence
from app.models.enums import EvidenceStance, ReviewStatus, ValidationStatus
from app.schemas import CopilotAnswer, CopilotCitation, CopilotRequest
from app.services.projects import live_filter
from app.services.review import priority_band

log = logging.getLogger(__name__)

MAX_EVIDENCE = 60  # quotes sent to the model when no theme is selected
CITE = re.compile(r"\[(T\d+|E\d+|I\d+|P)\]")


class LLMAnswer(BaseModel):
    answer: str = Field(description="Plain text; short paragraphs or '- ' bullets. Cite items like [T2] or [E5].")
    citations: list[str] = Field(default_factory=list, description="Every key cited in the answer, e.g. ['T2', 'E5'].")


SYSTEM = """You are a research copilot for a product team. Answer the question using ONLY the
project context provided. Rules:
- Every factual claim cites its source key in square brackets: themes [T3], quotes [E12],
  insights [I2], the selected interview [P]. One key per bracket, e.g. [T3] [E12]; never
  ranges or lists of every item.
- "This theme", "this interview" and "this insight" mean the FOCUS given before the question.
- Never invent quotes, participants, numbers or segments. Quote text only from the context.
- Frequency means the share of unique participants who raised a theme; it is not importance.
  Keep frequency, severity and strategic relevance separate.
- Mention contradicting evidence when it exists. Say "single participant" for one-person themes.
- If the context cannot answer the question, say so plainly and suggest what research would.
- Be concise: at most ~180 words, short paragraphs or "- " bullets, no headings."""


@dataclass
class Item:
    key: str
    kind: str  # theme | evidence | insight | interview
    label: str
    theme_id: uuid.UUID | None = None
    interview_id: uuid.UUID | None = None
    insight_id: uuid.UUID | None = None
    participant_id: str | None = None
    quote: str | None = None
    stance: str | None = None


@dataclass
class Context:
    project: ResearchProject
    themes: list[Theme]
    focus_theme: Theme | None
    focus_interview: Interview | None
    focus_insight: Insight | None
    segments: dict[str, dict[str, str]]  # participant_id(lower) -> role/size/plan
    items: dict[str, Item] = field(default_factory=dict)
    evidence: list[tuple[str, ThemeEvidence, Theme]] = field(default_factory=list)
    insights: list[tuple[str, Insight]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------


def build_context(db: Session, project: ResearchProject, req: CopilotRequest) -> Context:
    themes = list(
        db.scalars(
            select(Theme).where(
                live_filter(Theme, project), Theme.status.notin_((ReviewStatus.MERGED, ReviewStatus.REJECTED))
            )
        )
    )
    themes.sort(key=lambda t: (-t.participant_count, t.code))
    by_id = {t.id: t for t in themes}

    interviews = list(
        db.scalars(
            select(Interview).where(
                Interview.project_id == project.id, Interview.validation_status == ValidationStatus.VALID
            )
        )
    )
    segments = {
        iv.participant_id.lower(): {"role": iv.participant_role, "size": iv.company_size, "plan": iv.plan_tier}
        for iv in interviews
    }

    focus_insight = db.get(Insight, req.insight_id) if req.insight_id else None
    if focus_insight and focus_insight.project_id != project.id:
        focus_insight = None
    theme_id = req.theme_id or (focus_insight.theme_id if focus_insight else None)
    focus_theme = by_id.get(theme_id) if theme_id else None
    focus_interview = db.get(Interview, req.interview_id) if req.interview_id else None
    if focus_interview and focus_interview.project_id != project.id:
        focus_interview = None

    ctx = Context(project, themes, focus_theme, focus_interview, focus_insight, segments)
    for t in themes:
        ctx.items[t.code] = Item(t.code, "theme", f"{t.code} {t.name}", theme_id=t.id)

    ev_rows = list(
        db.scalars(select(ThemeEvidence).where(ThemeEvidence.theme_id.in_(list(by_id))))
    ) if by_id else []
    # Selected theme first, then contradictions, then verified quotes from the biggest themes.
    ev_rows.sort(
        key=lambda e: (
            e.theme_id != (focus_theme.id if focus_theme else None),
            e.stance != EvidenceStance.CONTRADICTING,
            not e.quote_verified,
            -by_id[e.theme_id].participant_count,
        )
    )
    for n, e in enumerate(ev_rows[:MAX_EVIDENCE], start=1):
        key = f"E{n}"
        t = by_id[e.theme_id]
        ctx.evidence.append((key, e, t))
        ctx.items[key] = Item(
            key, "evidence", f"{e.participant_id} on {t.code}", theme_id=t.id, interview_id=e.interview_id,
            participant_id=e.participant_id, quote=e.quote, stance=e.stance,
        )

    rows = list(
        db.scalars(
            select(Insight).where(live_filter(Insight, project), Insight.status.notin_((ReviewStatus.MERGED, ReviewStatus.REJECTED)))
        )
    )
    rows.sort(key=lambda i: -i.priority_score)
    for n, i in enumerate(rows[:12], start=1):
        key = f"I{n}"
        ctx.insights.append((key, i))
        ctx.items[key] = Item(key, "insight", i.title, insight_id=i.id, theme_id=i.theme_id)

    if focus_interview:
        ctx.items["P"] = Item(
            "P", "interview", f"Interview {focus_interview.participant_id}", interview_id=focus_interview.id,
            participant_id=focus_interview.participant_id,
        )
    return ctx


def coverage(ctx: Context) -> dict[str, Counter]:
    out: dict[str, Counter] = {"role": Counter(), "size": Counter(), "plan": Counter()}
    for seg in ctx.segments.values():
        for k in out:
            if seg[k]:
                out[k][seg[k]] += 1
    return out


def _segment_of(ctx: Context, pid: str) -> str:
    s = ctx.segments.get(pid.lower())
    return " · ".join(x for x in (s or {}).values() if x) if s else "segment unknown"


def context_text(ctx: Context) -> str:
    p = ctx.project
    cov = coverage(ctx)
    lines = [
        f"PROJECT: {p.name}",
        f"Objectives: {'; '.join(p.objectives) or 'none recorded'}",
        f"Target segments: {', '.join(p.target_segments) or 'none recorded'}",
        f"Valid participants: {len(ctx.segments)}",
        "Coverage by role: " + ", ".join(f"{k} {v}" for k, v in cov["role"].most_common()),
        "Coverage by company size: " + ", ".join(f"{k} {v}" for k, v in cov["size"].most_common()),
        "Coverage by plan: " + ", ".join(f"{k} {v}" for k, v in cov["plan"].most_common()),
        "",
        "THEMES (frequency = unique participants / all participants):",
    ]
    for t in ctx.themes:
        flags = [
            "SELECTED" if ctx.focus_theme and t.id == ctx.focus_theme.id else "",
            "single participant" if t.is_outlier else "",
            "has contradicting evidence" if t.has_contradictions else "",
            f"sensitive: {', '.join(t.sensitive_tags)}" if t.requires_approval else "",
            f"review status: {t.status}",
        ]
        lines.append(
            f"[{t.code}] {t.name} | {t.participant_count}/{t.total_participants} participants ({round(t.frequency * 100)}%) "
            f"| severity {t.severity}/5 | confidence {round(t.confidence * 100)}% | {'; '.join(f for f in flags if f)}"
        )
        if t.description:
            lines.append(f"    {t.description}")
    lines += ["", "QUOTES (verbatim from interview notes unless marked unverified):"]
    for key, e, t in ctx.evidence:
        lines.append(
            f"[{key}] {e.participant_id} ({_segment_of(ctx, e.participant_id)}) on {t.code}, {e.stance}"
            f"{'' if e.quote_verified else ', unverified'}: \"{e.quote}\""
        )
    lines += ["", "INSIGHTS:"]
    for key, i in ctx.insights:
        lines.append(
            f"[{key}] {i.title} | priority {i.priority_override or priority_band(i.priority_score)} | severity {i.severity}/5 "
            f"| strategic relevance {i.strategic_relevance}/5 | status {i.status} | implication: {i.implication or '-'}"
        )
    if ctx.focus_interview:
        iv = ctx.focus_interview
        lines += [
            "",
            f"SELECTED INTERVIEW [P]: {iv.participant_id} ({iv.participant_role} · {iv.company_size} · {iv.plan_tier})",
            f"Pain: {iv.pain}",
            f"Behavior: {iv.behavior}",
            f"Quote: {iv.verbatim_quote}",
        ]
    return "\n".join(lines)


def focus_text(ctx: Context) -> str:
    """What the person is looking at, so "this theme" resolves to one item."""
    parts = []
    if ctx.focus_theme:
        parts.append(f"the user is looking at theme [{ctx.focus_theme.code}] {ctx.focus_theme.name}")
    if ctx.focus_insight:
        key = next((k for k, i in ctx.insights if i.id == ctx.focus_insight.id), None)
        parts.append(f"insight {f'[{key}] ' if key else ''}{ctx.focus_insight.title}")
    if ctx.focus_interview:
        parts.append(f"interview [P] with {ctx.focus_interview.participant_id}")
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Answering
# ---------------------------------------------------------------------------


def answer(db: Session, project: ResearchProject, req: CopilotRequest, engine: AIEngine | None, build_error: str | None) -> CopilotAnswer:
    ctx = build_context(db, project, req)
    meta = {
        "theme_code": ctx.focus_theme.code if ctx.focus_theme else None,
        "interview_participant": ctx.focus_interview.participant_id if ctx.focus_interview else None,
        "evidence_in_context": len(ctx.evidence),
    }
    if not ctx.themes and not ctx.focus_interview:
        return CopilotAnswer(
            answer="This project has no synthesised themes yet, so there is nothing to answer from. Run synthesis first.",
            citations=[], mode="demo" if not isinstance(engine, LLMEngine) else "ai",
            provider=getattr(engine, "name", "demo"), model=getattr(engine, "model", ""), notice=None, **meta,
        )

    if isinstance(engine, LLMEngine):
        try:
            history = "\n".join(f"{m.role.upper()}: {m.content[:800]}" for m in req.history[-4:])
            user = (
                f"{context_text(ctx)}\n\n"
                + (f"EARLIER IN THIS CONVERSATION:\n{history}\n\n" if history else "")
                + (f"FOCUS: {focus_text(ctx)}\n" if focus_text(ctx) else "")
                + f"QUESTION: {req.question}"
            )
            out = engine.provider.generate_json(LLMAnswer, SYSTEM, user)
            text, cites = _clean_citations(out.answer, out.citations, ctx)
            if not text.strip():
                raise LLMError("The model returned an empty answer.")
            return CopilotAnswer(
                answer=text, citations=cites, mode="ai", provider=engine.name, model=engine.provider.model, notice=None, **meta
            )
        except LLMError as exc:
            log.warning("Copilot fell back to rules: %s", exc)
            text, cites = rule_answer(ctx, req.question)
            return CopilotAnswer(
                answer=text, citations=cites, mode="fallback", provider=engine.name, model=engine.provider.model,
                notice=f"The AI provider did not answer ({str(exc)[:160]}). This is a rule-based summary of your data instead.",
                **meta,
            )

    text, cites = rule_answer(ctx, req.question)
    return CopilotAnswer(
        answer=text, citations=cites, mode="demo", provider="demo", model="rules",
        notice=build_error
        or "Demo mode: no AI model is configured, so this answer was assembled by fixed rules from your project data.",
        **meta,
    )


BRACKET = re.compile(r"\[([^\[\]\n]{1,80})\]")
KEY = re.compile(r"^(T\d+|E\d+|I\d+|P)$")


def _clean_citations(text: str, cited: list[str], ctx: Context) -> tuple[str, list[CopilotCitation]]:
    """Keep only citations that point at real context items, one key per bracket.

    "[T1, E4]" becomes "[T1] [E4]"; ranges like "[T1-T9]" and unknown keys are dropped,
    because a citation must point at one specific, checkable thing. The returned list is
    exactly the keys left in the text (the model's own list is not trusted).
    """

    def fix(m: re.Match) -> str:
        parts = [p.strip() for p in re.split(r"[,;]|\s+", m.group(1)) if p.strip()]
        if not parts or not all(KEY.match(p) or re.match(r"^[A-Z]\d+-[A-Z]?\d+$", p) for p in parts):
            return m.group(0)  # ordinary bracketed prose, leave it
        return " ".join(f"[{p}]" for p in parts if KEY.match(p) and p in ctx.items)

    del cited  # only what the answer actually cites counts
    text = BRACKET.sub(fix, text)
    order: list[str] = []
    for key in CITE.findall(text):
        if key not in order:
            order.append(key)
    text = re.sub(r"[ \t]+([.,;:)])", r"\1", text)
    text = re.sub(r"\(\s*\)", "", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip(), [_citation(ctx.items[k]) for k in order]


def _citation(item: Item) -> CopilotCitation:
    return CopilotCitation(
        key=item.key, kind=item.kind, label=item.label, theme_id=item.theme_id, interview_id=item.interview_id,
        insight_id=item.insight_id, participant_id=item.participant_id, quote=item.quote, stance=item.stance,
    )


# --- rule-based answers (demo mode and provider failures) ---------------------------


def rule_answer(ctx: Context, question: str) -> tuple[str, list[CopilotCitation]]:
    q = question.lower()
    codes = [c.upper() for c in re.findall(r"\bt\d+\b", q)]
    if "contradict" in q or "disagree" in q or "push back" in q:
        return _cites(ctx, _contradictions(ctx))
    if "compare" in q or " vs" in q or "versus" in q:
        return _cites(ctx, _compare(ctx, codes))
    if "coverage" in q or "missing" in q or "gap" in q or "under-represented" in q:
        return _cites(ctx, _coverage(ctx))
    segment = _segment_in_question(ctx, q)
    if segment:
        return _cites(ctx, _segment_view(ctx, *segment))
    if "strongest" in q or "summar" in q or "best evidence" in q:
        return _cites(ctx, _strongest(ctx, codes))
    if "why" in q or "important" in q or "matter" in q:
        return _cites(ctx, _importance(ctx, codes))
    return _cites(ctx, _search(ctx, q))


def _cites(ctx: Context, text: str) -> tuple[str, list[CopilotCitation]]:
    return _clean_citations(text, [], ctx)


def _theme_for(ctx: Context, codes: list[str]) -> Theme | None:
    for c in codes:
        t = next((t for t in ctx.themes if t.code == c), None)
        if t:
            return t
    return ctx.focus_theme or (ctx.themes[0] if ctx.themes else None)


def _quote_line(key: str, e: ThemeEvidence, ctx: Context) -> str:
    return f'- {e.participant_id} ({_segment_of(ctx, e.participant_id)}): "{e.quote}" [{key}]'


def _keys_for_theme(ctx: Context, t: Theme, stance: str | None = None, verified_first: bool = True):
    rows = [(k, e) for k, e, th in ctx.evidence if th.id == t.id and (stance is None or e.stance == stance)]
    if verified_first:
        rows.sort(key=lambda r: not r[1].quote_verified)
    return rows


def _importance(ctx: Context, codes: list[str]) -> str:
    t = _theme_for(ctx, codes)
    if t is None:
        return "There are no themes to assess yet."
    parts = [
        f"{t.name} [{t.code}] was raised by {t.participant_count} of {t.total_participants} participants "
        f"({round(t.frequency * 100)}%), with severity {t.severity}/5 and clustering confidence {round(t.confidence * 100)}%.",
    ]
    if t.is_outlier:
        parts.append("It comes from a single participant, so treat it as a signal to investigate rather than a pattern.")
    if t.requires_approval:
        parts.append(f"It touches a sensitive topic ({', '.join(t.sensitive_tags).replace('_', ' ')}) and needs explicit sign-off.")
    linked = [(k, i) for k, i in ctx.insights if i.theme_id == t.id]
    for k, i in linked[:1]:
        parts.append(
            f"The linked insight is {i.priority_override or priority_band(i.priority_score)} priority "
            f"(strategic relevance {i.strategic_relevance}/5) [{k}]."
        )
    quotes = _keys_for_theme(ctx, t, EvidenceStance.SUPPORTING)[:2]
    if quotes:
        parts.append("In participants' words:\n" + "\n".join(_quote_line(k, e, ctx) for k, e in quotes))
    contra = _keys_for_theme(ctx, t, EvidenceStance.CONTRADICTING)
    if contra:
        parts.append(f"{len(contra)} quote(s) contradict it, e.g. [{contra[0][0]}].")
    return "\n\n".join(parts)


def _contradictions(ctx: Context) -> str:
    rows = [(k, e, t) for k, e, t in ctx.evidence if e.stance == EvidenceStance.CONTRADICTING]
    if ctx.focus_theme:
        rows = [r for r in rows if r[2].id == ctx.focus_theme.id] or rows
    if not rows:
        return "No contradicting evidence has been recorded for these themes."
    by_theme: dict[str, list] = defaultdict(list)
    for k, e, t in rows:
        by_theme[t.code].append((k, e))
    out = []
    for code, items in by_theme.items():
        t = next(t for t in ctx.themes if t.code == code)
        out.append(f"{t.name} [{code}]:\n" + "\n".join(_quote_line(k, e, ctx) for k, e in items))
    return "Contradicting evidence:\n\n" + "\n\n".join(out)


def _compare(ctx: Context, codes: list[str]) -> str:
    picked = [t for c in codes for t in ctx.themes if t.code == c][:2]
    for t in [ctx.focus_theme, *ctx.themes]:
        if len(picked) >= 2:
            break
        if t and t not in picked:
            picked.append(t)
    if len(picked) < 2:
        return "There are not enough themes to compare."
    a, b = picked
    shared = sorted(set(map(str.lower, a.participant_ids)) & set(map(str.lower, b.participant_ids)))
    lines = [
        f"- {a.name} [{a.code}]: {a.participant_count}/{a.total_participants} participants ({round(a.frequency * 100)}%), severity {a.severity}/5"
        + (", has contradictions" if a.has_contradictions else ""),
        f"- {b.name} [{b.code}]: {b.participant_count}/{b.total_participants} participants ({round(b.frequency * 100)}%), severity {b.severity}/5"
        + (", has contradictions" if b.has_contradictions else ""),
    ]
    overlap = (
        f"{len(shared)} participant(s) raised both ({', '.join(p.upper() for p in shared)})."
        if shared
        else "No participant raised both, so they describe different people's problems."
    )
    return "Side by side (frequency and severity kept separate):\n" + "\n".join(lines) + f"\n\n{overlap}"


def _coverage(ctx: Context) -> str:
    cov = coverage(ctx)
    n = len(ctx.segments)
    out = [f"{n} valid participants."]
    seen = " ".join(v.lower() for c in cov.values() for v in c)
    missing = [s for s in ctx.project.target_segments if s.lower() not in seen]
    if missing:
        out.append(
            f"Target segments not named in any participant's role, company size or plan: {', '.join(missing)}. "
            "Check how company sizes map to them before concluding they are missing."
        )
    for label, key in (("company size", "size"), ("plan", "plan")):
        thin = sorted(v for v, c in cov[key].items() if c == 1)
        if thin:
            out.append(f"Only one participant for {label}: {', '.join(thin)}.")
    roles = cov["role"]
    if roles and all(c == 1 for c in roles.values()):
        out.append(f"All {len(roles)} roles appear once, so no role-level pattern can be confirmed.")
    elif roles:
        out.append("Roles with one participant: " + ", ".join(sorted(v for v, c in roles.items() if c == 1)) + ".")
    singles = [t for t in ctx.themes if t.is_outlier]
    if singles:
        out.append(
            "Themes resting on a single participant: " + ", ".join(f"{t.name} [{t.code}]" for t in singles) + "."
        )
    weak = [t for t in ctx.themes if t.evidence_status == "insufficient"]
    if weak:
        out.append("Themes without a verified quote: " + ", ".join(f"[{t.code}]" for t in weak) + ".")
    if len(out) == 1:
        out.append("Every segment and theme has at least two participants.")
    return "\n\n".join(out)


def _segment_in_question(ctx: Context, q: str) -> tuple[str, str] | None:
    words = set(re.findall(r"[a-z0-9+\-]{3,}", q))
    for pid, seg in ctx.segments.items():
        for kind, value in seg.items():
            tokens = set(re.findall(r"[a-z0-9+\-]{3,}", value.lower()))
            hit = tokens & words
            if hit:
                return kind, sorted(hit)[0]
    return None


def _segment_view(ctx: Context, kind: str, token: str) -> str:
    people = {pid for pid, seg in ctx.segments.items() if token in seg[kind].lower()}
    if not people:
        return f"No participants match “{token}”."
    lines = []
    for t in ctx.themes:
        hits = [(k, e) for k, e, th in ctx.evidence if th.id == t.id and e.participant_id.lower() in people]
        if hits:
            lines.append(f"{t.name} [{t.code}]: {len(hits)} quote(s)\n" + "\n".join(_quote_line(k, e, ctx) for k, e in hits[:2]))
    head = f"{len(people)} participant(s) match “{token}” ({', '.join(sorted(p.upper() for p in people))})."
    return head + ("\n\n" + "\n\n".join(lines[:4]) if lines else "\n\nNone of their quotes are in a theme yet.")


def _strongest(ctx: Context, codes: list[str]) -> str:
    t = _theme_for(ctx, codes) if (codes or ctx.focus_theme) else None
    rows = _keys_for_theme(ctx, t, EvidenceStance.SUPPORTING) if t else [
        (k, e) for k, e, th in ctx.evidence if e.stance == EvidenceStance.SUPPORTING and e.quote_verified
    ]
    rows = [r for r in rows if r[1].quote_verified][:4] or rows[:4]
    if not rows:
        return "There is no verified supporting evidence yet."
    head = f"Strongest verified evidence for {t.name} [{t.code}]:" if t else "Strongest verified quotes across the project:"
    return head + "\n" + "\n".join(_quote_line(k, e, ctx) for k, e in rows)


def _search(ctx: Context, q: str) -> str:
    stop = {"what", "which", "where", "when", "does", "do", "the", "and", "for", "with", "about", "users", "user", "this", "that", "there", "their", "they", "think", "say", "show", "tell"}
    words = [w for w in re.findall(r"[a-z]{3,}", q) if w not in stop]
    hits = [(k, e, t) for k, e, t in ctx.evidence if any(w in e.quote.lower() for w in words)]
    if not hits:
        return (
            "Demo mode can only answer the suggested questions and simple keyword lookups, and no quote matches "
            f"“{' '.join(words) or q}”. Connect an AI provider in Settings for open questions."
        )
    return f"Quotes mentioning {', '.join(words[:3])}:\n" + "\n".join(_quote_line(k, e, ctx) for k, e, _ in hits[:5])
