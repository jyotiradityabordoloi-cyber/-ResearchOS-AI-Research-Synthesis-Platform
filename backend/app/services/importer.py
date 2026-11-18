"""Preview, validate and import interviews; project-level validation report."""

from __future__ import annotations

from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Interview, ResearchProject, User
from app.models.enums import InterviewSource, ProjectStatus, ValidationStatus
from app.schemas import (
    ImportItem,
    ImportPreview,
    InterviewFields,
    InvalidInterviewRef,
    PreviewItem,
    PreviewSummary,
    ReadinessCheck,
    SkippedItem,
    ValidationIssue,
    ValidationReport,
)
from app.services import audit
from app.services.parser import ParsedInterview
from app.services.validation import validate_fields


def _key(pid: str) -> str:
    return pid.strip().lower()


def _existing(db: Session, project: ResearchProject) -> tuple[Counter[str], set[str]]:
    """(interview count per participant, participants with a valid interview)."""
    rows = db.execute(
        select(Interview.participant_id, Interview.validation_status).where(
            Interview.project_id == project.id
        )
    ).all()
    counts: Counter[str] = Counter()
    valid: set[str] = set()
    for pid, status in rows:
        if pid.strip():
            counts[_key(pid)] += 1
            if status == ValidationStatus.VALID:
                valid.add(_key(pid))
    return counts, valid


def build_preview(
    db: Session,
    project: ResearchProject,
    parsed: list[ParsedInterview],
    source: InterviewSource,
    file_errors: list[dict[str, str]] | None = None,
) -> ImportPreview:
    existing_counts, existing_valid = _existing(db, project)
    batch_counts = Counter(_key(p.fields["participant_id"]) for p in parsed if p.fields["participant_id"].strip())

    items: list[PreviewItem] = []
    seen: set[str] = set()
    new_valid: set[str] = set()
    for i, p in enumerate(parsed):
        fields = InterviewFields.model_validate(p.fields)
        _, field_issues = validate_fields(fields.model_dump())
        context = [ValidationIssue(**x) for x in p.parse_issues]

        pid = fields.participant_id
        k = _key(pid)
        if k and batch_counts[k] > 1 and k in seen:
            context.append(
                ValidationIssue(
                    field="participant_id",
                    severity="warning",
                    message=f"Participant {pid} appears more than once in this import. "
                    "Their notes are kept, but they count as one participant.",
                )
            )
        if k and existing_counts[k]:
            context.append(
                ValidationIssue(
                    field="participant_id",
                    severity="warning",
                    message=f"Participant {pid} already has {existing_counts[k]} interview(s) in this "
                    "project. They count as one participant.",
                )
            )
        seen.add(k)

        issues = context + [ValidationIssue(**x) for x in field_issues]
        # Only field validation decides validity; context notes are warnings.
        status = "invalid" if any(x["severity"] == "error" for x in field_issues) else "valid"
        if status == "valid" and k:
            new_valid.add(k)
        items.append(
            PreviewItem(
                index=i,
                fields=fields,
                raw_content=p.raw_content,
                source=source,
                source_filename=p.source_filename,
                status=status,
                issues=issues,
                context_issues=context,
            )
        )

    minimum = get_settings().min_interviews_for_synthesis
    after = len(existing_valid | new_valid)
    summary = PreviewSummary(
        total=len(items),
        valid=sum(1 for x in items if x.status == "valid"),
        invalid=sum(1 for x in items if x.status == "invalid"),
        with_warnings=sum(
            1 for x in items if x.status == "valid" and any(i.severity == "warning" for i in x.issues)
        ),
        duplicate_participants=sorted(
            {x.fields.participant_id for x in items if batch_counts[_key(x.fields.participant_id)] > 1}
        ),
        existing_valid_participants=len(existing_valid),
        valid_participants_after_import=after,
        min_required=minimum,
        sample_sufficient=after >= minimum,
    )
    return ImportPreview(items=items, summary=summary, file_errors=file_errors or [])


def import_items(
    db: Session,
    project: ResearchProject,
    items: list[ImportItem],
    user: User,
    skip_invalid: bool = True,
) -> tuple[list[Interview], list[SkippedItem]]:
    """Save items in one transaction. Validation is re-run server-side; the client is not trusted."""
    created: list[Interview] = []
    skipped: list[SkippedItem] = []
    for i, item in enumerate(items):
        fields = item.fields.model_dump()
        status, issues = validate_fields(fields)
        if status == ValidationStatus.INVALID and skip_invalid:
            skipped.append(
                SkippedItem(
                    index=i,
                    participant_id=item.fields.participant_id,
                    reason="; ".join(x["message"] for x in issues if x["severity"] == "error"),
                )
            )
            continue
        interview = Interview(
            project_id=project.id,
            **fields,
            raw_content=item.raw_content,
            source=item.source,
            source_filename=item.source_filename,
            validation_status=status,
            validation_errors=issues,
            created_by_id=user.id,
        )
        db.add(interview)
        db.flush()

        corrected = {}
        if item.parsed_fields is not None:
            parsed = item.parsed_fields.model_dump()
            corrected = {k: {"parsed": parsed[k], "saved": fields[k]} for k in fields if parsed[k] != fields[k]}
        audit.record(
            db,
            project_id=project.id,
            entity_type="interview",
            entity_id=interview.id,
            action="imported",
            after={
                "participant_id": interview.participant_id,
                "validation_status": status,
                "source": str(item.source),
                "source_filename": item.source_filename,
                **({"corrected_before_import": corrected} if corrected else {}),
            },
            user=user,
        )
        created.append(interview)

    if created and project.status == ProjectStatus.DRAFT:
        project.status = ProjectStatus.COLLECTING
    db.commit()
    return created, skipped


def validation_report(db: Session, project: ResearchProject) -> ValidationReport:
    rows = list(
        db.scalars(
            select(Interview).where(Interview.project_id == project.id).order_by(Interview.created_at)
        )
    )
    minimum = get_settings().min_interviews_for_synthesis
    valid = [r for r in rows if r.validation_status == ValidationStatus.VALID]
    invalid = [r for r in rows if r.validation_status != ValidationStatus.VALID]
    unique_valid = {_key(r.participant_id) for r in valid if r.participant_id.strip()}
    counts = Counter(r.participant_id.strip() for r in rows if r.participant_id.strip())
    # Group case-insensitively but report the first spelling seen.
    by_key: dict[str, tuple[str, int]] = {}
    for pid, n in counts.items():
        name, total = by_key.get(_key(pid), (pid, 0))
        by_key[_key(pid)] = (name, total + n)
    duplicates = {name: n for name, n in by_key.values() if n > 1}

    checks: list[ReadinessCheck] = []
    if not rows:
        checks.append(ReadinessCheck(key="has_interviews", status="fail", message="No interviews yet."))
    if len(unique_valid) < minimum:
        checks.append(
            ReadinessCheck(
                key="sample_size",
                status="fail",
                message=f"Only {len(unique_valid)} valid participant(s). At least {minimum} are needed "
                "for standard synthesis; with fewer, findings are not representative.",
            )
        )
    else:
        checks.append(
            ReadinessCheck(
                key="sample_size",
                status="pass",
                message=f"{len(unique_valid)} valid participants (minimum {minimum}).",
            )
        )
    if invalid:
        checks.append(
            ReadinessCheck(
                key="invalid_interviews",
                status="warn",
                message=f"{len(invalid)} interview(s) have validation errors and will be excluded "
                "from synthesis until corrected.",
            )
        )
    elif rows:
        checks.append(
            ReadinessCheck(key="invalid_interviews", status="pass", message="All interviews are valid.")
        )
    if duplicates:
        checks.append(
            ReadinessCheck(
                key="duplicate_participants",
                status="warn",
                message="Multiple interviews for: "
                + ", ".join(f"{k} ({v})" for k, v in sorted(duplicates.items()))
                + ". Each participant is counted once.",
            )
        )

    return ValidationReport(
        total_interviews=len(rows),
        valid_interviews=len(valid),
        invalid_interviews=len(invalid),
        unique_valid_participants=len(unique_valid),
        min_required=minimum,
        duplicate_participants=duplicates,
        invalid=[
            InvalidInterviewRef(
                id=r.id,
                participant_id=r.participant_id,
                errors=[e["message"] for e in r.validation_errors if e.get("severity") == "error"],
            )
            for r in invalid
        ],
        checks=checks,
        can_run_standard_synthesis=not any(c.status == "fail" for c in checks),
    )
