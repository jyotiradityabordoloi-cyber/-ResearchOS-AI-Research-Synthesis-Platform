"""Modules E & F — human review and prioritisation.

Every action here:
- is performed by a person (never the AI),
- recomputes derived numbers deterministically (participants, frequency, flags),
- writes an entry to the `human_reviews` audit log with before/after values.

Rules
- Approving a finding tagged pricing / churn / competitive switching requires an
  explicit acknowledgement (fallback rule D).
- Changing a theme's evidence (merge, split, move) sends an approved theme back to
  `proposed`, because what was approved is no longer what is shown.
- A manual priority override never changes the computed score or the frequency; both
  stay visible next to the override (frequency and impact are kept separate).
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai import lexicon
from app.models import Insight, Interview, PainPoint, ResearchProject, Theme, ThemeEvidence, User
from app.models.enums import EvidenceStance, Origin, ReviewStatus
from app.services import audit
from app.services.pipeline import locate_field, verify_quote, InterviewRecord

Decision = Literal["approve", "reject", "reopen"]
PriorityBand = Literal["high", "medium", "low"]

HIGH, MEDIUM = 0.55, 0.40


class ReviewError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Derived values
# ---------------------------------------------------------------------------


def priority_band(score: float) -> PriorityBand:
    return "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"


def priority_score(frequency: float, severity: int, strategic: int, confidence: float) -> float:
    return round(
        0.35 * frequency + 0.25 * (severity - 1) / 4 + 0.25 * (strategic - 1) / 4 + 0.15 * confidence, 3
    )


def _theme_snapshot(t: Theme) -> dict[str, Any]:
    return {
        "name": t.name,
        "status": t.status,
        "participant_ids": list(t.participant_ids),
        "frequency": t.frequency,
    }


def recompute_theme(db: Session, theme: Theme) -> None:
    """Recalculate participant counts, frequency and flags from the theme's evidence."""
    db.flush()
    db.refresh(theme, attribute_names=["evidence"])
    supporting = [e for e in theme.evidence if e.stance == EvidenceStance.SUPPORTING]
    participants: dict[str, str] = {}
    for e in supporting:
        participants.setdefault(e.participant_id.strip().lower(), e.participant_id)
    theme.participant_ids = sorted(participants.values(), key=str.lower)
    theme.participant_count = len(participants)
    theme.frequency = (
        round(theme.participant_count / theme.total_participants, 4) if theme.total_participants else 0.0
    )
    theme.is_outlier = theme.participant_count == 1
    theme.has_contradictions = any(e.stance == EvidenceStance.CONTRADICTING for e in theme.evidence)
    theme.evidence_status = "sufficient" if any(e.quote_verified for e in supporting) else "insufficient"

    pp_ids = [e.pain_point_id for e in supporting if e.pain_point_id]
    tags: set[str] = set()
    if pp_ids:
        for row in db.scalars(select(PainPoint.sensitive_tags).where(PainPoint.id.in_(pp_ids))):
            tags |= set(row or [])
    tags |= set(
        lexicon.sensitive_tags(" ".join([theme.name, theme.description] + [e.quote for e in theme.evidence]))
    )
    theme.sensitive_tags = sorted(tags)
    theme.requires_approval = bool(tags)

    for insight in db.scalars(select(Insight).where(Insight.theme_id == theme.id)):
        insight.frequency = theme.frequency
        insight.is_outlier = theme.is_outlier
        insight.sensitive_tags = sorted(set(insight.sensitive_tags or []) | tags)
        insight.requires_approval = bool(insight.sensitive_tags)
        insight.priority_score = priority_score(
            insight.frequency, insight.severity, insight.strategic_relevance, insight.confidence
        )


def _reset_approval(db: Session, theme: Theme, user: User, reason: str) -> None:
    if theme.status == ReviewStatus.APPROVED:
        theme.status = ReviewStatus.PROPOSED
        audit.record(
            db,
            project_id=theme.project_id,
            entity_type="theme",
            entity_id=theme.id,
            action="approval_reset",
            before={"status": "approved"},
            after={"status": "proposed"},
            comment=reason,
            user=user,
        )


def _live_theme(db: Session, theme_id: uuid.UUID) -> Theme:
    theme = db.get(Theme, theme_id, options=[selectinload(Theme.evidence)])
    if theme is None:
        raise ReviewError(404, "Theme not found")
    if theme.status == ReviewStatus.MERGED:
        raise ReviewError(409, "This theme was merged into another theme.")
    project = db.get(ResearchProject, theme.project_id)
    if theme.run_id is not None and theme.run_id != project.active_run_id:
        raise ReviewError(409, "This theme belongs to an older synthesis run and can no longer be edited.")
    return theme


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------


def edit_theme(db: Session, theme_id: uuid.UUID, changes: dict[str, Any], comment: str | None, user: User) -> Theme:
    theme = _live_theme(db, theme_id)
    before = {k: getattr(theme, k) for k in changes}
    for k, v in changes.items():
        setattr(theme, k, v)
    after = {k: getattr(theme, k) for k in changes}
    if before == after:
        return theme
    if any(k in changes for k in ("name", "description", "implication")):
        theme.human_edited = True
    if "implication" in changes:
        for insight in db.scalars(select(Insight).where(Insight.theme_id == theme.id)):
            insight.implication = theme.implication
    if "name" in changes:
        for insight in db.scalars(select(Insight).where(Insight.theme_id == theme.id, Insight.origin == Origin.AI)):
            insight.title = theme.name[:300]
    recompute_theme(db, theme)  # wording can change sensitivity
    action = "rename" if set(changes) == {"name"} else "flag_strategic" if set(changes) == {"strategic_flag"} else "edit"
    audit.record(
        db, project_id=theme.project_id, entity_type="theme", entity_id=theme.id,
        action=action, before=before, after=after, comment=comment, user=user,
    )
    db.commit()
    return theme


def _check_sensitive(requires: bool, tags: list[str], acknowledge: bool, comment: str | None) -> None:
    if requires and not acknowledge:
        raise ReviewError(
            422,
            "This finding involves " + ", ".join(t.replace("_", " ") for t in tags)
            + ". Approving it requires explicit acknowledgement (acknowledge_sensitive=true).",
        )
    if requires and not (comment and comment.strip()):
        raise ReviewError(422, "Add a comment explaining why this sensitive finding is approved.")


_DECISION_STATUS = {
    "approve": ReviewStatus.APPROVED,
    "reject": ReviewStatus.REJECTED,
    "reopen": ReviewStatus.PROPOSED,
}


def review_theme(
    db: Session, theme_id: uuid.UUID, decision: Decision, comment: str | None, acknowledge: bool, user: User
) -> Theme:
    theme = _live_theme(db, theme_id)
    if decision == "approve":
        _check_sensitive(theme.requires_approval, theme.sensitive_tags, acknowledge, comment)
    before = theme.status
    theme.status = _DECISION_STATUS[decision]
    # The theme's AI insight follows the theme decision; PM-written insights are reviewed separately.
    for insight in db.scalars(select(Insight).where(Insight.theme_id == theme.id, Insight.origin == Origin.AI)):
        insight.status = theme.status
    audit.record(
        db, project_id=theme.project_id, entity_type="theme", entity_id=theme.id, action=decision,
        before={"status": before}, after={"status": theme.status, "sensitive_tags": theme.sensitive_tags},
        comment=comment, user=user,
    )
    db.commit()
    return theme


def merge_themes(
    db: Session, project: ResearchProject, theme_ids: list[uuid.UUID], name: str | None,
    description: str | None, comment: str | None, user: User,
) -> Theme:
    if len(set(theme_ids)) < 2:
        raise ReviewError(422, "Select at least two themes to merge.")
    themes = [_live_theme(db, tid) for tid in dict.fromkeys(theme_ids)]
    if any(t.project_id != project.id for t in themes):
        raise ReviewError(422, "Themes must belong to this project.")
    target, sources = themes[0], themes[1:]
    before = {"target": _theme_snapshot(target), "sources": [_theme_snapshot(s) for s in sources]}

    for src in sources:
        for e in list(src.evidence):
            duplicate = any(
                x.interview_id == e.interview_id and x.quote == e.quote and x.stance == e.stance for x in target.evidence
            )
            if duplicate:
                db.delete(e)
            else:
                e.theme_id = target.id
        src.status = ReviewStatus.MERGED
        src.merged_into_id = target.id
        for insight in db.scalars(select(Insight).where(Insight.theme_id == src.id)):
            insight.status = ReviewStatus.MERGED
        recompute_theme(db, src)
    if name:
        target.name = name.strip()
        for insight in db.scalars(select(Insight).where(Insight.theme_id == target.id, Insight.origin == Origin.AI)):
            insight.title = target.name[:300]
    if description:
        target.description = description.strip()
    target.human_edited = True
    target.confidence = round(min([t.confidence for t in themes]), 2)
    recompute_theme(db, target)
    _reset_approval(db, target, user, "Evidence changed by merge.")
    audit.record(
        db, project_id=project.id, entity_type="theme", entity_id=target.id, action="merge",
        before=before, after=_theme_snapshot(target), comment=comment, user=user,
    )
    db.commit()
    return target


def split_theme(
    db: Session, theme_id: uuid.UUID, evidence_ids: list[uuid.UUID], name: str, description: str,
    comment: str | None, user: User,
) -> Theme:
    source = _live_theme(db, theme_id)
    moving = [e for e in source.evidence if e.id in set(evidence_ids)]
    if not moving or len(moving) != len(set(evidence_ids)):
        raise ReviewError(422, "Choose evidence that belongs to this theme.")
    remaining = [e for e in source.evidence if e.id not in set(evidence_ids) and e.stance == EvidenceStance.SUPPORTING]
    if not remaining:
        raise ReviewError(422, "Leave at least one supporting item in the original theme.")
    if not any(e.stance == EvidenceStance.SUPPORTING for e in moving):
        raise ReviewError(422, "The new theme needs at least one supporting item.")

    codes = db.scalars(select(Theme.code).where(Theme.project_id == source.project_id, Theme.run_id == source.run_id))
    next_n = 1 + max((int(c[1:]) for c in codes if c[1:].isdigit()), default=0)
    new = Theme(
        project_id=source.project_id, run_id=source.run_id, code=f"T{next_n}", name=name.strip(),
        description=description.strip(), implication="", total_participants=source.total_participants,
        confidence=source.confidence, severity=source.severity, status=ReviewStatus.PROPOSED,
        origin=Origin.MANUAL, human_edited=True, split_from_id=source.id, embedding=source.embedding,
    )
    db.add(new)
    db.flush()
    for e in moving:
        e.theme_id = new.id
    recompute_theme(db, source)
    recompute_theme(db, new)
    source_insight = db.scalar(select(Insight).where(Insight.theme_id == source.id))
    db.add(
        Insight(
            project_id=new.project_id, run_id=new.run_id, theme_id=new.id, title=new.name[:300],
            statement=new.description, implication="", frequency=new.frequency, severity=new.severity,
            strategic_relevance=source_insight.strategic_relevance if source_insight else 3,
            confidence=new.confidence,
            priority_score=priority_score(
                new.frequency, new.severity, source_insight.strategic_relevance if source_insight else 3, new.confidence
            ),
            is_outlier=new.is_outlier, sensitive_tags=new.sensitive_tags, requires_approval=new.requires_approval,
            status=ReviewStatus.PROPOSED, origin=Origin.MANUAL,
        )
    )
    _reset_approval(db, source, user, "Evidence changed by split.")
    audit.record(
        db, project_id=source.project_id, entity_type="theme", entity_id=source.id, action="split",
        before={"source": _theme_snapshot(source)},
        after={"new_theme": _theme_snapshot(new), "moved_evidence": [str(e.id) for e in moving]},
        comment=comment, user=user,
    )
    db.commit()
    return new


def move_evidence(
    db: Session, evidence_id: uuid.UUID, target_theme_id: uuid.UUID, comment: str | None, user: User
) -> tuple[Theme, Theme]:
    ev = db.get(ThemeEvidence, evidence_id)
    if ev is None:
        raise ReviewError(404, "Evidence not found")
    source = _live_theme(db, ev.theme_id)
    target = _live_theme(db, target_theme_id)
    if source.id == target.id:
        raise ReviewError(422, "Evidence is already in this theme.")
    if source.project_id != target.project_id:
        raise ReviewError(422, "Themes must belong to the same project.")
    if ev.stance == EvidenceStance.SUPPORTING and sum(
        1 for e in source.evidence if e.stance == EvidenceStance.SUPPORTING
    ) == 1:
        raise ReviewError(422, "This is the theme's last supporting item. Merge or reject the theme instead.")
    ev.theme_id = target.id
    recompute_theme(db, source)
    recompute_theme(db, target)
    for t in (source, target):
        _reset_approval(db, t, user, "Evidence regrouped.")
    audit.record(
        db, project_id=source.project_id, entity_type="evidence", entity_id=ev.id, action="move_evidence",
        before={"theme": source.code, "participant_id": ev.participant_id},
        after={"theme": target.code}, comment=comment, user=user,
    )
    db.commit()
    return source, target


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------


def _live_insight(db: Session, insight_id: uuid.UUID) -> Insight:
    insight = db.get(Insight, insight_id)
    if insight is None:
        raise ReviewError(404, "Insight not found")
    if insight.status == ReviewStatus.MERGED:
        raise ReviewError(409, "This insight belongs to a merged theme.")
    return insight


def edit_insight(db: Session, insight_id: uuid.UUID, changes: dict[str, Any], comment: str | None, user: User) -> Insight:
    insight = _live_insight(db, insight_id)
    if "priority_override" in changes and changes["priority_override"] and not (
        changes.get("override_reason") or insight.override_reason
    ):
        raise ReviewError(422, "Give a reason when overriding the priority.")
    if changes.get("priority_override", "unset") is None:
        changes.setdefault("override_reason", None)
    before = {k: getattr(insight, k) for k in changes}
    for k, v in changes.items():
        setattr(insight, k, v)
    after = {k: getattr(insight, k) for k in changes}
    if before == after:
        return insight
    insight.priority_score = priority_score(
        insight.frequency, insight.severity, insight.strategic_relevance, insight.confidence
    )
    text_changed = any(k in changes for k in ("title", "statement", "implication"))
    if text_changed:
        tags = set(lexicon.sensitive_tags(" ".join([insight.title, insight.statement, insight.implication])))
        insight.sensitive_tags = sorted(set(insight.sensitive_tags or []) | tags)
        insight.requires_approval = bool(insight.sensitive_tags)
    keys = set(changes) - {"override_reason"}
    action = (
        "override_priority" if keys == {"priority_override"}
        else "comment" if keys == {"pm_comment"}
        else "flag_strategic" if keys == {"strategic_flag"}
        else "edit"
    )
    audit.record(
        db, project_id=insight.project_id, entity_type="insight", entity_id=insight.id, action=action,
        before=before, after=after, comment=comment, user=user,
    )
    db.commit()
    return insight


def review_insight(
    db: Session, insight_id: uuid.UUID, decision: Decision, comment: str | None, acknowledge: bool, user: User
) -> Insight:
    insight = _live_insight(db, insight_id)
    if decision == "approve":
        _check_sensitive(insight.requires_approval, insight.sensitive_tags, acknowledge, comment)
    before = insight.status
    insight.status = _DECISION_STATUS[decision]
    audit.record(
        db, project_id=insight.project_id, entity_type="insight", entity_id=insight.id, action=decision,
        before={"status": before}, after={"status": insight.status}, comment=comment, user=user,
    )
    db.commit()
    return insight


def create_insight(db: Session, project: ResearchProject, data: dict[str, Any], user: User) -> Insight:
    theme = None
    if data.get("theme_id"):
        theme = _live_theme(db, data["theme_id"])
        if theme.project_id != project.id:
            raise ReviewError(422, "Theme must belong to this project.")
    text = " ".join([data["title"], data.get("statement", ""), data.get("implication", "")])
    tags = sorted(set(lexicon.sensitive_tags(text)) | set(theme.sensitive_tags if theme else []))
    frequency = theme.frequency if theme else 0.0
    confidence = theme.confidence if theme else 0.0
    insight = Insight(
        project_id=project.id,
        run_id=theme.run_id if theme else None,
        theme_id=theme.id if theme else None,
        title=data["title"].strip(),
        statement=data.get("statement", "").strip(),
        implication=data.get("implication", "").strip(),
        frequency=frequency,
        severity=data["severity"],
        strategic_relevance=data["strategic_relevance"],
        confidence=confidence,
        priority_score=priority_score(frequency, data["severity"], data["strategic_relevance"], confidence),
        is_outlier=theme.is_outlier if theme else False,
        sensitive_tags=tags,
        requires_approval=bool(tags),
        strategic_flag=bool(data.get("strategic_flag")),
        pm_comment=data.get("pm_comment"),
        # A PM's own insight is approved on creation, unless it touches a sensitive topic.
        status=ReviewStatus.PROPOSED if tags else ReviewStatus.APPROVED,
        origin=Origin.MANUAL,
    )
    db.add(insight)
    db.flush()
    audit.record(
        db, project_id=project.id, entity_type="insight", entity_id=insight.id, action="create",
        after={"title": insight.title, "theme": theme.code if theme else None, "sensitive_tags": tags}, user=user,
    )
    db.commit()
    return insight


def add_manual_evidence(
    db: Session, theme_id: uuid.UUID, interview_id: uuid.UUID, quote: str, stance: str, note: str,
    user: User,
) -> ThemeEvidence:
    """Attach a quote a PM found themselves. It is verified against the interview like AI quotes."""
    theme = _live_theme(db, theme_id)
    iv = db.get(Interview, interview_id)
    if iv is None or iv.project_id != theme.project_id:
        raise ReviewError(422, "Interview must belong to this project.")
    record = InterviewRecord(
        id=iv.id, participant_id=iv.participant_id, participant_role=iv.participant_role,
        company_size=iv.company_size, plan_tier=iv.plan_tier, pain=iv.pain, behavior=iv.behavior,
        verbatim_quote=iv.verbatim_quote, raw_content=iv.raw_content,
    )
    cleaned, ok = verify_quote(quote, record)
    if not ok:
        raise ReviewError(422, "That quote does not appear word-for-word in the interview notes.")
    ev = ThemeEvidence(
        theme_id=theme.id, interview_id=iv.id, participant_id=iv.participant_id, quote=cleaned,
        quote_verified=True, source_field=locate_field(cleaned, record), stance=EvidenceStance(stance), note=note,
    )
    db.add(ev)
    recompute_theme(db, theme)
    _reset_approval(db, theme, user, "Evidence added.")
    audit.record(
        db, project_id=theme.project_id, entity_type="evidence", entity_id=None, action="add_evidence",
        after={"theme": theme.code, "participant_id": iv.participant_id, "stance": stance, "quote": cleaned},
        user=user,
    )
    db.commit()
    return ev
