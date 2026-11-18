import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import HumanReview, User


def record(
    db: Session,
    *,
    project_id: uuid.UUID,
    entity_type: str,
    action: str,
    entity_id: uuid.UUID | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    comment: str | None = None,
    user: User | None = None,
) -> HumanReview:
    """Append an entry to the human review / audit log. Caller commits."""
    entry = HumanReview(
        project_id=project_id,
        user_id=user.id if user else None,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        before=before,
        after=after,
        comment=comment,
    )
    db.add(entry)
    return entry
