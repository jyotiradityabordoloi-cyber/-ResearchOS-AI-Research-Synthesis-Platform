import uuid
from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_project_or_404
from app.core.db import get_db
from app.models import HumanReview, Insight, Interview, ResearchProject, Theme, ThemeEvidence, User
from app.models.enums import EvidenceStance, ReviewStatus
from app.schemas import (
    AddEvidenceRequest,
    AuditEntry,
    CommentCreate,
    EvidenceOut,
    InsightCreate,
    InsightEvidence,
    InsightEvidenceItem,
    InsightOut,
    InsightTheme,
    SensitiveFlag,
    InsightUpdate,
    MergeRequest,
    MoveEvidenceRequest,
    ReviewDecision,
    SplitRequest,
    ThemeOut,
    ThemeUpdate,
)
from app.services import review
from app.services.projects import live_filter

router = APIRouter(tags=["review"])
T = TypeVar("T")

_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _call(fn: Callable[[], T]) -> T:
    try:
        return fn()
    except review.ReviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def theme_out(db: Session, theme_id: uuid.UUID) -> ThemeOut:
    theme = db.get(Theme, theme_id, options=[selectinload(Theme.evidence)], populate_existing=True)
    return ThemeOut.model_validate(theme)


def insight_out(insight: Insight, theme_code: str | None = None, project_name: str | None = None) -> InsightOut:
    computed = review.priority_band(insight.priority_score)
    return InsightOut.model_validate(insight).model_copy(
        update={
            "theme_code": theme_code,
            "project_name": project_name,
            "computed_priority": computed,
            "effective_priority": insight.priority_override or computed,
            "is_overridden": insight.priority_override is not None,
        }
    )


def add_context(db: Session, items: list[InsightOut]) -> list[InsightOut]:
    """Theme name, evidence and comment counts for a batch of insights (three queries)."""
    if not items:
        return items
    theme_ids = {i.theme_id for i in items if i.theme_id}
    themes = {}
    counts: dict[tuple, int] = {}
    if theme_ids:
        themes = {
            row.id: row
            for row in db.execute(select(Theme.id, Theme.name, Theme.participant_count).where(Theme.id.in_(theme_ids)))
        }
        for tid, stance, n in db.execute(
            select(ThemeEvidence.theme_id, ThemeEvidence.stance, func.count())
            .where(ThemeEvidence.theme_id.in_(theme_ids))
            .group_by(ThemeEvidence.theme_id, ThemeEvidence.stance)
        ):
            counts[(tid, stance)] = n
    comments = dict(
        db.execute(
            select(HumanReview.entity_id, func.count())
            .where(
                HumanReview.entity_type == "insight",
                HumanReview.action == "review_comment",
                HumanReview.entity_id.in_([i.id for i in items]),
            )
            .group_by(HumanReview.entity_id)
        ).all()
    )
    out = []
    for i in items:
        t = themes.get(i.theme_id)
        out.append(
            i.model_copy(
                update={
                    "theme_name": t.name if t else None,
                    "participant_count": t.participant_count if t else 0,
                    "evidence_count": counts.get((i.theme_id, EvidenceStance.SUPPORTING), 0),
                    "contradicting_count": counts.get((i.theme_id, EvidenceStance.CONTRADICTING), 0),
                    "comment_count": comments.get(i.id, 0),
                }
            )
        )
    return out


def _insight_with_code(db: Session, insight_id: uuid.UUID) -> InsightOut:
    insight = db.get(Insight, insight_id, populate_existing=True)
    code = db.scalar(select(Theme.code).where(Theme.id == insight.theme_id)) if insight.theme_id else None
    return add_context(db, [insight_out(insight, code)])[0]


def sort_insights(items: list[InsightOut]) -> list[InsightOut]:
    return sorted(items, key=lambda i: (_PRIORITY_RANK[i.effective_priority], -i.priority_score))


# --- Themes ------------------------------------------------------------------------


@router.patch("/api/themes/{theme_id}", response_model=ThemeOut)
def edit_theme(
    theme_id: uuid.UUID, payload: ThemeUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ThemeOut:
    """Rename, edit description/implication, or flag strategic importance."""
    changes = payload.model_dump(exclude_unset=True, exclude={"comment"}, exclude_none=True)
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to change.")
    _call(lambda: review.edit_theme(db, theme_id, changes, payload.comment, user))
    return theme_out(db, theme_id)


@router.post("/api/themes/{theme_id}/review", response_model=ThemeOut)
def review_theme(
    theme_id: uuid.UUID, payload: ReviewDecision, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ThemeOut:
    """Approve, reject or reopen an AI theme. Sensitive themes need `acknowledge_sensitive`."""
    _call(lambda: review.review_theme(db, theme_id, payload.decision, payload.comment, payload.acknowledge_sensitive, user))
    return theme_out(db, theme_id)


@router.post("/api/projects/{project_id}/themes/merge", response_model=ThemeOut)
def merge_themes(
    payload: MergeRequest,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ThemeOut:
    target = _call(
        lambda: review.merge_themes(db, project, payload.theme_ids, payload.name, payload.description, payload.comment, user)
    )
    return theme_out(db, target.id)


@router.post("/api/themes/{theme_id}/split", response_model=ThemeOut, status_code=201)
def split_theme(
    theme_id: uuid.UUID, payload: SplitRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> ThemeOut:
    """Move selected evidence out of a theme into a new theme. Returns the new theme."""
    new = _call(
        lambda: review.split_theme(db, theme_id, payload.evidence_ids, payload.name, payload.description, payload.comment, user)
    )
    return theme_out(db, new.id)


@router.post("/api/evidence/{evidence_id}/move", response_model=list[ThemeOut])
def move_evidence(
    evidence_id: uuid.UUID,
    payload: MoveEvidenceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ThemeOut]:
    """Regroup one piece of evidence into another theme. Returns [source, target]."""
    source, target = _call(lambda: review.move_evidence(db, evidence_id, payload.target_theme_id, payload.comment, user))
    return [theme_out(db, source.id), theme_out(db, target.id)]


@router.post("/api/themes/{theme_id}/evidence", response_model=EvidenceOut, status_code=201)
def add_evidence(
    theme_id: uuid.UUID, payload: AddEvidenceRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> EvidenceOut:
    ev = _call(
        lambda: review.add_manual_evidence(
            db, theme_id, payload.interview_id, payload.quote, payload.stance, payload.note, user
        )
    )
    return EvidenceOut.model_validate(ev)


@router.get("/api/themes/{theme_id}/history", response_model=list[AuditEntry])
def theme_history(theme_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AuditEntry]:
    rows = db.scalars(
        select(HumanReview)
        .options(selectinload(HumanReview.user))
        .where(HumanReview.entity_type == "theme", HumanReview.entity_id == theme_id)
        .order_by(HumanReview.created_at.desc())
    )
    return [AuditEntry.model_validate(r).model_copy(update={"actor": r.user.name if r.user else None}) for r in rows]


# --- Insights ----------------------------------------------------------------------


@router.get("/api/insights", response_model=list[InsightOut])
def all_insights(
    project_id: uuid.UUID | None = None,
    status: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
) -> list[InsightOut]:
    """Live insights across all projects (prioritisation view)."""
    stmt = (
        select(Insight, Theme.code, ResearchProject.name)
        .join(ResearchProject, ResearchProject.id == Insight.project_id)
        .outerjoin(Theme, Theme.id == Insight.theme_id)
        .where(live_filter(Insight), Insight.status != ReviewStatus.MERGED)
    )
    if project_id:
        stmt = stmt.where(Insight.project_id == project_id)
    if status:
        stmt = stmt.where(Insight.status == status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Insight.title.ilike(like), Insight.statement.ilike(like), Insight.implication.ilike(like)))
    return sort_insights(add_context(db, [insight_out(i, code, pname) for i, code, pname in db.execute(stmt).all()]))


@router.post("/api/projects/{project_id}/insights", response_model=InsightOut, status_code=201)
def create_insight(
    payload: InsightCreate,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InsightOut:
    insight = _call(lambda: review.create_insight(db, project, payload.model_dump(), user))
    return _insight_with_code(db, insight.id)


@router.patch("/api/insights/{insight_id}", response_model=InsightOut)
def edit_insight(
    insight_id: uuid.UUID, payload: InsightUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> InsightOut:
    """Edit wording, scores, manual priority override (with reason), PM comment or strategic flag.

    Send `priority_override: null` to clear an override.
    """
    changes = payload.model_dump(exclude_unset=True, exclude={"comment"})
    changes = {k: v for k, v in changes.items() if v is not None or k in ("priority_override", "pm_comment")}
    if not changes:
        raise HTTPException(status_code=422, detail="Nothing to change.")
    _call(lambda: review.edit_insight(db, insight_id, changes, payload.comment, user))
    return _insight_with_code(db, insight_id)


@router.post("/api/insights/{insight_id}/review", response_model=InsightOut)
def review_insight(
    insight_id: uuid.UUID, payload: ReviewDecision, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> InsightOut:
    _call(lambda: review.review_insight(db, insight_id, payload.decision, payload.comment, payload.acknowledge_sensitive, user))
    return _insight_with_code(db, insight_id)


@router.get("/api/insights/{insight_id}/evidence", response_model=InsightEvidence)
def insight_evidence(insight_id: uuid.UUID, db: Session = Depends(get_db)) -> InsightEvidence:
    """The original quotes behind an insight (through its theme), with each participant's segment."""
    insight = db.get(Insight, insight_id)
    if insight is None:
        raise HTTPException(status_code=404, detail="Insight not found")
    if not insight.theme_id:
        return InsightEvidence(theme=None, evidence=[])
    theme = db.get(Theme, insight.theme_id)
    rows = db.execute(
        select(ThemeEvidence, Interview.participant_role, Interview.company_size, Interview.plan_tier)
        .join(Interview, Interview.id == ThemeEvidence.interview_id)
        .where(ThemeEvidence.theme_id == theme.id)
        .order_by(
            ThemeEvidence.stance != EvidenceStance.SUPPORTING,
            ThemeEvidence.quote_verified.desc(),
            ThemeEvidence.participant_id,
        )
    ).all()
    return InsightEvidence(
        theme=InsightTheme(
            id=theme.id, code=theme.code, name=theme.name, status=theme.status,
            participant_ids=theme.participant_ids, total_participants=theme.total_participants,
        ),
        evidence=[
            InsightEvidenceItem.model_validate(ev).model_copy(
                update={"participant_role": role, "company_size": size, "plan_tier": plan}
            )
            for ev, role, size, plan in rows
        ],
    )


@router.get("/api/insights/{insight_id}/history", response_model=list[AuditEntry])
def insight_history(insight_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AuditEntry]:
    """Every review action and reviewer comment on this insight, newest first."""
    rows = db.scalars(
        select(HumanReview)
        .options(selectinload(HumanReview.user))
        .where(HumanReview.entity_type == "insight", HumanReview.entity_id == insight_id)
        .order_by(HumanReview.created_at.desc())
    )
    return [AuditEntry.model_validate(r).model_copy(update={"actor": r.user.name if r.user else None}) for r in rows]


@router.post("/api/insights/{insight_id}/comments", response_model=AuditEntry, status_code=201)
def comment_on_insight(
    insight_id: uuid.UUID, payload: CommentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> AuditEntry:
    entry = _call(lambda: review.comment_on_insight(db, insight_id, payload.text, user))
    return AuditEntry.model_validate(entry).model_copy(update={"actor": user.name})


@router.post("/api/insights/{insight_id}/sensitive", response_model=InsightOut)
def flag_sensitive(
    insight_id: uuid.UUID, payload: SensitiveFlag, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> InsightOut:
    """Flag a finding as sensitive by hand; it then needs acknowledged approval."""
    _call(lambda: review.flag_insight_sensitive(db, insight_id, payload.tags, payload.reason, user))
    return _insight_with_code(db, insight_id)
