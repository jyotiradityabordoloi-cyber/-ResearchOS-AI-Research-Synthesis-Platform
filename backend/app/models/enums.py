from enum import StrEnum


class ProjectStatus(StrEnum):
    DRAFT = "draft"  # created, no interviews yet
    COLLECTING = "collecting"  # interviews being added
    IN_REVIEW = "in_review"  # synthesis done, human review in progress
    COMPLETED = "completed"  # report approved, archived in repository


class SynthesisStatus(StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationStatus(StrEnum):
    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"


class InterviewSource(StrEnum):
    PASTE = "paste"
    UPLOAD = "upload"
    MANUAL = "manual"


class ReviewStatus(StrEnum):
    PROPOSED = "proposed"  # AI generated, not yet reviewed
    APPROVED = "approved"
    REJECTED = "rejected"
    MERGED = "merged"  # folded into another theme


class Origin(StrEnum):
    AI = "ai"
    MANUAL = "manual"


class EvidenceStance(StrEnum):
    SUPPORTING = "supporting"
    CONTRADICTING = "contradicting"


class ReportStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"


class SensitiveTag(StrEnum):
    PRICING = "pricing"
    CHURN = "churn"
    COMPETITIVE_SWITCHING = "competitive_switching"
