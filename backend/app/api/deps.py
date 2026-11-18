import uuid

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import ResearchProject, User

DEFAULT_USER_EMAIL = "pm@researchos.local"


def get_current_user(db: Session = Depends(get_db)) -> User:
    """MVP: single-workspace mode with one default user (real auth is a later phase)."""
    user = db.scalar(select(User).where(User.email == DEFAULT_USER_EMAIL))
    if user is None:
        user = User(email=DEFAULT_USER_EMAIL, name="Research Lead", role="product_manager")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_project_or_404(project_id: uuid.UUID, db: Session = Depends(get_db)) -> ResearchProject:
    project = db.get(ResearchProject, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Research project not found")
    return project
