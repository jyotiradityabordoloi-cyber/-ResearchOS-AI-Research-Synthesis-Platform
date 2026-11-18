import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_current_user, get_project_or_404
from app.core.db import get_db
from app.models import HumanReview, ResearchProject, User
from app.schemas import AuditEntry, ProjectCreate, ProjectOut, ProjectUpdate
from app.services import audit
from app.services.projects import serialize_projects

router = APIRouter(prefix="/api/projects", tags=["projects"])

_AUDITED = ("name", "description", "objectives", "target_segments", "status")


@router.get("", response_model=list[ProjectOut])
def list_projects(
    q: str | None = Query(default=None, max_length=200),
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list[ProjectOut]:
    stmt = select(ResearchProject).options(selectinload(ResearchProject.owner))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(ResearchProject.name.ilike(like), ResearchProject.description.ilike(like))
        )
    if status:
        stmt = stmt.where(ResearchProject.status == status)
    projects = list(db.scalars(stmt.order_by(ResearchProject.updated_at.desc())))
    return serialize_projects(db, projects)


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    project = ResearchProject(**payload.model_dump(), owner_id=user.id)
    db.add(project)
    db.flush()
    audit.record(
        db,
        project_id=project.id,
        entity_type="project",
        entity_id=project.id,
        action="created",
        after=payload.model_dump(),
        user=user,
    )
    db.commit()
    db.refresh(project)
    return serialize_projects(db, [project])[0]


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project: ResearchProject = Depends(get_project_or_404), db: Session = Depends(get_db)
) -> ProjectOut:
    return serialize_projects(db, [project])[0]


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(
    payload: ProjectUpdate,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    changes = payload.model_dump(exclude_unset=True, exclude_none=True)
    before = {k: getattr(project, k) for k in changes if k in _AUDITED}
    for key, value in changes.items():
        setattr(project, key, value)
    after = {k: getattr(project, k) for k in changes if k in _AUDITED}
    if before != after:
        audit.record(
            db,
            project_id=project.id,
            entity_type="project",
            entity_id=project.id,
            action="updated",
            before=before,
            after=after,
            user=user,
        )
    db.commit()
    db.refresh(project)
    return serialize_projects(db, [project])[0]


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project: ResearchProject = Depends(get_project_or_404), db: Session = Depends(get_db)
) -> Response:
    db.delete(project)
    db.commit()
    return Response(status_code=204)


@router.get("/{project_id}/audit", response_model=list[AuditEntry])
def project_audit_log(
    project_id: uuid.UUID,
    limit: int = Query(default=100, ge=1, le=500),
    _: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
) -> list[AuditEntry]:
    rows = db.scalars(
        select(HumanReview)
        .options(selectinload(HumanReview.user))
        .where(HumanReview.project_id == project_id)
        .order_by(HumanReview.created_at.desc())
        .limit(limit)
    )
    return [
        AuditEntry.model_validate(r).model_copy(update={"actor": r.user.name if r.user else None})
        for r in rows
    ]
