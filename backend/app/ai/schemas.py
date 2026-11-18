"""Pydantic schemas for every structured LLM output. All LLM JSON is validated against these."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

SensitiveTagName = Literal["pricing", "churn", "competitive_switching"]
SourceField = Literal["pain", "behavior", "verbatim_quote"]


class ExtractedPainPoint(BaseModel):
    pain: str = Field(min_length=3, max_length=500, description="One atomic pain point, paraphrased neutrally.")
    quote: str = Field(
        default="",
        max_length=1000,
        description="An EXACT, word-for-word excerpt from the interview text that supports this pain. Empty if none.",
    )
    source_field: SourceField = "pain"
    severity: int = Field(ge=1, le=5, description="1 = minor annoyance, 5 = blocks adoption or causes loss.")
    sensitive_tags: list[SensitiveTagName] = Field(default_factory=list)

    @field_validator("sensitive_tags", mode="before")
    @classmethod
    def drop_unknown_tags(cls, v: object) -> object:
        allowed = {"pricing", "churn", "competitive_switching"}
        return [t for t in v if t in allowed] if isinstance(v, list) else v


class ExtractionResult(BaseModel):
    pain_points: list[ExtractedPainPoint] = Field(max_length=12)


class ThemeNaming(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=3, max_length=800)
    coherence: float = Field(ge=0, le=1, description="How clearly the pain points share one underlying problem.")


class ClusterGrouping(BaseModel):
    groups: list[list[int]] = Field(
        description="Each inner list holds the numbers of clusters that describe the SAME underlying problem."
    )


class ContradictionCheck(BaseModel):
    contradicts: bool
    explanation: str = Field(default="", max_length=600)
    quote: str = Field(default="", max_length=1000, description="EXACT excerpt from the candidate text, or empty.")


class InsightDraft(BaseModel):
    statement: str = Field(min_length=3, max_length=800, description="What we learned, grounded in the evidence.")
    implication: str = Field(min_length=3, max_length=800, description="Suggested product implication.")
    severity: int = Field(ge=1, le=5)
    strategic_relevance: int = Field(ge=1, le=5, description="Relevance to the stated research objectives.")
