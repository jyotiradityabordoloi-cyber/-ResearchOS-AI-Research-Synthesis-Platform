"""Traceability from one interview forward: what synthesis made of it.

The reverse direction (theme -> quote -> interview) already exists on every piece of
evidence; this closes the loop so a researcher can open an interview and see which
pain points were extracted from it and which live themes and insights it supports
or contradicts.
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Insight, Interview, PainPoint, ResearchProject, Theme, ThemeEvidence
from app.models.enums import ReviewStatus
from app.schemas import (
    FacetValue,
    InterviewFacets,
    InterviewFindings,
    InterviewInsightLink,
    InterviewPainPoint,
    InterviewThemeLink,
    ThemeQuote,
)
from app.services.projects import live_filter
from app.services.review import priority_band


def interview_findings(db: Session, interview: Interview) -> InterviewFindings:
    project = db.get(ResearchProject, interview.project_id)
    run_id = project.active_run_id if project else None

    theme_by_point: dict[uuid.UUID, Theme] = {}
    themes: dict[uuid.UUID, InterviewThemeLink] = {}
    rows = db.execute(
        select(ThemeEvidence, Theme)
        .join(Theme, Theme.id == ThemeEvidence.theme_id)
        .where(
            ThemeEvidence.interview_id == interview.id,
            live_filter(Theme, project),
            Theme.status != ReviewStatus.MERGED,
        )
        .order_by(Theme.code, ThemeEvidence.created_at)
    ).all()
    for ev, theme in rows:
        if ev.pain_point_id:
            theme_by_point[ev.pain_point_id] = theme
        link = themes.get(theme.id)
        if link is None:
            link = themes[theme.id] = InterviewThemeLink(
                theme_id=theme.id,
                code=theme.code,
                name=theme.name,
                status=theme.status,
                frequency=theme.frequency,
                participant_count=theme.participant_count,
                is_outlier=theme.is_outlier,
                requires_approval=theme.requires_approval,
                quotes=[],
            )
        link.quotes.append(ThemeQuote(quote=ev.quote, stance=ev.stance, verified=ev.quote_verified, note=ev.note))

    points = []
    if run_id:
        for pp in db.scalars(
            select(PainPoint)
            .where(PainPoint.interview_id == interview.id, PainPoint.run_id == run_id)
            .order_by(PainPoint.created_at)
        ):
            theme = theme_by_point.get(pp.id)
            points.append(
                InterviewPainPoint(
                    id=pp.id,
                    text=pp.text,
                    quote=pp.quote,
                    quote_verified=pp.quote_verified,
                    severity=pp.severity,
                    sensitive_tags=pp.sensitive_tags,
                    duplicate_count=pp.duplicate_count,
                    theme_id=theme.id if theme else None,
                    theme_code=theme.code if theme else None,
                    theme_name=theme.name if theme else None,
                )
            )

    insights = []
    if themes:
        for ins in db.scalars(
            select(Insight)
            .where(Insight.theme_id.in_(themes), live_filter(Insight, project))
            .order_by(Insight.priority_score.desc())
        ):
            insights.append(
                InterviewInsightLink(
                    id=ins.id,
                    title=ins.title,
                    status=ins.status,
                    priority=ins.priority_override or priority_band(ins.priority_score),
                    theme_code=themes[ins.theme_id].code,
                )
            )

    return InterviewFindings(
        synthesised=run_id is not None,
        pain_points=points,
        themes=list(themes.values()),
        insights=insights,
    )


def interview_facets(db: Session, project_id: uuid.UUID | None = None) -> InterviewFacets:
    def counts(col) -> list[FacetValue]:
        stmt = select(col, func.count()).where(func.length(col) > 0).group_by(col).order_by(func.count().desc(), col)
        if project_id:
            stmt = stmt.where(Interview.project_id == project_id)
        return [FacetValue(value=v, count=n) for v, n in db.execute(stmt).all()]

    return InterviewFacets(
        roles=counts(Interview.participant_role),
        company_sizes=counts(Interview.company_size),
        plan_tiers=counts(Interview.plan_tier),
    )
