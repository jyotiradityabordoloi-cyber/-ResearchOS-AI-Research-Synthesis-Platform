"""Synthesis run lifecycle: start, execute in the background, persist atomically.

Safety guarantees (Test 6):
- The pipeline runs fully in memory. Results are written in ONE transaction at the end.
- On any failure the transaction is rolled back, the run is marked `failed` with the
  error, and the project's `active_run_id` (the previous good synthesis) is untouched.
"""

from __future__ import annotations

import logging
import traceback
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai.embeddings import Embedder
from app.ai.engine import AIEngine
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models import Insight, Interview, PainPoint, ResearchProject, SynthesisRun, Theme, ThemeEvidence, User
from app.models.enums import (
    EvidenceStance,
    Origin,
    ProjectStatus,
    ReviewStatus,
    SynthesisStatus,
    ValidationStatus,
)
from app.services.pipeline import InterviewRecord, PipelineResult, run_pipeline

log = logging.getLogger(__name__)
STALE_AFTER = timedelta(minutes=30)


class SynthesisRefused(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def _valid_interviews(db: Session, project_id: uuid.UUID) -> list[Interview]:
    return list(
        db.scalars(
            select(Interview)
            .where(Interview.project_id == project_id, Interview.validation_status == ValidationStatus.VALID)
            .order_by(Interview.created_at)
        )
    )


def start_run(
    db: Session,
    project: ResearchProject,
    user: User | None,
    engine: AIEngine,
    embedder: Embedder,
    force: bool = False,
) -> SynthesisRun:
    """Validate preconditions and create a `running` run row. Execution happens separately."""
    now = datetime.now(UTC)
    active = db.scalar(
        select(SynthesisRun).where(
            SynthesisRun.project_id == project.id, SynthesisRun.status == SynthesisStatus.RUNNING
        )
    )
    if active is not None:
        if now - active.started_at < STALE_AFTER:
            raise SynthesisRefused(409, "A synthesis run is already in progress for this project.")
        active.status = SynthesisStatus.FAILED
        active.error = "Run abandoned (no progress for 30 minutes)."
        active.finished_at = now

    interviews = _valid_interviews(db, project.id)
    participants = {i.participant_id.strip().lower() for i in interviews}
    minimum = get_settings().min_interviews_for_synthesis
    if not interviews:
        raise SynthesisRefused(422, "No valid interviews. Fix validation errors before running synthesis.")
    warnings: list[dict[str, str]] = []
    if len(participants) < minimum:
        if not force:
            raise SynthesisRefused(
                422,
                f"Only {len(participants)} valid participant(s); standard synthesis needs at least {minimum}. "
                "Add interviews, or run anyway with force=true to get an exploratory synthesis.",
            )
        warnings.append(
            {
                "code": "insufficient_sample",
                "message": f"Exploratory synthesis on {len(participants)} participant(s) (fewer than {minimum}). "
                "Findings are not representative.",
            }
        )

    run = SynthesisRun(
        project_id=project.id,
        status=SynthesisStatus.RUNNING,
        stage="queued",
        provider=engine.name,
        model=engine.model,
        embedding_provider=f"{embedder.name}:{embedder.model}",
        warnings=warnings,
        stats={"forced": force},
        triggered_by_id=user.id if user else None,
    )
    db.add(run)
    project.synthesis_status = SynthesisStatus.RUNNING
    db.commit()
    db.refresh(run)
    return run


def _set_stage(run_id: uuid.UUID, stage: str) -> None:
    """Progress is committed in its own short transaction so the UI can poll it."""
    with SessionLocal() as s:
        s.execute(update(SynthesisRun).where(SynthesisRun.id == run_id).values(stage=stage))
        s.commit()


def execute_run(run_id: uuid.UUID, engine: AIEngine, embedder: Embedder) -> None:
    with SessionLocal() as db:
        run = db.get(SynthesisRun, run_id)
        if run is None:
            return
        project = db.get(ResearchProject, run.project_id)
        records = [
            InterviewRecord(
                id=i.id,
                participant_id=i.participant_id,
                participant_role=i.participant_role,
                company_size=i.company_size,
                plan_tier=i.plan_tier,
                pain=i.pain,
                behavior=i.behavior,
                verbatim_quote=i.verbatim_quote,
                raw_content=i.raw_content,
            )
            for i in _valid_interviews(db, run.project_id)
        ]
        objectives = list(project.objectives or [])
        prior_warnings = list(run.warnings or [])
        prior_stats = dict(run.stats or {})

    try:
        result = run_pipeline(records, objectives, engine, embedder, progress=lambda st: _set_stage(run_id, st))
        with SessionLocal() as db:
            _persist(db, run_id, result, prior_warnings, prior_stats)
            db.commit()
    except Exception as exc:  # noqa: BLE001 - any failure must leave data consistent
        log.exception("Synthesis run %s failed", run_id)
        with SessionLocal() as db:
            run = db.get(SynthesisRun, run_id)
            project = db.get(ResearchProject, run.project_id)
            run.status = SynthesisStatus.FAILED
            run.stage = "failed"
            run.error = f"{exc.__class__.__name__}: {exc}"[:2000]
            run.stats = {**prior_stats, "traceback": traceback.format_exc()[-2000:]}
            run.finished_at = datetime.now(UTC)
            project.synthesis_status = SynthesisStatus.FAILED
            db.commit()


def _persist(
    db: Session,
    run_id: uuid.UUID,
    result: PipelineResult,
    prior_warnings: list[dict[str, str]],
    prior_stats: dict,
) -> None:
    run = db.get(SynthesisRun, run_id)
    project = db.get(ResearchProject, run.project_id)

    pp_rows: dict[int, PainPoint] = {}
    for p in result.pain_points:
        row = PainPoint(
            project_id=project.id,
            run_id=run.id,
            interview_id=p.interview.id,
            participant_id=p.interview.participant_id,
            text=p.text,
            quote=p.quote or None,
            quote_verified=p.quote_verified,
            source_field=p.source_field,
            duplicate_count=p.duplicate_count,
            severity=p.severity,
            sensitive_tags=p.sensitive_tags,
            embedding=p.embedding,
        )
        db.add(row)
        pp_rows[id(p)] = row
    db.flush()

    for t in result.themes:
        theme = Theme(
            project_id=project.id,
            run_id=run.id,
            code=t.code,
            name=t.name[:300],
            description=t.description,
            implication=t.implication,
            participant_ids=t.participant_ids,
            participant_count=t.participant_count,
            total_participants=t.total_participants,
            frequency=t.frequency,
            confidence=t.confidence,
            severity=t.severity,
            evidence_status=t.evidence_status,
            is_outlier=t.is_outlier,
            is_low_confidence=t.is_low_confidence,
            has_contradictions=t.has_contradictions,
            sensitive_tags=t.sensitive_tags,
            requires_approval=t.requires_approval,
            status=ReviewStatus.PROPOSED,
            origin=Origin.AI,
            embedding=t.embedding,
        )
        db.add(theme)
        db.flush()
        for e in t.evidence:
            db.add(
                ThemeEvidence(
                    theme_id=theme.id,
                    interview_id=e.interview.id,
                    pain_point_id=pp_rows[id(e.pain_point)].id if e.pain_point is not None else None,
                    participant_id=e.interview.participant_id,
                    quote=e.quote,
                    quote_verified=e.quote_verified,
                    source_field=e.source_field,
                    stance=EvidenceStance(e.stance),
                    note=e.note,
                )
            )
        db.add(
            Insight(
                project_id=project.id,
                run_id=run.id,
                theme_id=theme.id,
                title=t.name[:300],
                statement=t.statement,
                implication=t.implication,
                frequency=t.frequency,
                severity=t.severity,
                strategic_relevance=t.strategic_relevance,
                confidence=t.confidence,
                priority_score=t.priority_score,
                is_outlier=t.is_outlier,
                sensitive_tags=t.sensitive_tags,
                requires_approval=t.requires_approval,
                status=ReviewStatus.PROPOSED,
                origin=Origin.AI,
                embedding=t.embedding,
            )
        )

    run.status = SynthesisStatus.COMPLETED
    run.stage = "completed"
    run.warnings = prior_warnings + result.warnings
    run.stats = {**prior_stats, **result.stats}
    run.finished_at = datetime.now(UTC)
    project.active_run_id = run.id
    project.synthesis_status = SynthesisStatus.COMPLETED
    if project.status in (ProjectStatus.DRAFT, ProjectStatus.COLLECTING):
        project.status = ProjectStatus.IN_REVIEW
