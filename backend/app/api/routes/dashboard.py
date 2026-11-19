from collections import defaultdict
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, cast, func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.types import Date

from app.core.config import get_settings
from app.core.db import get_db
from app.models import (
    HumanReview,
    Insight,
    Interview,
    ResearchProject,
    SynthesisRun,
    Theme,
)
from app.models.enums import ReviewStatus, ValidationStatus
from app.schemas import (
    ActivityDay,
    ActivityItem,
    DashboardStats,
    FindingItem,
    ProjectCount,
    ProjectProgress,
    ReviewQueueItem,
    RunItem,
)
from app.services.projects import live_filter, project_aggregates
from app.services.review import priority_band

ACTIVITY_DAYS = 30
_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}

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
    ("insight", "review_comment"): "Reviewer comment",
    ("insight", "flag_sensitive"): "Flagged as sensitive",
    ("theme", "create"): "Theme created",
    ("theme", "delete"): "Theme deleted",
    ("theme", "unmerge"): "Merge undone",
    ("evidence", "remove_evidence"): "Evidence removed from theme",
    ("evidence", "set_stance"): "Evidence stance changed",
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
    queue = _review_queue(db, names)

    return DashboardStats(
        total_projects=len(projects),
        sensitive_pending=sum(1 for i in queue if i.requires_approval),
        review_counts=_review_counts(db),
        interview_activity=_interview_activity(db),
        project_progress=_project_progress(projects, agg),
        review_queue=queue[:8],
        top_findings=_top_findings(db, names),
        recent_runs=_recent_runs(db, names),
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


# ---------------------------------------------------------------------------
# Command-centre panels. Everything is read from live rows; nothing is invented.
# ---------------------------------------------------------------------------

_REVIEWABLE = (ReviewStatus.PROPOSED, ReviewStatus.APPROVED, ReviewStatus.REJECTED)


def _theme_join():
    return and_(Theme.project_id == ResearchProject.id, live_filter(Theme))


def _insight_join():
    return and_(Insight.project_id == ResearchProject.id, live_filter(Insight))


def _interview_activity(db: Session) -> list[ActivityDay]:
    """Interviews added per day over the last 30 days, split by validation result."""
    today = datetime.now(UTC).date()
    start = today - timedelta(days=ACTIVITY_DAYS - 1)
    day = cast(Interview.created_at, Date)
    rows = db.execute(
        select(day, Interview.validation_status, func.count())
        .where(Interview.created_at >= datetime.combine(start, datetime.min.time(), UTC))
        .group_by(day, Interview.validation_status)
    ).all()
    counts: dict = defaultdict(lambda: [0, 0])
    for d, status, n in rows:
        counts[d][0 if status == ValidationStatus.VALID else 1] += n
    return [
        ActivityDay(day=d, valid=counts[d][0], needs_fixes=counts[d][1])
        for d in (start + timedelta(days=i) for i in range(ACTIVITY_DAYS))
    ]


def _project_progress(projects: list[ResearchProject], agg: dict) -> list[ProjectProgress]:
    minimum = get_settings().min_interviews_for_synthesis
    out = [
        ProjectProgress(
            project_id=p.id,
            project_name=p.name,
            status=p.status,
            synthesis_status=p.synthesis_status,
            interviews=agg[p.id]["interview_count"],
            valid_interviews=agg[p.id]["valid_interview_count"],
            participants=agg[p.id]["participant_count"],
            min_participants=minimum,
            themes=agg[p.id]["theme_count"],
            review_total=agg[p.id]["review_total"],
            review_done=agg[p.id]["review_done"],
            reports=agg[p.id]["report_count"],
            last_activity_at=max(x for x in (p.updated_at, agg[p.id]["last_audit_at"]) if x is not None),
        )
        for p in projects
    ]
    out.sort(key=lambda x: x.last_activity_at, reverse=True)
    return out[:8]


def _review_counts(db: Session) -> dict[str, int]:
    counts = {s.value: 0 for s in _REVIEWABLE}
    for model, join in ((Theme, _theme_join()), (Insight, _insight_join())):
        for status, n in db.execute(
            select(model.status, func.count())
            .join(ResearchProject, join)
            .where(model.status.in_(_REVIEWABLE))
            .group_by(model.status)
        ).all():
            counts[status] += n
    return counts


def _review_queue(db: Session, names: dict) -> list[ReviewQueueItem]:
    """Proposed themes and insights: sensitive first, then most severe, then most frequent."""
    items: list[ReviewQueueItem] = []
    for t in db.scalars(
        select(Theme).join(ResearchProject, _theme_join()).where(Theme.status == ReviewStatus.PROPOSED)
    ):
        items.append(
            ReviewQueueItem(
                kind="theme",
                id=t.id,
                project_id=t.project_id,
                project_name=names.get(t.project_id, ""),
                code=t.code,
                title=t.name,
                severity=t.severity,
                frequency=t.frequency,
                requires_approval=t.requires_approval,
                is_outlier=t.is_outlier,
                has_contradictions=t.has_contradictions,
            )
        )
    for i in db.scalars(
        select(Insight).join(ResearchProject, _insight_join()).where(Insight.status == ReviewStatus.PROPOSED)
    ):
        items.append(
            ReviewQueueItem(
                kind="insight",
                id=i.id,
                project_id=i.project_id,
                project_name=names.get(i.project_id, ""),
                title=i.title,
                severity=i.severity,
                frequency=i.frequency,
                requires_approval=i.requires_approval,
                is_outlier=i.is_outlier,
            )
        )
    items.sort(key=lambda x: (not x.requires_approval, -x.severity, -x.frequency))
    return items


def _top_findings(db: Session, names: dict) -> list[FindingItem]:
    rows = db.execute(
        select(Insight, Theme.code)
        .join(ResearchProject, _insight_join())
        .outerjoin(Theme, Theme.id == Insight.theme_id)
        .where(Insight.status.in_((ReviewStatus.PROPOSED, ReviewStatus.APPROVED)))
    ).all()
    found = [
        FindingItem(
            id=i.id,
            project_id=i.project_id,
            project_name=names.get(i.project_id, ""),
            theme_code=code,
            title=i.title,
            implication=i.implication or i.statement,
            priority=i.priority_override or priority_band(i.priority_score),
            frequency=i.frequency,
            severity=i.severity,
            strategic_relevance=i.strategic_relevance,
            status=i.status,
        )
        for i, code in rows
    ]
    found.sort(key=lambda f: (_PRIORITY_RANK[f.priority], f.status != ReviewStatus.APPROVED, -f.frequency))
    return found[:5]


def _recent_runs(db: Session, names: dict) -> list[RunItem]:
    runs = db.scalars(select(SynthesisRun).order_by(SynthesisRun.started_at.desc()).limit(5))
    return [
        RunItem(
            id=r.id,
            project_id=r.project_id,
            project_name=names.get(r.project_id, ""),
            status=r.status,
            stage=r.stage,
            provider=r.provider,
            model=r.model,
            started_at=r.started_at,
            finished_at=r.finished_at,
            themes=(r.stats or {}).get("themes"),
            participants=(r.stats or {}).get("participants"),
            error=r.error[:200] if r.error else None,
        )
        for r in runs
    ]
