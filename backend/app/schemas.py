"""Pydantic request/response schemas for the HTTP API."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import InterviewSource, ProjectStatus


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def _clean_list(values: list[str]) -> list[str]:
    seen: list[str] = []
    for v in values:
        v = v.strip()
        if v and v not in seen:
            seen.append(v)
    return seen


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class UserOut(ORM):
    id: uuid.UUID
    email: str
    name: str
    role: str


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    objectives: list[str] = Field(default_factory=list, max_length=20)
    target_segments: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Project name cannot be blank")
        return v

    @field_validator("objectives", "target_segments")
    @classmethod
    def clean(cls, v: list[str]) -> list[str]:
        return _clean_list(v)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    objectives: list[str] | None = Field(default=None, max_length=20)
    target_segments: list[str] | None = Field(default=None, max_length=20)
    status: ProjectStatus | None = None

    @field_validator("objectives", "target_segments")
    @classmethod
    def clean(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _clean_list(v)


class ProjectOut(ORM):
    id: uuid.UUID
    name: str
    description: str
    objectives: list[str]
    target_segments: list[str]
    status: str
    synthesis_status: str
    owner_name: str | None = None
    interview_count: int = 0
    valid_interview_count: int = 0
    invalid_interview_count: int = 0
    participant_count: int = 0
    theme_count: int = 0
    pending_review_count: int = 0
    ready_for_synthesis: bool = False
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Interviews
# ---------------------------------------------------------------------------


class InterviewFields(BaseModel):
    participant_id: str = Field(default="", max_length=100)
    participant_role: str = Field(default="", max_length=200)
    company_size: str = Field(default="", max_length=100)
    plan_tier: str = Field(default="", max_length=100)
    pain: str = Field(default="", max_length=20000)
    behavior: str = Field(default="", max_length=20000)
    verbatim_quote: str = Field(default="", max_length=20000)

    @field_validator("*")
    @classmethod
    def strip(cls, v: Any) -> Any:
        return v.strip() if isinstance(v, str) else v


class InterviewCreate(InterviewFields):
    raw_content: str | None = Field(
        default=None,
        max_length=100000,
        description="Original notes. If omitted, a canonical text block is built from the fields.",
    )
    source: InterviewSource = InterviewSource.MANUAL
    source_filename: str | None = None


class InterviewUpdate(BaseModel):
    """Corrections to structured fields. `raw_content` is intentionally not editable."""

    model_config = ConfigDict(extra="forbid")

    participant_id: str | None = Field(default=None, max_length=100)
    participant_role: str | None = Field(default=None, max_length=200)
    company_size: str | None = Field(default=None, max_length=100)
    plan_tier: str | None = Field(default=None, max_length=100)
    pain: str | None = Field(default=None, max_length=20000)
    behavior: str | None = Field(default=None, max_length=20000)
    verbatim_quote: str | None = Field(default=None, max_length=20000)
    comment: str | None = Field(default=None, max_length=2000)


class ValidationIssue(BaseModel):
    field: str
    severity: Literal["error", "warning"]
    message: str


class InterviewOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str | None = None
    participant_id: str
    participant_role: str
    company_size: str
    plan_tier: str
    pain: str
    behavior: str
    verbatim_quote: str
    raw_content: str
    source: str
    source_filename: str | None
    validation_status: str
    validation_errors: list[ValidationIssue]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Import (Module B) and validation report (Module C)
# ---------------------------------------------------------------------------


class ValidationResult(BaseModel):
    status: Literal["valid", "invalid"]
    issues: list[ValidationIssue]


class PreviewTextRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500_000)


class PreviewItem(BaseModel):
    index: int
    fields: InterviewFields
    raw_content: str
    source: InterviewSource
    source_filename: str | None = None
    status: Literal["valid", "invalid"]
    issues: list[ValidationIssue] = Field(description="All issues: context + field validation.")
    context_issues: list[ValidationIssue] = Field(
        description="Parsing and duplicate-participant notes (warnings). Unaffected by field edits."
    )


class FileError(BaseModel):
    filename: str
    message: str


class PreviewSummary(BaseModel):
    total: int
    valid: int
    invalid: int
    with_warnings: int
    duplicate_participants: list[str]
    existing_valid_participants: int
    valid_participants_after_import: int
    min_required: int
    sample_sufficient: bool


class ImportPreview(BaseModel):
    items: list[PreviewItem]
    summary: PreviewSummary
    file_errors: list[FileError] = Field(default_factory=list)


class ImportItem(BaseModel):
    fields: InterviewFields
    raw_content: str = Field(min_length=1, max_length=100_000)
    parsed_fields: InterviewFields | None = Field(
        default=None, description="Fields as originally parsed; used to log pre-import corrections."
    )
    source: InterviewSource = InterviewSource.PASTE
    source_filename: str | None = Field(default=None, max_length=300)


class ImportRequest(BaseModel):
    items: list[ImportItem] = Field(min_length=1, max_length=200)
    skip_invalid: bool = True


class SkippedItem(BaseModel):
    index: int
    participant_id: str
    reason: str


class ImportResult(BaseModel):
    created: list[InterviewOut]
    skipped: list[SkippedItem]


class ReadinessCheck(BaseModel):
    key: str
    status: Literal["pass", "warn", "fail"]
    message: str


class InvalidInterviewRef(BaseModel):
    id: uuid.UUID
    participant_id: str
    errors: list[str]


class ValidationReport(BaseModel):
    total_interviews: int
    valid_interviews: int
    invalid_interviews: int
    unique_valid_participants: int
    min_required: int
    duplicate_participants: dict[str, int]
    invalid: list[InvalidInterviewRef]
    checks: list[ReadinessCheck]
    can_run_standard_synthesis: bool


# ---------------------------------------------------------------------------
# Synthesis (Module D) and insights
# ---------------------------------------------------------------------------


class SynthesisRequest(BaseModel):
    force: bool = Field(
        default=False, description="Run an exploratory synthesis even with fewer than the minimum participants."
    )


class RunWarning(BaseModel):
    code: str
    message: str


class SynthesisRunOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    stage: str
    provider: str
    model: str
    embedding_provider: str
    error: str | None
    warnings: list[RunWarning]
    stats: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None
    is_active: bool = False
    is_demo: bool = False


class EvidenceOut(ORM):
    id: uuid.UUID
    interview_id: uuid.UUID
    pain_point_id: uuid.UUID | None
    participant_id: str
    quote: str
    quote_verified: bool
    source_field: str | None
    stance: str
    note: str


class ThemeOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    run_id: uuid.UUID | None
    code: str
    name: str
    description: str
    implication: str
    participant_ids: list[str]
    participant_count: int
    total_participants: int
    frequency: float
    confidence: float
    severity: int
    evidence_status: str
    is_outlier: bool
    is_low_confidence: bool
    has_contradictions: bool
    sensitive_tags: list[str]
    requires_approval: bool
    strategic_flag: bool
    status: str
    origin: str
    human_edited: bool
    merged_into_id: uuid.UUID | None = None
    split_from_id: uuid.UUID | None = None
    evidence: list[EvidenceOut]
    created_at: datetime
    updated_at: datetime


class InsightOut(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    theme_id: uuid.UUID | None
    theme_code: str | None = None
    title: str
    statement: str
    implication: str
    frequency: float
    severity: int
    strategic_relevance: int
    confidence: float
    priority_score: float
    priority_override: str | None
    override_reason: str | None
    pm_comment: str | None
    is_outlier: bool
    sensitive_tags: list[str]
    requires_approval: bool
    strategic_flag: bool
    status: str
    origin: str
    project_name: str | None = None
    computed_priority: Literal["high", "medium", "low"] = "low"
    effective_priority: Literal["high", "medium", "low"] = "low"
    is_overridden: bool = False
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Human review (Module F) and prioritisation (Module E)
# ---------------------------------------------------------------------------


class ThemeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    implication: str | None = Field(default=None, max_length=5000)
    strategic_flag: bool | None = None
    comment: str | None = Field(default=None, max_length=2000)


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject", "reopen"]
    comment: str | None = Field(default=None, max_length=2000)
    acknowledge_sensitive: bool = Field(
        default=False, description="Required to approve pricing, churn or competitive-switching findings."
    )


class MergeRequest(BaseModel):
    theme_ids: list[uuid.UUID] = Field(min_length=2, max_length=20, description="First id is the merge target.")
    name: str | None = Field(default=None, min_length=3, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    comment: str | None = Field(default=None, max_length=2000)


class SplitRequest(BaseModel):
    evidence_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    name: str = Field(min_length=3, max_length=300)
    description: str = Field(default="", max_length=5000)
    comment: str | None = Field(default=None, max_length=2000)


class MoveEvidenceRequest(BaseModel):
    target_theme_id: uuid.UUID
    comment: str | None = Field(default=None, max_length=2000)


class AddEvidenceRequest(BaseModel):
    interview_id: uuid.UUID
    quote: str = Field(min_length=3, max_length=2000)
    stance: Literal["supporting", "contradicting"] = "supporting"
    note: str = Field(default="", max_length=2000)


class InsightUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=3, max_length=300)
    statement: str | None = Field(default=None, max_length=5000)
    implication: str | None = Field(default=None, max_length=5000)
    severity: int | None = Field(default=None, ge=1, le=5)
    strategic_relevance: int | None = Field(default=None, ge=1, le=5)
    priority_override: Literal["high", "medium", "low"] | None = None
    override_reason: str | None = Field(default=None, max_length=2000)
    pm_comment: str | None = Field(default=None, max_length=5000)
    strategic_flag: bool | None = None
    comment: str | None = Field(default=None, max_length=2000)


class InsightCreate(BaseModel):
    title: str = Field(min_length=3, max_length=300)
    statement: str = Field(default="", max_length=5000)
    implication: str = Field(default="", max_length=5000)
    theme_id: uuid.UUID | None = None
    severity: int = Field(default=3, ge=1, le=5)
    strategic_relevance: int = Field(default=3, ge=1, le=5)
    strategic_flag: bool = False
    pm_comment: str | None = Field(default=None, max_length=5000)


# ---------------------------------------------------------------------------
# Reports (Module G) and repository (Module H)
# ---------------------------------------------------------------------------


class ReportCreate(BaseModel):
    kind: Literal["draft", "approved"] = "draft"
    title: str | None = Field(default=None, max_length=300)


class ReportSummary(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str | None = None
    run_id: uuid.UUID | None
    title: str
    status: str
    excluded_sensitive_count: int
    created_at: datetime


class ReportOut(ReportSummary):
    content_markdown: str
    content_json: dict[str, Any]


class RepositoryEvidence(BaseModel):
    id: str
    interview_id: str
    participant_id: str
    quote: str
    quote_verified: bool
    note: str
    stance: str


class RepositoryHit(BaseModel):
    kind: Literal["theme", "insight"]
    id: str
    project_id: str
    project_name: str
    project_status: str
    code: str | None
    title: str
    description: str
    implication: str
    participant_ids: list[str]
    participant_count: int | None
    total_participants: int | None
    frequency: float
    severity: int
    status: str
    requires_approval: bool
    sensitive_tags: list[str]
    is_outlier: bool
    has_contradictions: bool
    score: float | None
    evidence_count: int
    evidence: list[RepositoryEvidence]
    priority: str | None
    created_at: str


class RepositoryFacets(BaseModel):
    projects: list[dict[str, str]]
    roles: list[str]
    company_sizes: list[str]
    plan_tiers: list[str]


# ---------------------------------------------------------------------------
# Dashboard / audit
# ---------------------------------------------------------------------------


class ActivityItem(BaseModel):
    kind: str
    title: str
    detail: str | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    actor: str | None = None
    at: datetime


class ProjectCount(BaseModel):
    project_id: uuid.UUID
    project_name: str
    interviews: int
    valid_interviews: int
    themes: int


class DashboardStats(BaseModel):
    total_projects: int
    total_interviews: int
    valid_interviews: int
    themes_identified: int
    pending_reviews: int
    projects_by_status: dict[str, int]
    per_project: list[ProjectCount]
    recent_activity: list[ActivityItem]


class AuditEntry(ORM):
    id: uuid.UUID
    project_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID | None
    action: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    comment: str | None
    actor: str | None = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class ProviderStatus(BaseModel):
    name: str
    model: str
    available: bool
    detail: str
    is_demo: bool


class AISettingsOut(BaseModel):
    llm: ProviderStatus
    embeddings: ProviderStatus
    min_interviews_for_synthesis: int
