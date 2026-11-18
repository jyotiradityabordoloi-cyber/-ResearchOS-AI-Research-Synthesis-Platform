import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_project_or_404
from app.core.db import get_db
from app.models import Interview, ResearchProject, User
from app.models.enums import ProjectStatus
from app.schemas import InterviewCreate, InterviewFields, InterviewOut, InterviewUpdate
from app.services import audit
from app.services.validation import validate_fields

router = APIRouter(tags=["interviews"])

FIELD_LABELS = {
    "participant_id": "Participant ID",
    "participant_role": "Participant Role",
    "company_size": "Company Size",
    "plan_tier": "Plan Tier",
    "pain": "Pain",
    "behavior": "Behavior",
    "verbatim_quote": "Verbatim Quote",
}
STRUCTURED_FIELDS = tuple(FIELD_LABELS)


def compose_raw(fields: dict[str, str]) -> str:
    return "\n".join(f"{label}: {fields.get(key, '')}" for key, label in FIELD_LABELS.items())


def to_out(interview: Interview) -> InterviewOut:
    out = InterviewOut.model_validate(interview)
    return out.model_copy(update={"project_name": interview.project.name if interview.project else None})


def _get_interview(db: Session, interview_id: uuid.UUID) -> Interview:
    interview = db.get(Interview, interview_id, options=[selectinload(Interview.project)])
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview not found")
    return interview


@router.get("/api/interviews", response_model=list[InterviewOut])
def list_interviews(
    project_id: uuid.UUID | None = None,
    validation_status: str | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[InterviewOut]:
    stmt = select(Interview).options(selectinload(Interview.project))
    if project_id:
        stmt = stmt.where(Interview.project_id == project_id)
    if validation_status:
        stmt = stmt.where(Interview.validation_status == validation_status)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Interview.participant_id.ilike(like),
                Interview.participant_role.ilike(like),
                Interview.pain.ilike(like),
                Interview.behavior.ilike(like),
                Interview.verbatim_quote.ilike(like),
            )
        )
    rows = db.scalars(stmt.order_by(Interview.created_at.desc()).limit(limit))
    return [to_out(i) for i in rows]


@router.get("/api/projects/{project_id}/interviews", response_model=list[InterviewOut])
def list_project_interviews(
    project: ResearchProject = Depends(get_project_or_404), db: Session = Depends(get_db)
) -> list[InterviewOut]:
    rows = db.scalars(
        select(Interview)
        .options(selectinload(Interview.project))
        .where(Interview.project_id == project.id)
        .order_by(Interview.participant_id, Interview.created_at)
    )
    return [to_out(i) for i in rows]


@router.post("/api/projects/{project_id}/interviews", response_model=InterviewOut, status_code=201)
def create_interview(
    payload: InterviewCreate,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InterviewOut:
    fields = payload.model_dump(include=set(STRUCTURED_FIELDS))
    status, issues = validate_fields(fields)
    raw = payload.raw_content if payload.raw_content and payload.raw_content.strip() else compose_raw(fields)
    interview = Interview(
        project_id=project.id,
        **fields,
        raw_content=raw,
        source=payload.source,
        source_filename=payload.source_filename,
        validation_status=status,
        validation_errors=issues,
        created_by_id=user.id,
    )
    db.add(interview)
    if project.status == ProjectStatus.DRAFT:
        project.status = ProjectStatus.COLLECTING
    db.flush()
    audit.record(
        db,
        project_id=project.id,
        entity_type="interview",
        entity_id=interview.id,
        action="created",
        after={"participant_id": interview.participant_id, "validation_status": status},
        user=user,
    )
    db.commit()
    return to_out(_get_interview(db, interview.id))


@router.get("/api/interviews/{interview_id}", response_model=InterviewOut)
def get_interview(interview_id: uuid.UUID, db: Session = Depends(get_db)) -> InterviewOut:
    return to_out(_get_interview(db, interview_id))


@router.patch("/api/interviews/{interview_id}", response_model=InterviewOut)
def correct_interview(
    interview_id: uuid.UUID,
    payload: InterviewUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InterviewOut:
    """Correct structured fields. The original `raw_content` is never modified."""
    interview = _get_interview(db, interview_id)
    changes = payload.model_dump(exclude_unset=True, exclude={"comment"})
    changes = {k: (v or "").strip() for k, v in changes.items() if v is not None}
    # Clients may send every field; only log the ones that actually changed.
    changes = {k: v for k, v in changes.items() if getattr(interview, k) != v}
    before = {k: getattr(interview, k) for k in changes}
    for key, value in changes.items():
        setattr(interview, key, value)

    fields = InterviewFields.model_validate(
        {k: getattr(interview, k) for k in STRUCTURED_FIELDS}
    ).model_dump()
    status, issues = validate_fields(fields)
    interview.validation_status = status
    interview.validation_errors = issues

    after = {k: getattr(interview, k) for k in changes}
    if before != after:
        audit.record(
            db,
            project_id=interview.project_id,
            entity_type="interview",
            entity_id=interview.id,
            action="corrected",
            before=before,
            after={**after, "validation_status": status},
            comment=payload.comment,
            user=user,
        )
    db.commit()
    return to_out(_get_interview(db, interview.id))


@router.delete("/api/interviews/{interview_id}", status_code=204)
def delete_interview(
    interview_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    interview = _get_interview(db, interview_id)
    audit.record(
        db,
        project_id=interview.project_id,
        entity_type="interview",
        entity_id=interview.id,
        action="deleted",
        before={"participant_id": interview.participant_id, "raw_content": interview.raw_content},
        user=user,
    )
    db.delete(interview)
    db.commit()
    return Response(status_code=204)
