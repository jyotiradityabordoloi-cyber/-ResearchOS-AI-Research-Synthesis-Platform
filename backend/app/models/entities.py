import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import EMBEDDING_DIM
from app.core.db import Base
from app.models.enums import (
    EvidenceStance,
    InterviewSource,
    Origin,
    ProjectStatus,
    ReportStatus,
    ReviewStatus,
    SynthesisStatus,
    ValidationStatus,
)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Users & projects
# ---------------------------------------------------------------------------


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="product_manager", nullable=False)


class ResearchProject(TimestampMixin, Base):
    __tablename__ = "research_projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    objectives: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    target_segments: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=ProjectStatus.DRAFT, nullable=False)
    synthesis_status: Mapped[str] = mapped_column(
        String(32), default=SynthesisStatus.NOT_STARTED, nullable=False
    )
    # Run whose themes/insights are currently "live" for this project.
    active_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "synthesis_runs.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_research_projects_active_run_id",
        )
    )

    owner: Mapped[User | None] = relationship()
    interviews: Mapped[list["Interview"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (Index("ix_research_projects_status", "status"),)


class Interview(TimestampMixin, Base):
    """One interview. `raw_content` is the untouched original and is never updated."""

    __tablename__ = "interviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    participant_role: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    company_size: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    plan_tier: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    pain: Mapped[str] = mapped_column(Text, default="", nullable=False)
    behavior: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verbatim_quote: Mapped[str] = mapped_column(Text, default="", nullable=False)

    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default=InterviewSource.MANUAL, nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(300))

    validation_status: Mapped[str] = mapped_column(
        String(16), default=ValidationStatus.PENDING, nullable=False
    )
    validation_errors: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    project: Mapped[ResearchProject] = relationship(back_populates="interviews")

    __table_args__ = (
        Index("ix_interviews_project_id", "project_id"),
        Index("ix_interviews_project_participant", "project_id", "participant_id"),
        Index("ix_interviews_validation_status", "validation_status"),
    )


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


class SynthesisRun(Base):
    """A single execution of the synthesis pipeline.

    Results are written in one transaction at the end of a run, so a failed run
    never replaces the project's previous `active_run_id`.
    """

    __tablename__ = "synthesis_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), default=SynthesisStatus.RUNNING, nullable=False
    )
    stage: Mapped[str] = mapped_column(String(64), default="queued", nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class PainPoint(Base):
    """Atomic pain point extracted from a single interview (pipeline stage 1)."""

    __tablename__ = "pain_points"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("synthesis_runs.id", ondelete="CASCADE"), nullable=False
    )
    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    quote: Mapped[str | None] = mapped_column(Text)
    quote_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Which interview field the quote came from: verbatim_quote | pain | behavior.
    source_field: Mapped[str | None] = mapped_column(String(32))
    # Near-identical pain points from the same participant collapse into one (counted once).
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    severity: Mapped[int | None] = mapped_column(Integer)  # 1-5, LLM estimate
    sensitive_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_pain_points_project_run", "project_id", "run_id"),
        Index("ix_pain_points_interview_id", "interview_id"),
        Index(
            "ix_pain_points_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Theme(TimestampMixin, Base):
    __tablename__ = "themes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("synthesis_runs.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(String(16), nullable=False)  # human-friendly "T3"
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    implication: Mapped[str] = mapped_column(Text, default="", nullable=False)

    # Deterministic, computed in Python: unique participants / total participants.
    participant_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    participant_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_participants: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    frequency: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    severity: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)
    evidence_status: Mapped[str] = mapped_column(
        String(16), default="sufficient", nullable=False
    )  # sufficient | insufficient

    is_outlier: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_low_confidence: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_contradictions: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sensitive_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    strategic_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[str] = mapped_column(String(16), default=ReviewStatus.PROPOSED, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), default=Origin.AI, nullable=False)
    human_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("themes.id", ondelete="SET NULL")
    )
    split_from_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("themes.id", ondelete="SET NULL")
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    evidence: Mapped[list["ThemeEvidence"]] = relationship(
        back_populates="theme", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("ix_themes_project_run", "project_id", "run_id"),
        Index("ix_themes_status", "status"),
        Index(
            "ix_themes_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class ThemeEvidence(Base):
    """Links a theme to an original interview and a verbatim quote."""

    __tablename__ = "theme_evidence"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    theme_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("themes.id", ondelete="CASCADE"), nullable=False
    )
    interview_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False
    )
    pain_point_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pain_points.id", ondelete="SET NULL")
    )
    participant_id: Mapped[str] = mapped_column(String(100), nullable=False)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    quote_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_field: Mapped[str | None] = mapped_column(String(32))
    stance: Mapped[str] = mapped_column(
        String(16), default=EvidenceStance.SUPPORTING, nullable=False
    )
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    theme: Mapped[Theme] = relationship(back_populates="evidence")
    interview: Mapped[Interview] = relationship()

    __table_args__ = (
        Index("ix_theme_evidence_theme_id", "theme_id"),
        Index("ix_theme_evidence_interview_id", "interview_id"),
    )


class Insight(TimestampMixin, Base):
    """Prioritised finding. Frequency and impact are stored separately on purpose."""

    __tablename__ = "insights"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("synthesis_runs.id", ondelete="CASCADE")
    )
    theme_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("themes.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    statement: Mapped[str] = mapped_column(Text, default="", nullable=False)
    implication: Mapped[str] = mapped_column(Text, default="", nullable=False)

    frequency: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    severity: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1-5
    strategic_relevance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1-5
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    priority_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    # Manual override (Module E). The computed score is kept for transparency.
    priority_override: Mapped[str | None] = mapped_column(String(16))  # high | medium | low
    override_reason: Mapped[str | None] = mapped_column(Text)
    pm_comment: Mapped[str | None] = mapped_column(Text)

    is_outlier: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sensitive_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    strategic_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ReviewStatus.PROPOSED, nullable=False)
    origin: Mapped[str] = mapped_column(String(16), default=Origin.AI, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))

    __table_args__ = (
        Index("ix_insights_project_run", "project_id", "run_id"),
        Index("ix_insights_theme_id", "theme_id"),
        Index("ix_insights_status", "status"),
        Index(
            "ix_insights_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


# ---------------------------------------------------------------------------
# Human review & reports
# ---------------------------------------------------------------------------


class HumanReview(Base):
    """Append-only audit log of every human action on research data."""

    __tablename__ = "human_reviews"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)  # theme|insight|interview|...
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    action: Mapped[str] = mapped_column(String(48), nullable=False)  # rename|merge|approve|...
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User | None] = relationship()

    __table_args__ = (
        Index("ix_human_reviews_project_created", "project_id", "created_at"),
        Index("ix_human_reviews_entity", "entity_type", "entity_id"),
    )


class ResearchReport(TimestampMixin, Base):
    __tablename__ = "research_reports"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("research_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("synthesis_runs.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default=ReportStatus.DRAFT, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    excluded_sensitive_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    generated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
