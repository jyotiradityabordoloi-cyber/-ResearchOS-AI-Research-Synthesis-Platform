"""Project aggregates computed from the database (never hardcoded)."""

import uuid
from collections import defaultdict

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import HumanReview, Insight, Interview, ResearchProject, ResearchReport, Theme
from app.models.enums import ReviewStatus, ValidationStatus
from app.schemas import ProjectOut

_LIVE_EXCLUDED = (ReviewStatus.REJECTED, ReviewStatus.MERGED)


def live_filter(model, project: ResearchProject | None = None):
    """Rows that belong to a project's active synthesis run, plus manual rows (run_id NULL)."""
    if project is not None:
        return and_(
            model.project_id == project.id,
            or_(model.run_id == project.active_run_id, model.run_id.is_(None)),
        )
    return or_(
        model.run_id == ResearchProject.active_run_id,
        model.run_id.is_(None),
    )


def _count_by_project(db: Session, stmt) -> dict[uuid.UUID, int]:
    return {pid: n for pid, n in db.execute(stmt).all()}


def project_aggregates(db: Session, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    if not project_ids:
        return {}
    agg: dict[uuid.UUID, dict] = defaultdict(dict)

    rows = db.execute(
        select(
            Interview.project_id,
            Interview.validation_status,
            func.count(),
        )
        .where(Interview.project_id.in_(project_ids))
        .group_by(Interview.project_id, Interview.validation_status)
    ).all()
    for pid, status, n in rows:
        agg[pid].setdefault("by_status", {})[status] = n

    participants = _count_by_project(
        db,
        select(Interview.project_id, func.count(func.distinct(func.lower(Interview.participant_id))))
        .where(
            Interview.project_id.in_(project_ids),
            Interview.validation_status == ValidationStatus.VALID,
        )
        .group_by(Interview.project_id),
    )

    live_theme = and_(
        Theme.project_id == ResearchProject.id,
        live_filter(Theme),
        Theme.status.notin_(_LIVE_EXCLUDED),
    )
    themes = _count_by_project(
        db,
        select(Theme.project_id, func.count())
        .join(ResearchProject, live_theme)
        .where(Theme.project_id.in_(project_ids))
        .group_by(Theme.project_id),
    )
    pending_themes = _count_by_project(
        db,
        select(Theme.project_id, func.count())
        .join(ResearchProject, live_theme)
        .where(Theme.project_id.in_(project_ids), Theme.status == ReviewStatus.PROPOSED)
        .group_by(Theme.project_id),
    )
    pending_insights = _count_by_project(
        db,
        select(Insight.project_id, func.count())
        .join(
            ResearchProject,
            and_(Insight.project_id == ResearchProject.id, live_filter(Insight)),
        )
        .where(Insight.project_id.in_(project_ids), Insight.status == ReviewStatus.PROPOSED)
        .group_by(Insight.project_id),
    )

    review = _review_progress(db, project_ids)
    reports = _count_by_project(
        db,
        select(ResearchReport.project_id, func.count())
        .where(ResearchReport.project_id.in_(project_ids))
        .group_by(ResearchReport.project_id),
    )
    last_audit = dict(
        db.execute(
            select(HumanReview.project_id, func.max(HumanReview.created_at))
            .where(HumanReview.project_id.in_(project_ids))
            .group_by(HumanReview.project_id)
        ).all()
    )

    for pid in project_ids:
        by_status = agg[pid].get("by_status", {})
        agg[pid] = {
            "interview_count": sum(by_status.values()),
            "valid_interview_count": by_status.get(ValidationStatus.VALID, 0),
            "invalid_interview_count": by_status.get(ValidationStatus.INVALID, 0),
            "participant_count": participants.get(pid, 0),
            "theme_count": themes.get(pid, 0),
            "pending_review_count": pending_themes.get(pid, 0) + pending_insights.get(pid, 0),
            "review_total": review[pid][0],
            "review_done": review[pid][1],
            "report_count": reports.get(pid, 0),
            "last_audit_at": last_audit.get(pid),
        }
    return agg


_REVIEWABLE = (ReviewStatus.PROPOSED, ReviewStatus.APPROVED, ReviewStatus.REJECTED)


def _review_progress(db: Session, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[int]]:
    """[reviewable, decided] counts over each project's live themes and insights."""
    totals: dict[uuid.UUID, list[int]] = defaultdict(lambda: [0, 0])
    for model in (Theme, Insight):
        join = and_(model.project_id == ResearchProject.id, live_filter(model))
        for pid, status, n in db.execute(
            select(model.project_id, model.status, func.count())
            .join(ResearchProject, join)
            .where(model.project_id.in_(project_ids), model.status.in_(_REVIEWABLE))
            .group_by(model.project_id, model.status)
        ).all():
            totals[pid][0] += n
            if status != ReviewStatus.PROPOSED:
                totals[pid][1] += n
    return totals


def to_out(project: ResearchProject, agg: dict) -> ProjectOut:
    minimum = get_settings().min_interviews_for_synthesis
    return ProjectOut.model_validate(
        {
            **{c: getattr(project, c) for c in ProjectOut.model_fields if hasattr(project, c)},
            **agg,
            "owner_name": project.owner.name if project.owner else None,
            "ready_for_synthesis": agg.get("participant_count", 0) >= minimum,
            "min_participants": minimum,
            "last_activity_at": max(x for x in (project.updated_at, agg.get("last_audit_at")) if x is not None),
        }
    )


def serialize_projects(db: Session, projects: list[ResearchProject]) -> list[ProjectOut]:
    agg = project_aggregates(db, [p.id for p in projects])
    return [to_out(p, agg.get(p.id, {})) for p in projects]
