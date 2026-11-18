"""Module H — research repository: search past findings across projects.

Modes
- keyword:  case-insensitive match in theme names/descriptions/implications, evidence quotes
            and notes, and insight text.
- theme:    match theme names only.
- semantic: embed the query with the configured embedder and rank themes, pain points
            (mapped back to their themes) and insights by pgvector cosine similarity.

Only "live" findings are searched (the active synthesis run of each project plus manual
items); rejected and merged findings are excluded. Every theme hit carries its evidence
with links back to the original interviews.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.ai.embeddings import Embedder
from app.models import Insight, Interview, PainPoint, ResearchProject, Theme, ThemeEvidence
from app.models.enums import EvidenceStance, ReviewStatus
from app.services.review import priority_band

Mode = Literal["keyword", "semantic", "theme"]
MIN_SIMILARITY = 0.15


@dataclass
class Filters:
    project_id: uuid.UUID | None = None
    role: str | None = None
    company_size: str | None = None
    plan_tier: str | None = None
    approved_only: bool = False


def _live(model):
    return and_(
        model.project_id == ResearchProject.id,
        or_(model.run_id == ResearchProject.active_run_id, model.run_id.is_(None)),
        model.status.notin_([ReviewStatus.REJECTED, ReviewStatus.MERGED]),
    )


def _segment_clause(f: Filters):
    conds = []
    if f.role:
        conds.append(Interview.participant_role.ilike(f"%{f.role}%"))
    if f.company_size:
        conds.append(Interview.company_size == f.company_size)
    if f.plan_tier:
        conds.append(Interview.plan_tier == f.plan_tier)
    if not conds:
        return None
    return exists(
        select(ThemeEvidence.id)
        .join(Interview, Interview.id == ThemeEvidence.interview_id)
        .where(ThemeEvidence.theme_id == Theme.id, ThemeEvidence.stance == EvidenceStance.SUPPORTING, *conds)
    )


def _theme_base(f: Filters):
    stmt = select(Theme, ResearchProject).join(ResearchProject, _live(Theme))
    if f.project_id:
        stmt = stmt.where(Theme.project_id == f.project_id)
    if f.approved_only:
        stmt = stmt.where(Theme.status == ReviewStatus.APPROVED)
    seg = _segment_clause(f)
    if seg is not None:
        stmt = stmt.where(seg)
    return stmt.options(selectinload(Theme.evidence))


def _insight_base(f: Filters):
    stmt = (
        select(Insight, ResearchProject, Theme.code)
        .join(ResearchProject, _live(Insight))
        .outerjoin(Theme, Theme.id == Insight.theme_id)
    )
    if f.project_id:
        stmt = stmt.where(Insight.project_id == f.project_id)
    if f.approved_only:
        stmt = stmt.where(Insight.status == ReviewStatus.APPROVED)
    seg = _segment_clause(f)
    if seg is not None:
        # Insights match a segment through their theme's evidence.
        stmt = stmt.where(Insight.theme_id.in_(select(Theme.id).where(seg)))
    return stmt


def _theme_hit(t: Theme, p: ResearchProject, score: float | None, needle: str | None) -> dict:
    supporting = [e for e in t.evidence if e.stance == EvidenceStance.SUPPORTING]
    contradicting = [e for e in t.evidence if e.stance == EvidenceStance.CONTRADICTING]
    if needle:
        n = needle.lower()
        supporting.sort(key=lambda e: n not in (e.quote + " " + e.note).lower())
    evidence = [
        {
            "id": str(e.id),
            "interview_id": str(e.interview_id),
            "participant_id": e.participant_id,
            "quote": e.quote,
            "quote_verified": e.quote_verified,
            "note": e.note,
            "stance": e.stance,
        }
        for e in supporting[:4] + contradicting[:2]
    ]
    return {
        "kind": "theme",
        "id": str(t.id),
        "project_id": str(p.id),
        "project_name": p.name,
        "project_status": p.status,
        "code": t.code,
        "title": t.name,
        "description": t.description,
        "implication": t.implication,
        "participant_ids": t.participant_ids,
        "participant_count": t.participant_count,
        "total_participants": t.total_participants,
        "frequency": t.frequency,
        "severity": t.severity,
        "status": t.status,
        "requires_approval": t.requires_approval,
        "sensitive_tags": t.sensitive_tags,
        "is_outlier": t.is_outlier,
        "has_contradictions": t.has_contradictions,
        "score": None if score is None else round(score, 3),
        "evidence_count": len(t.evidence),
        "evidence": evidence,
        "priority": None,
        "created_at": t.created_at.isoformat(),
    }


def _insight_hit(i: Insight, p: ResearchProject, code: str | None, score: float | None) -> dict:
    return {
        "kind": "insight",
        "id": str(i.id),
        "project_id": str(p.id),
        "project_name": p.name,
        "project_status": p.status,
        "code": code,
        "title": i.title,
        "description": i.statement,
        "implication": i.implication,
        "participant_ids": [],
        "participant_count": None,
        "total_participants": None,
        "frequency": i.frequency,
        "severity": i.severity,
        "status": i.status,
        "requires_approval": i.requires_approval,
        "sensitive_tags": i.sensitive_tags,
        "is_outlier": i.is_outlier,
        "has_contradictions": False,
        "score": None if score is None else round(score, 3),
        "evidence_count": 0,
        "evidence": [],
        "priority": i.priority_override or priority_band(i.priority_score),
        "created_at": i.created_at.isoformat(),
    }


def search(
    db: Session, q: str, mode: Mode, f: Filters, embedder: Embedder | None, limit: int = 30
) -> list[dict]:
    q = (q or "").strip()
    hits: list[dict] = []

    if mode == "semantic" and q:
        vec = embedder.embed([q])[0]
        theme_rows = db.execute(
            _theme_base(f)
            .add_columns((1 - Theme.embedding.cosine_distance(vec)).label("sim"))
            .where(Theme.embedding.is_not(None))
            .order_by(Theme.embedding.cosine_distance(vec))
            .limit(limit)
        ).all()
        best: dict[uuid.UUID, tuple[Theme, ResearchProject, float]] = {
            t.id: (t, p, float(sim)) for t, p, sim in theme_rows
        }
        # Pain points catch specific wording a theme summary may not contain.
        pp_rows = db.execute(
            select(ThemeEvidence.theme_id, (1 - PainPoint.embedding.cosine_distance(vec)).label("sim"))
            .join(PainPoint, PainPoint.id == ThemeEvidence.pain_point_id)
            .where(PainPoint.embedding.is_not(None))
            .order_by(PainPoint.embedding.cosine_distance(vec))
            .limit(limit * 3)
        ).all()
        pp_best: dict[uuid.UUID, float] = {}
        for theme_id, sim in pp_rows:
            pp_best[theme_id] = max(pp_best.get(theme_id, -1.0), float(sim))
        missing = [tid for tid in pp_best if tid not in best]
        if missing:
            for t, p in db.execute(_theme_base(f).where(Theme.id.in_(missing))).all():
                best[t.id] = (t, p, pp_best[t.id])
        for tid, sim in pp_best.items():
            if tid in best and sim > best[tid][2]:
                t, p, _ = best[tid]
                best[tid] = (t, p, sim)
        hits += [_theme_hit(t, p, sim, None) for t, p, sim in best.values() if sim >= MIN_SIMILARITY]

        ins_rows = db.execute(
            _insight_base(f)
            .add_columns((1 - Insight.embedding.cosine_distance(vec)).label("sim"))
            .where(Insight.embedding.is_not(None), Insight.theme_id.is_(None))
            .order_by(Insight.embedding.cosine_distance(vec))
            .limit(limit)
        ).all()
        hits += [_insight_hit(i, p, code, float(sim)) for i, p, code, sim in ins_rows if sim >= MIN_SIMILARITY]
        hits.sort(key=lambda h: -(h["score"] or 0))
        return hits[:limit]

    like = f"%{q}%"
    stmt = _theme_base(f)
    if q and mode == "theme":
        stmt = stmt.where(Theme.name.ilike(like))
    elif q:
        stmt = stmt.where(
            or_(
                Theme.name.ilike(like),
                Theme.description.ilike(like),
                Theme.implication.ilike(like),
                exists(
                    select(ThemeEvidence.id).where(
                        ThemeEvidence.theme_id == Theme.id,
                        or_(ThemeEvidence.quote.ilike(like), ThemeEvidence.note.ilike(like)),
                    )
                ),
            )
        )
    stmt = stmt.order_by(Theme.participant_count.desc(), Theme.created_at.desc()).limit(limit)
    hits += [_theme_hit(t, p, None, q or None) for t, p in db.execute(stmt).all()]

    if mode == "keyword":
        istmt = _insight_base(f).where(Insight.theme_id.is_(None))
        if q:
            istmt = istmt.where(
                or_(Insight.title.ilike(like), Insight.statement.ilike(like), Insight.implication.ilike(like))
            )
        hits += [_insight_hit(i, p, code, None) for i, p, code in db.execute(istmt.limit(limit)).all()]
    return hits[:limit]


def facets(db: Session) -> dict:
    projects = db.execute(
        select(ResearchProject.id, ResearchProject.name, ResearchProject.status)
        .where(ResearchProject.active_run_id.is_not(None))
        .order_by(ResearchProject.name)
    ).all()
    ids = [p.id for p in projects]

    def distinct(col):
        if not ids:
            return []
        return [
            v
            for (v,) in db.execute(
                select(col).where(Interview.project_id.in_(ids), func.length(col) > 0).distinct().order_by(col)
            ).all()
        ]

    return {
        "projects": [{"id": str(p.id), "name": p.name, "status": p.status} for p in projects],
        "roles": distinct(Interview.participant_role),
        "company_sizes": distinct(Interview.company_size),
        "plan_tiers": distinct(Interview.plan_tier),
    }
