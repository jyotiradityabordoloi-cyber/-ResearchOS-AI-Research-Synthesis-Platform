import re
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import build_embedder
from app.api.deps import get_current_user, get_project_or_404
from app.core.config import get_settings
from app.core.db import get_db
from app.models import ResearchProject, ResearchReport, User
from app.schemas import ReportCreate, ReportOut, ReportPreview, ReportSummary, RepositoryFacets, RepositoryHit
from app.services import repository
from app.services.pdf import render_pdf
from app.services.report import (
    ReportError,
    ReportOptions,
    build_report_content,
    default_title,
    generate_report,
    to_markdown,
)

router = APIRouter(tags=["reports"])


def _summary(r: ResearchReport, project_name: str | None) -> ReportSummary:
    return ReportSummary.model_validate(r).model_copy(update={"project_name": project_name})


def _get_report(db: Session, report_id: uuid.UUID) -> tuple[ResearchReport, ResearchProject]:
    report = db.get(ResearchReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report, db.get(ResearchProject, report.project_id)


def _filename(title: str, ext: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()[:80] or "research-report"
    return f"{slug}.{ext}"


# --- Reports -----------------------------------------------------------------------


def _options(payload: ReportCreate) -> ReportOptions:
    o = payload.options
    if o is None:
        return ReportOptions()
    return ReportOptions(sections=o.sections, excluded_theme_ids=o.excluded_theme_ids, executive_summary=o.executive_summary)


@router.post("/api/projects/{project_id}/reports/preview", response_model=ReportPreview)
def preview_report(
    payload: ReportCreate,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> ReportPreview:
    """Build a report exactly as it would be saved, without saving it (report builder preview)."""
    try:
        content = build_report_content(db, project, payload.kind, _options(payload))
    except ReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    title = (payload.title or "").strip() or default_title(project, payload.kind)
    return ReportPreview(title=title, content=content, markdown=to_markdown(content, title))


@router.post("/api/projects/{project_id}/reports", response_model=ReportOut, status_code=201)
def create_report(
    payload: ReportCreate,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReportOut:
    """Generate a draft (approved + unreviewed findings) or approved (approved only) report.

    Sensitive findings are never included until a person has approved them.
    """
    try:
        report = generate_report(db, project, payload.kind, payload.title, user, _options(payload))
    except ReportError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc
    return ReportOut.model_validate(report).model_copy(update={"project_name": project.name})


@router.get("/api/projects/{project_id}/reports", response_model=list[ReportSummary])
def project_reports(
    project: ResearchProject = Depends(get_project_or_404), db: Session = Depends(get_db)
) -> list[ReportSummary]:
    rows = db.scalars(
        select(ResearchReport).where(ResearchReport.project_id == project.id).order_by(ResearchReport.created_at.desc())
    )
    return [_summary(r, project.name) for r in rows]


@router.get("/api/reports", response_model=list[ReportSummary])
def all_reports(
    status: Literal["draft", "approved"] | None = None, db: Session = Depends(get_db)
) -> list[ReportSummary]:
    stmt = select(ResearchReport, ResearchProject.name).join(
        ResearchProject, ResearchProject.id == ResearchReport.project_id
    )
    if status:
        stmt = stmt.where(ResearchReport.status == status)
    rows = db.execute(stmt.order_by(ResearchReport.created_at.desc()).limit(200)).all()
    return [_summary(r, name) for r, name in rows]


@router.get("/api/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: uuid.UUID, db: Session = Depends(get_db)) -> ReportOut:
    report, project = _get_report(db, report_id)
    return ReportOut.model_validate(report).model_copy(update={"project_name": project.name})


@router.get("/api/reports/{report_id}/export.md")
def export_markdown(report_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    report, _ = _get_report(db, report_id)
    return Response(
        content=report.content_markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{_filename(report.title, "md")}"'},
    )


@router.get("/api/reports/{report_id}/export.pdf")
def export_pdf(report_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    report, _ = _get_report(db, report_id)
    return Response(
        content=render_pdf(report.content_json, report.title),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_filename(report.title, "pdf")}"'},
    )


@router.delete("/api/reports/{report_id}", status_code=204)
def delete_report(report_id: uuid.UUID, db: Session = Depends(get_db)) -> Response:
    report, _ = _get_report(db, report_id)
    db.delete(report)
    db.commit()
    return Response(status_code=204)


# --- Repository --------------------------------------------------------------------


@router.get("/api/repository/search", response_model=list[RepositoryHit])
def search_repository(
    q: str = Query(default="", max_length=500),
    mode: Literal["keyword", "semantic", "theme"] = "keyword",
    project_id: uuid.UUID | None = None,
    role: str | None = Query(default=None, max_length=200),
    company_size: str | None = Query(default=None, max_length=100),
    plan_tier: str | None = Query(default=None, max_length=100),
    approved_only: bool = False,
    limit: int = Query(default=30, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Search past findings by keyword, theme name, or meaning (semantic, via pgvector)."""
    if mode == "semantic" and not q.strip():
        raise HTTPException(status_code=422, detail="Enter a question or phrase for semantic search.")
    filters = repository.Filters(
        project_id=project_id, role=role, company_size=company_size, plan_tier=plan_tier, approved_only=approved_only
    )
    embedder = build_embedder(get_settings()) if mode == "semantic" else None
    return repository.search(db, q, mode, filters, embedder, limit)


@router.get("/api/repository/facets", response_model=RepositoryFacets)
def repository_facets(db: Session = Depends(get_db)) -> dict:
    return repository.facets(db)
