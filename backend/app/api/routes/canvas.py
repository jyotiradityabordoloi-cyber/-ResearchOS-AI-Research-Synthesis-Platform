"""Theme exploration canvas endpoints. See app/services/canvas.py for the undo pairs."""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_project_or_404
from app.api.routes.review import _call, theme_out
from app.core.db import get_db
from app.models import ResearchProject, User
from app.schemas import (
    AttachObservationRequest,
    AttachObservationResult,
    DeleteThemeResult,
    DetachEvidenceResult,
    EvidenceOut,
    EvidenceStanceRequest,
    ObservationOut,
    ThemeCreate,
    ThemeOut,
    UnmergeResult,
)
from app.services import canvas

router = APIRouter(tags=["canvas"])


@router.get("/api/projects/{project_id}/observations", response_model=list[ObservationOut])
def list_observations(
    project: ResearchProject = Depends(get_project_or_404), db: Session = Depends(get_db)
) -> list[ObservationOut]:
    """Every pain point the active synthesis run extracted, with the participant's segment."""
    return canvas.list_observations(db, project)


@router.post("/api/projects/{project_id}/themes", response_model=ThemeOut, status_code=201)
def create_theme(
    payload: ThemeCreate,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ThemeOut:
    """Create an empty PM-written theme; drag observations into it."""
    theme = _call(lambda: canvas.create_theme(db, project, payload.name, payload.description, user))
    return theme_out(db, theme.id)


@router.delete("/api/themes/{theme_id}", response_model=DeleteThemeResult)
def delete_theme(
    theme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DeleteThemeResult:
    """Delete a PM-created theme (AI themes are rejected instead, so they stay auditable)."""
    return DeleteThemeResult(evidence_returned_to=_call(lambda: canvas.delete_theme(db, theme_id, user)))


@router.post("/api/themes/{theme_id}/observations", response_model=AttachObservationResult, status_code=201)
def attach_observation(
    theme_id: uuid.UUID,
    payload: AttachObservationRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AttachObservationResult:
    """Put an observation into a theme, moving it if it already sits in another theme."""
    ev, moved_from = _call(lambda: canvas.attach_observation(db, theme_id, payload.pain_point_id, payload.stance, user))
    return AttachObservationResult(evidence=EvidenceOut.model_validate(ev), moved_from_theme_id=moved_from)


@router.delete("/api/evidence/{evidence_id}", response_model=DetachEvidenceResult)
def detach_evidence(
    evidence_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> DetachEvidenceResult:
    snap = _call(lambda: canvas.detach_evidence(db, evidence_id, user))
    return DetachEvidenceResult.model_validate(snap)


@router.patch("/api/evidence/{evidence_id}", response_model=ThemeOut)
def set_evidence_stance(
    evidence_id: uuid.UUID,
    payload: EvidenceStanceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ThemeOut:
    """Mark evidence as supporting or contradicting its theme."""
    theme = _call(lambda: canvas.set_evidence_stance(db, evidence_id, payload.stance, user))
    return theme_out(db, theme.id)


@router.post("/api/themes/{theme_id}/unmerge", response_model=UnmergeResult)
def unmerge_theme(
    theme_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> UnmergeResult:
    """Reverse the most recent merge into this theme."""
    return UnmergeResult(restored_theme_ids=_call(lambda: canvas.unmerge_theme(db, theme_id, user)))
