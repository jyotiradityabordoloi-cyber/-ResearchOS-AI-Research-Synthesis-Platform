"""Theme exploration canvas: the operations behind drag-and-drop regrouping.

Every operation here has an exact inverse so the canvas can offer undo/redo while
persisting each step on the server:

    attach observation (new evidence)  <->  detach evidence
    attach observation (moved)         <->  move evidence back   (review.move_evidence)
    set evidence stance                <->  set it back
    create theme                       <->  delete theme (PM-created themes only)
    split theme                        <->  delete the new theme (evidence returns to its source)
    merge themes                       <->  unmerge (restores sources, evidence and wording)

Like the rest of human review, every change recomputes participant counts and
frequency in Python, resets an approval the change invalidates, and is written to the
audit log.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import HumanReview, Insight, Interview, PainPoint, ResearchProject, Theme, ThemeEvidence, User
from app.models.enums import EvidenceStance, Origin, ReviewStatus, ValidationStatus
from app.schemas import ObservationOut
from app.services import audit
from app.services.projects import live_filter
from app.services.review import (
    ReviewError,
    _live_theme,
    _reset_approval,
    _theme_snapshot,
    evidence_snapshot,
    move_evidence,
    priority_score,
    recompute_theme,
)

NEUTRAL_CONFIDENCE = 0.5  # a PM-created grouping has no AI clustering confidence


def _supporting(theme: Theme) -> int:
    return sum(1 for e in theme.evidence if e.stance == EvidenceStance.SUPPORTING)


def list_observations(db: Session, project: ResearchProject) -> list[ObservationOut]:
    """Pain points the project's active run extracted, with the interview's segment."""
    if not project.active_run_id:
        return []
    rows = db.execute(
        select(PainPoint, Interview.participant_role, Interview.company_size, Interview.plan_tier)
        .join(Interview, Interview.id == PainPoint.interview_id)
        .where(PainPoint.project_id == project.id, PainPoint.run_id == project.active_run_id)
        .order_by(func.lower(PainPoint.participant_id), PainPoint.created_at)
    ).all()
    return [
        ObservationOut(
            id=pp.id,
            interview_id=pp.interview_id,
            participant_id=pp.participant_id,
            participant_role=role,
            company_size=size,
            plan_tier=plan,
            text=pp.text,
            quote=pp.quote,
            quote_verified=pp.quote_verified,
            severity=pp.severity,
            sensitive_tags=pp.sensitive_tags,
            duplicate_count=pp.duplicate_count,
        )
        for pp, role, size, plan in rows
    ]


def _live_evidence_for(db: Session, pain_point: PainPoint, project: ResearchProject) -> ThemeEvidence | None:
    return db.scalars(
        select(ThemeEvidence)
        .join(Theme, Theme.id == ThemeEvidence.theme_id)
        .where(
            ThemeEvidence.pain_point_id == pain_point.id,
            live_filter(Theme, project),
            Theme.status != ReviewStatus.MERGED,
        )
    ).first()


def attach_observation(
    db: Session, theme_id: uuid.UUID, pain_point_id: uuid.UUID, stance: str, user: User
) -> tuple[ThemeEvidence, uuid.UUID | None]:
    """Put an observation into a theme. If it already sits in another theme it is moved.

    Returns the evidence row and, when it was moved, the theme it came from.
    """
    theme = _live_theme(db, theme_id)
    project = db.get(ResearchProject, theme.project_id)
    pp = db.get(PainPoint, pain_point_id)
    if pp is None or pp.project_id != theme.project_id or pp.run_id != project.active_run_id:
        raise ReviewError(422, "That observation does not belong to this project's current synthesis.")

    existing = _live_evidence_for(db, pp, project)
    if existing is not None:
        if existing.theme_id == theme.id:
            raise ReviewError(422, "This observation is already in that theme.")
        source_id = existing.theme_id
        move_evidence(db, existing.id, theme.id, None, user)
        return db.get(ThemeEvidence, existing.id), source_id

    has_quote = bool(pp.quote and pp.quote.strip())
    ev = ThemeEvidence(
        theme_id=theme.id,
        interview_id=pp.interview_id,
        pain_point_id=pp.id,
        participant_id=pp.participant_id,
        # Without a verified quote the observation text is shown, clearly marked unverified.
        quote=pp.quote if has_quote else pp.text,
        quote_verified=pp.quote_verified and has_quote,
        source_field=pp.source_field,
        stance=EvidenceStance(stance),
        note="" if has_quote else "Observation summary; no verbatim quote was extracted.",
    )
    db.add(ev)
    recompute_theme(db, theme)
    _reset_approval(db, theme, user, "Evidence added.")
    audit.record(
        db, project_id=theme.project_id, entity_type="evidence", entity_id=None, action="add_evidence",
        after={"theme": theme.code, "participant_id": pp.participant_id, "stance": stance, "observation": pp.text[:200]},
        user=user,
    )
    db.commit()
    return ev, None


def detach_evidence(db: Session, evidence_id: uuid.UUID, user: User) -> dict[str, Any]:
    """Take evidence out of its theme (the observation becomes unassigned). Returns its snapshot."""
    ev = db.get(ThemeEvidence, evidence_id)
    if ev is None:
        raise ReviewError(404, "Evidence not found")
    theme = _live_theme(db, ev.theme_id)
    if theme.origin == Origin.AI and ev.stance == EvidenceStance.SUPPORTING and _supporting(theme) == 1:
        raise ReviewError(422, "This is the theme's last supporting item. Merge or reject the theme instead.")
    snapshot = evidence_snapshot(ev)
    db.delete(ev)
    recompute_theme(db, theme)
    _reset_approval(db, theme, user, "Evidence removed.")
    audit.record(
        db, project_id=theme.project_id, entity_type="evidence", entity_id=evidence_id, action="remove_evidence",
        before={**snapshot, "theme": theme.code}, user=user,
    )
    db.commit()
    return snapshot


def set_evidence_stance(db: Session, evidence_id: uuid.UUID, stance: str, user: User) -> Theme:
    ev = db.get(ThemeEvidence, evidence_id)
    if ev is None:
        raise ReviewError(404, "Evidence not found")
    theme = _live_theme(db, ev.theme_id)
    if ev.stance == stance:
        return theme
    if ev.stance == EvidenceStance.SUPPORTING and _supporting(theme) == 1:
        raise ReviewError(422, "A theme needs at least one supporting item.")
    before = ev.stance
    ev.stance = EvidenceStance(stance)
    recompute_theme(db, theme)
    _reset_approval(db, theme, user, "Evidence stance changed.")
    audit.record(
        db, project_id=theme.project_id, entity_type="evidence", entity_id=ev.id, action="set_stance",
        before={"stance": before, "theme": theme.code, "participant_id": ev.participant_id},
        after={"stance": stance}, user=user,
    )
    db.commit()
    return theme


def _next_code(db: Session, project: ResearchProject) -> str:
    codes = db.scalars(select(Theme.code).where(Theme.project_id == project.id))
    return f"T{1 + max((int(c[1:]) for c in codes if c[1:].isdigit()), default=0)}"


def _total_participants(db: Session, project: ResearchProject) -> int:
    known = db.scalar(
        select(Theme.total_participants).where(Theme.project_id == project.id, Theme.run_id == project.active_run_id).limit(1)
    )
    if known:
        return known
    return (
        db.scalar(
            select(func.count(func.distinct(func.lower(Interview.participant_id)))).where(
                Interview.project_id == project.id, Interview.validation_status == ValidationStatus.VALID
            )
        )
        or 0
    )


def create_theme(db: Session, project: ResearchProject, name: str, description: str, user: User) -> Theme:
    """An empty PM-created theme in the active run, with its own (manual) insight."""
    if not project.active_run_id:
        raise ReviewError(409, "Run synthesis first; themes group the observations it extracts.")
    theme = Theme(
        project_id=project.id, run_id=project.active_run_id, code=_next_code(db, project), name=name.strip(),
        description=description.strip(), implication="", total_participants=_total_participants(db, project),
        confidence=NEUTRAL_CONFIDENCE, severity=3, status=ReviewStatus.PROPOSED, origin=Origin.MANUAL,
        human_edited=True, evidence_status="insufficient",
    )
    db.add(theme)
    db.flush()
    db.add(
        Insight(
            project_id=project.id, run_id=theme.run_id, theme_id=theme.id, title=theme.name[:300],
            statement=theme.description, implication="", frequency=0.0, severity=3, strategic_relevance=3,
            confidence=NEUTRAL_CONFIDENCE, priority_score=priority_score(0.0, 3, 3, NEUTRAL_CONFIDENCE),
            status=ReviewStatus.PROPOSED, origin=Origin.MANUAL,
        )
    )
    audit.record(
        db, project_id=project.id, entity_type="theme", entity_id=theme.id, action="create",
        after=_theme_snapshot(theme), user=user,
    )
    db.commit()
    return theme


def delete_theme(db: Session, theme_id: uuid.UUID, user: User) -> uuid.UUID | None:
    """Delete a PM-created theme. Evidence returns to the theme it was split from, if any;
    otherwise its observations become unassigned. Returns the theme the evidence went to."""
    theme = _live_theme(db, theme_id)
    if theme.origin != Origin.MANUAL:
        raise ReviewError(422, "Only PM-created themes can be deleted. Reject an AI theme instead.")
    if db.scalar(select(func.count()).select_from(Theme).where(Theme.merged_into_id == theme.id)):
        raise ReviewError(409, "Other themes were merged into this one. Undo that merge first.")

    project = db.get(ResearchProject, theme.project_id)
    parent = db.get(Theme, theme.split_from_id) if theme.split_from_id else None
    if parent is not None and (
        parent.status == ReviewStatus.MERGED or (parent.run_id is not None and parent.run_id != project.active_run_id)
    ):
        parent = None

    snapshot = _theme_snapshot(theme)
    for e in list(theme.evidence):
        if parent is not None:
            # Reassign through the relationship: the theme's delete-orphan cascade would
            # otherwise delete evidence still listed in `theme.evidence`.
            e.theme = parent
        else:
            db.delete(e)
    for insight in db.scalars(select(Insight).where(Insight.theme_id == theme.id)):
        db.delete(insight)
    db.flush()
    db.delete(theme)
    if parent is not None:
        recompute_theme(db, parent)
        _reset_approval(db, parent, user, "Evidence returned from a deleted theme.")
    audit.record(
        db, project_id=project.id, entity_type="theme", entity_id=theme_id, action="delete",
        before={**snapshot, "code": theme.code}, after={"evidence_returned_to": parent.code if parent else None},
        user=user,
    )
    db.commit()
    return parent.id if parent else None


def unmerge_theme(db: Session, target_id: uuid.UUID, user: User) -> list[uuid.UUID]:
    """Reverse the most recent merge into `target_id`. Returns the restored source theme ids."""
    target = _live_theme(db, target_id)
    entry = db.scalars(
        select(HumanReview)
        .where(
            and_(HumanReview.entity_type == "theme", HumanReview.entity_id == target.id, HumanReview.action == "merge")
        )
        .order_by(HumanReview.created_at.desc())
    ).first()
    undo = (entry.before or {}).get("undo") if entry else None
    if not undo:
        raise ReviewError(409, "There is no merge to undo on this theme.")
    sources = [db.get(Theme, uuid.UUID(s["id"])) for s in undo["sources"]]
    if any(s is None or s.status != ReviewStatus.MERGED or s.merged_into_id != target.id for s in sources):
        raise ReviewError(409, "That merge was already undone or the themes changed since.")

    for m in undo["moved"]:
        ev = db.get(ThemeEvidence, uuid.UUID(m["evidence_id"]))
        if ev is not None and ev.theme_id == target.id:
            ev.theme_id = uuid.UUID(m["from"])
    for d in undo["duplicates"]:
        db.add(
            ThemeEvidence(
                theme_id=uuid.UUID(d["theme_id"]), interview_id=uuid.UUID(d["interview_id"]),
                pain_point_id=uuid.UUID(d["pain_point_id"]) if d["pain_point_id"] else None,
                participant_id=d["participant_id"], quote=d["quote"], quote_verified=d["quote_verified"],
                source_field=d["source_field"], stance=d["stance"], note=d["note"],
            )
        )
    for saved, src in zip(undo["sources"], sources, strict=True):
        src.status = saved["status"]
        src.merged_into_id = None
        for insight_id, status in saved["insights"].items():
            insight = db.get(Insight, uuid.UUID(insight_id))
            if insight is not None:
                insight.status = status

    t = undo["target"]
    if target.name != t["name"]:
        for insight in db.scalars(select(Insight).where(Insight.theme_id == target.id, Insight.origin == Origin.AI)):
            insight.title = t["name"][:300]
    target.name, target.description = t["name"], t["description"]
    target.confidence, target.human_edited = t["confidence"], t["human_edited"]
    db.flush()
    for theme in (target, *sources):
        recompute_theme(db, theme)
    target.status = t["status"]  # the evidence is exactly as approved again
    audit.record(
        db, project_id=target.project_id, entity_type="theme", entity_id=target.id, action="unmerge",
        before=_theme_snapshot(target), after={"restored": [s.code for s in sources]}, user=user,
    )
    db.commit()
    return [s.id for s in sources]
