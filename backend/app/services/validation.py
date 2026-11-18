"""Module C — interview input validation (deterministic, no AI)."""

import re

from app.models.enums import ValidationStatus

REQUIRED_FIELDS = {
    "participant_id": "Participant ID",
    "pain": "Pain",
    "behavior": "Behavior",
}
RECOMMENDED_FIELDS = {
    "participant_role": "Participant Role",
    "company_size": "Company Size",
    "plan_tier": "Plan Tier",
    "verbatim_quote": "Verbatim Quote",
}

# Values people type when they have nothing to say.
_FILLER = {"n/a", "na", "none", "nil", "-", "--", "tbd", "todo", "?", "...", "null", "x"}
_MIN_MEANINGFUL_WORDS = 3


def _is_meaningful(text: str) -> bool:
    t = text.strip().lower()
    if not t or t in _FILLER:
        return False
    words = re.findall(r"[a-zA-ZÀ-ɏ]{2,}", t)
    return len(words) >= _MIN_MEANINGFUL_WORDS


def validate_fields(fields: dict[str, str]) -> tuple[str, list[dict[str, str]]]:
    """Return (validation_status, issues). Errors block synthesis; warnings don't."""
    issues: list[dict[str, str]] = []

    for key, label in REQUIRED_FIELDS.items():
        value = (fields.get(key) or "").strip()
        if not value:
            issues.append({"field": key, "severity": "error", "message": f"{label} is missing."})
        elif key in ("pain", "behavior") and not _is_meaningful(value):
            issues.append(
                {
                    "field": key,
                    "severity": "error",
                    "message": f"{label} does not contain meaningful information "
                    f"(needs at least {_MIN_MEANINGFUL_WORDS} words).",
                }
            )

    pid = (fields.get("participant_id") or "").strip()
    if pid and not re.fullmatch(r"[A-Za-z0-9_\-. ]{1,100}", pid):
        issues.append(
            {
                "field": "participant_id",
                "severity": "error",
                "message": "Participant ID may only contain letters, digits, spaces, '-', '_' or '.'.",
            }
        )

    for key, label in RECOMMENDED_FIELDS.items():
        if not (fields.get(key) or "").strip():
            issues.append(
                {"field": key, "severity": "warning", "message": f"{label} is empty."}
            )

    status = (
        ValidationStatus.INVALID
        if any(i["severity"] == "error" for i in issues)
        else ValidationStatus.VALID
    )
    return status, issues
