import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.api.routes import dashboard, imports, interviews, projects, reports, review, synthesis, system
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import ResearchProject, SynthesisRun
from app.models.enums import SynthesisStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("researchos")


def recover_interrupted_runs() -> int:
    """Runs execute in-process; any still 'running' at startup were cut off by a restart.

    Mark them failed so the UI stops waiting and new runs are allowed. Their results were
    never committed (results are written in one transaction), so no data is lost.
    """
    with SessionLocal() as db:
        runs = list(db.scalars(select(SynthesisRun).where(SynthesisRun.status == SynthesisStatus.RUNNING)))
        for run in runs:
            run.status = SynthesisStatus.FAILED
            run.stage = "failed"
            run.error = "Interrupted: the server restarted while this run was in progress. Run synthesis again."
            run.finished_at = datetime.now(UTC)
            project = db.get(ResearchProject, run.project_id)
            if project and project.synthesis_status == SynthesisStatus.RUNNING:
                project.synthesis_status = (
                    SynthesisStatus.COMPLETED if project.active_run_id else SynthesisStatus.FAILED
                )
        db.commit()
        return len(runs)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    try:
        recovered = recover_interrupted_runs()
        if recovered:
            log.warning("Marked %d interrupted synthesis run(s) as failed", recovered)
    except Exception:  # noqa: BLE001 - a DB hiccup at boot must not stop the API starting
        log.exception("Could not check for interrupted synthesis runs")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ResearchOS API",
        version="1.0.0",
        description="AI-assisted user research synthesis. Interactive docs at /docs.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log the details server-side; never leak stack traces to the client.
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server. Please try again."})

    for module in (system, dashboard, projects, imports, interviews, synthesis, review, reports):
        app.include_router(module.router)
    return app


app = create_app()
