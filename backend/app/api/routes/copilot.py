"""Research copilot endpoint. See app/services/copilot.py."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.engine import AIEngine, LLMEngine, build_engine
from app.ai.providers import LLMError
from app.api.deps import get_project_or_404
from app.core.config import get_settings
from app.core.db import get_db
from app.models import ResearchProject
from app.schemas import CopilotAnswer, CopilotRequest
from app.services import copilot

router = APIRouter(tags=["copilot"])


def get_copilot_engine() -> tuple[AIEngine | None, str | None]:
    """Overridable in tests. A provider that can't even be built means rule-based answers."""
    settings = get_settings()
    try:
        engine = build_engine(settings.model_copy(update={"llm_timeout_seconds": settings.copilot_timeout_seconds}))
        if isinstance(engine, LLMEngine):
            # Synthesis retries patiently in the background; a person is waiting here.
            engine.provider.max_retries = max(1, settings.copilot_max_retries)
            if hasattr(engine.provider, "switch_on_timeout"):
                engine.provider.switch_on_timeout = True
        return engine, None
    except LLMError as exc:
        return None, f"The AI provider is not set up ({exc}). This answer was assembled by fixed rules from your data."


@router.post("/api/projects/{project_id}/copilot", response_model=CopilotAnswer)
def ask_copilot(
    payload: CopilotRequest,
    project: ResearchProject = Depends(get_project_or_404),
    db: Session = Depends(get_db),
    engine: tuple[AIEngine | None, str | None] = Depends(get_copilot_engine),
) -> CopilotAnswer:
    """Answer a question about this project from its themes, quotes and insights, with citations."""
    return copilot.answer(db, project, payload, engine[0], engine[1])
