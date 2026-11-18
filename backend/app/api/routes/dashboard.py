from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.models import HumanReview, Interview, ResearchProject, SynthesisRun
from app.models.enums import ValidationStatus
from app.schemas import ActivityItem, DashboardStats, ProjectCount
from app.services.projects import project_aggregates

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

_ACTION_TITLES = {
    ("project", "created"): "Project created",
    ("project", "updated"): "Project updated",
    ("interview", "created"): "Interview added",
    ("interview", "imported"): "Interview imported",
    ("interview", "corrected"): "Interview corrected",
    ("interview", "deleted"): "Interview deleted",
    ("theme", "rename"): "Theme renamed",
    ("theme", "edit"): "Theme edited",
    ("theme", "flag_strategic"): "Theme flagged as strategic",
    ("theme", "approve"): "Theme approved",
    ("theme", "reject"): "Theme rejected",
    ("theme", "reopen"): "Theme reopened",
    ("theme", "merge"): "Themes merged",
    ("theme", "split"): "Theme split",
    ("theme", "approval_reset"): "Theme sent back to review",
    ("evidence", "move_evidence"): "Evidence regrouped",
    ("evidence", "add_evidence"): "Quote added to theme",
    ("insight", "create"): "Insight added",
    ("insight", "edit"): "Insight edited",
    ("insight", "override_priority"): "Priority overridden",
    ("insight", "comment"): "Insight commented",
    ("insight", "flag_strategic"): "Insight flagged as strategic",
    ("insight", "approve"): "Insight approved",
    ("insight", "reject"): "Insight rejected",
    ("insight", "reopen"): "Insight reopened",
    ("report", "generated"): "Report generated",
}


@router.get("", response_model=DashboardStats)
def dashboard(db: Session = Depends(get_db)) -> DashboardStats:
    projects = list(db.scalars(select(ResearchProject).order_by(ResearchProject.updated_at.desc())))
    agg = project_aggregates(db, [p.id for p in projects])

    by_status: dict[str, int] = {}
    for p in projects:
        by_status[p.status] = by_status.get(p.status, 0) + 1

    total_interviews = db.scalar(select(func.count()).select_from(Interview)) or 0
    valid_interviews = (
        db.scalar(
            select(func.count())
            .select_from(Interview)
            .where(Interview.validation_status == ValidationStatus.VALID)
        )
        or 0
    )

    names = {p.id: p.name for p in projects}
    activity: list[ActivityItem] = []
    for r in db.scalars(
        select(HumanReview)
        .options(selectinload(HumanReview.user))
        .order_by(HumanReview.created_at.desc())
        .limit(15)
    ):
        detail = None
        src = r.after or r.before or {}
        if r.entity_type == "interview":
            detail = f"Participant {src.get('participant_id') or '—'}"
        elif r.entity_type == "report":
            detail = str(src.get("title") or "")
        elif r.action == "rename" and r.after:
            detail = str(r.after.get("name") or "")
        elif r.action == "merge" and r.after:
            detail = str(r.after.get("name") or "")
        activity.append(
            ActivityItem(
                kind=f"{r.entity_type}.{r.action}",
                title=_ACTION_TITLES.get(
                    (r.entity_type, r.action), f"{r.entity_type.title()} {r.action.replace('_', ' ')}"
                ),
                detail=detail,
                project_id=r.project_id,
                project_name=names.get(r.project_id),
                actor=r.user.name if r.user else None,
                at=r.created_at,
            )
        )
    for run in db.scalars(select(SynthesisRun).order_by(SynthesisRun.started_at.desc()).limit(10)):
        activity.append(
            ActivityItem(
                kind=f"synthesis.{run.status}",
                title=f"Synthesis {run.status}",
                detail=f"{run.provider} · {run.model}",
                project_id=run.project_id,
                project_name=names.get(run.project_id),
                at=run.finished_at or run.started_at,
            )
        )
    activity.sort(key=lambda a: a.at, reverse=True)

    return DashboardStats(
        total_projects=len(projects),
        total_interviews=total_interviews,
        valid_interviews=valid_interviews,
        themes_identified=sum(a.get("theme_count", 0) for a in agg.values()),
        pending_reviews=sum(a.get("pending_review_count", 0) for a in agg.values()),
        projects_by_status=by_status,
        per_project=[
            ProjectCount(
                project_id=p.id,
                project_name=p.name,
                interviews=agg[p.id]["interview_count"],
                valid_interviews=agg[p.id]["valid_interview_count"],
                themes=agg[p.id]["theme_count"],
            )
            for p in projects[:8]
        ],
        recent_activity=activity[:15],
    )
