from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_project_or_404
from app.api.routes.interviews import to_out
from app.core.db import get_db
from app.models import ResearchProject, User
from app.models.enums import InterviewSource
from app.schemas import (
    ImportPreview,
    ImportRequest,
    ImportResult,
    InterviewFields,
    PreviewTextRequest,
    ValidationIssue,
    ValidationReport,
    ValidationResult,
)
from app.services.importer import build_preview, import_items, validation_report
from app.services.parser import MAX_FILE_BYTES, ParseError, parse_file, parse_text
from app.services.validation import validate_fields

router = APIRouter(tags=["import"])

MAX_FILES = 20


@router.post("/api/projects/{project_id}/import/preview", response_model=ImportPreview)
def preview_text(
    payload: PreviewTextRequest,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> ImportPreview:
    """Parse pasted notes and return a validation report. Nothing is saved."""
    return build_preview(db, project, parse_text(payload.text), InterviewSource.PASTE)


@router.post("/api/projects/{project_id}/import/preview-files", response_model=ImportPreview)
async def preview_files(
    files: list[UploadFile] = File(...),
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> ImportPreview:
    """Parse uploaded .txt/.md/.csv/.json files. Nothing is saved."""
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=422, detail=f"Upload at most {MAX_FILES} files at a time.")
    parsed = []
    errors: list[dict[str, str]] = []
    for upload in files:
        name = upload.filename or "upload"
        content = await upload.read(MAX_FILE_BYTES + 1)
        try:
            items = parse_file(name, content)
        except ParseError as exc:
            errors.append({"filename": name, "message": str(exc)})
            continue
        if not items:
            errors.append({"filename": name, "message": "No interviews found in this file."})
        parsed.extend(items)
    preview = build_preview(db, project, parsed, InterviewSource.UPLOAD, errors)
    return preview


@router.post("/api/projects/{project_id}/import", response_model=ImportResult, status_code=201)
def import_interviews(
    payload: ImportRequest,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ImportResult:
    """Save reviewed interviews. Invalid items are skipped unless `skip_invalid` is false."""
    created, skipped = import_items(db, project, payload.items, user, payload.skip_invalid)
    for interview in created:
        db.refresh(interview)
    return ImportResult(created=[to_out(i) for i in created], skipped=skipped)


@router.post("/api/interviews/validate", response_model=ValidationResult)
def validate(payload: InterviewFields) -> ValidationResult:
    status, issues = validate_fields(payload.model_dump())
    return ValidationResult(status=str(status), issues=[ValidationIssue(**i) for i in issues])


@router.get("/api/projects/{project_id}/validation-report", response_model=ValidationReport)
def project_validation_report(
    project: ResearchProject = Depends(get_project_or_404), db: Session = Depends(get_db)
) -> ValidationReport:
    return validation_report(db, project)
