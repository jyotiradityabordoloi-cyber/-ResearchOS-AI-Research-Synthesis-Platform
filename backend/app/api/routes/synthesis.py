from dataclasses import dataclass

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.ai.embeddings import Embedder, build_embedder
from app.ai.engine import AIEngine, build_engine
from app.ai.providers import LLMError
from app.api.deps import get_current_user, get_project_or_404
from app.core.config import get_settings
from app.core.db import get_db
from app.models import Insight, ResearchProject, SynthesisRun, Theme, User
from app.models.enums import EvidenceStance, ReviewStatus
from app.schemas import InsightOut, SynthesisRequest, SynthesisRunOut, ThemeOut
from app.services.projects import live_filter
from app.services.synthesis import SynthesisRefused, execute_run, start_run

router = APIRouter(tags=["synthesis"])


@dataclass
class AI:
    engine: AIEngine
    embedder: Embedder


def get_ai() -> AI:
    """Overridable dependency: tests inject failing or fake engines here."""
    settings = get_settings()
    try:
        return AI(engine=build_engine(settings), embedder=build_embedder(settings))
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=f"AI provider unavailable: {exc}") from exc


def _run_out(run: SynthesisRun, project: ResearchProject) -> SynthesisRunOut:
    return SynthesisRunOut.model_validate(run).model_copy(
        update={"is_active": project.active_run_id == run.id, "is_demo": run.provider == "demo"}
    )


@router.post("/api/projects/{project_id}/synthesis", response_model=SynthesisRunOut, status_code=202)
def run_synthesis(
    background: BackgroundTasks,
    payload: SynthesisRequest | None = None,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    ai: AI = Depends(get_ai),
) -> SynthesisRunOut:
    """Start AI synthesis on the project's valid interviews. Poll the runs endpoint for progress."""
    try:
        run = start_run(db, project, user, ai.engine, ai.embedder, force=bool(payload and payload.force))
    except SynthesisRefused as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    background.add_task(execute_run, run.id, ai.engine, ai.embedder)
    return _run_out(run, project)


@router.get("/api/projects/{project_id}/synthesis/runs", response_model=list[SynthesisRunOut])
def list_runs(
    limit: int = Query(default=10, ge=1, le=100),
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> list[SynthesisRunOut]:
    runs = db.scalars(
        select(SynthesisRun)
        .where(SynthesisRun.project_id == project.id)
        .order_by(SynthesisRun.started_at.desc())
        .limit(limit)
    )
    return [_run_out(r, project) for r in runs]


_STATUS_ORDER = {ReviewStatus.APPROVED: 0, ReviewStatus.PROPOSED: 1, ReviewStatus.REJECTED: 2}


@router.get("/api/projects/{project_id}/themes", response_model=list[ThemeOut])
def list_themes(
    include_rejected: bool = False,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> list[ThemeOut]:
    """Themes of the active synthesis run plus manual themes, with linked evidence."""
    stmt = (
        select(Theme)
        .options(selectinload(Theme.evidence))
        .where(live_filter(Theme, project), Theme.status != ReviewStatus.MERGED)
    )
    if not include_rejected:
        stmt = stmt.where(Theme.status != ReviewStatus.REJECTED)
    themes = list(db.scalars(stmt))
    themes.sort(key=lambda t: (-t.participant_count, -t.confidence, t.code))
    out = []
    for t in themes:
        t.evidence.sort(key=lambda e: (e.stance != EvidenceStance.SUPPORTING, not e.quote_verified, e.participant_id))
        out.append(ThemeOut.model_validate(t))
    return out


@router.get("/api/projects/{project_id}/insights", response_model=list[InsightOut])
def list_insights(
    include_rejected: bool = True,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> list[InsightOut]:
    """Prioritised insights: manual override first, otherwise the computed band, then score."""
    from app.api.routes.review import add_context, insight_out, sort_insights

    stmt = (
        select(Insight, Theme.code)
        .outerjoin(Theme, Theme.id == Insight.theme_id)
        .where(live_filter(Insight, project), Insight.status != ReviewStatus.MERGED)
    )
    if not include_rejected:
        stmt = stmt.where(Insight.status != ReviewStatus.REJECTED)
    return sort_insights(add_context(db, [insight_out(i, code, project.name) for i, code in db.execute(stmt).all()]))
