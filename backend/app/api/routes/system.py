from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ai.status import embedding_status, llm_status
from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.models import User
from app.schemas import AISettingsOut, UserOut

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    vector = db.scalar(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
    return {"status": "ok", "database": "ok", "pgvector": vector}


@router.get("/settings/ai", response_model=AISettingsOut)
def ai_settings() -> AISettingsOut:
    s = get_settings()
    return AISettingsOut(
        llm=llm_status(s),
        embeddings=embedding_status(s),
        min_interviews_for_synthesis=s.min_interviews_for_synthesis,
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user
