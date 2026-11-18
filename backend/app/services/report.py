"""Module G — research report generation (pipeline stage 9).

Reports are assembled deterministically from reviewed data; nothing is invented.
Inclusion rules:
- Rejected and merged findings are never included.
- Sensitive findings (pricing / churn / competitive switching) are included only once a
  person has approved them (fallback rule D). Withheld items are counted in the report.
- A "draft" report includes approved and not-yet-reviewed findings (marked as unreviewed).
- An "approved" report includes approved findings only, needs at least one approved theme,
  and marks the project as completed so it lives on in the repository.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Insight, Interview, ResearchProject, ResearchReport, SynthesisRun, Theme, User
from app.models.enums import EvidenceStance, ProjectStatus, ReportStatus, ReviewStatus, ValidationStatus
from app.services import audit
from app.services.review import priority_band

ReportKind = Literal["draft", "approved"]

SECTION_TITLES = [
    "Research objective",
    "Participant overview",
    "Research methodology",
    "Top recurring themes",
    "Participant frequency",
    "Supporting quotes",
    "Contradictory findings",
    "High-impact outliers",
    "Product implications",
    "Recommended next steps",
    "Limitations",
]
_PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
_TAG_LABEL = {"pricing": "pricing", "churn": "churn", "competitive_switching": "competitive switching"}


class ReportError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


def _included(status: str, requires_approval: bool, kind: ReportKind) -> bool:
    if status in (ReviewStatus.REJECTED, ReviewStatus.MERGED):
        return False
    if requires_approval and status != ReviewStatus.APPROVED:
        return False
    return status == ReviewStatus.APPROVED or kind == "draft"


def build_report_content(db: Session, project: ResearchProject, kind: ReportKind) -> dict[str, Any]:
    if project.active_run_id is None:
        raise ReportError(422, "Run synthesis before generating a report.")
    run = db.get(SynthesisRun, project.active_run_id)
    themes = list(
        db.scalars(
            select(Theme)
            .options(selectinload(Theme.evidence))
            .where(
                Theme.project_id == project.id,
                (Theme.run_id == project.active_run_id) | Theme.run_id.is_(None),
            )
        )
    )
    insights = list(
        db.execute(
            select(Insight, Theme.code)
            .outerjoin(Theme, Theme.id == Insight.theme_id)
            .where(
                Insight.project_id == project.id,
                (Insight.run_id == project.active_run_id) | Insight.run_id.is_(None),
            )
        ).all()
    )
    interviews = list(db.scalars(select(Interview).where(Interview.project_id == project.id)))
    valid = [i for i in interviews if i.validation_status == ValidationStatus.VALID]

    kept = [t for t in themes if _included(t.status, t.requires_approval, kind)]
    if kind == "approved" and not kept:
        raise ReportError(422, "Approve at least one theme before generating an approved report.")
    live = [t for t in themes if t.status not in (ReviewStatus.REJECTED, ReviewStatus.MERGED)]
    withheld_sensitive = [t for t in live if t.requires_approval and t.status != ReviewStatus.APPROVED]
    unreviewed_excluded = [
        t for t in live if kind == "approved" and t.status == ReviewStatus.PROPOSED and not t.requires_approval
    ]
    rejected = [t for t in themes if t.status == ReviewStatus.REJECTED]
    kept.sort(key=lambda t: (-t.participant_count, -t.confidence, t.code))
    kept_ids = {t.id for t in kept}

    def theme_ref(t: Theme) -> dict[str, Any]:
        supporting = [e for e in t.evidence if e.stance == EvidenceStance.SUPPORTING and e.quote_verified and e.quote]
        contradicting = [e for e in t.evidence if e.stance == EvidenceStance.CONTRADICTING]
        return {
            "id": str(t.id),
            "code": t.code,
            "name": t.name,
            "description": t.description,
            "implication": t.implication,
            "status": t.status,
            "reviewed": t.status == ReviewStatus.APPROVED,
            "participant_ids": t.participant_ids,
            "participant_count": t.participant_count,
            "total_participants": t.total_participants,
            "frequency": t.frequency,
            "confidence": t.confidence,
            "severity": t.severity,
            "strategic_flag": t.strategic_flag,
            "sensitive_tags": t.sensitive_tags,
            "is_outlier": t.is_outlier,
            "is_low_confidence": t.is_low_confidence,
            "evidence_status": t.evidence_status,
            "quotes": [
                {"participant_id": e.participant_id, "quote": e.quote, "interview_id": str(e.interview_id)}
                for e in supporting
            ],
            "contradictions": [
                {
                    "participant_id": e.participant_id,
                    "quote": e.quote if e.quote_verified else "",
                    "note": e.note,
                    "interview_id": str(e.interview_id),
                }
                for e in contradicting
            ],
        }

    theme_refs = [theme_ref(t) for t in kept]
    recurring = [t for t in theme_refs if not t["is_outlier"]]
    outliers = sorted((t for t in theme_refs if t["is_outlier"]), key=lambda t: -t["severity"])

    implications = []
    for i, code in insights:
        if not _included(i.status, i.requires_approval, kind):
            continue
        if i.theme_id is not None and i.theme_id not in kept_ids:
            continue
        computed = priority_band(i.priority_score)
        implications.append(
            {
                "title": i.title,
                "statement": i.statement,
                "implication": i.implication,
                "theme_code": code,
                "priority": i.priority_override or computed,
                "computed_priority": computed,
                "overridden": i.priority_override is not None,
                "override_reason": i.override_reason,
                "frequency": i.frequency,
                "severity": i.severity,
                "strategic_relevance": i.strategic_relevance,
                "confidence": i.confidence,
                "pm_comment": i.pm_comment,
                "origin": i.origin,
                "reviewed": i.status == ReviewStatus.APPROVED,
            }
        )
    implications.sort(key=lambda x: (_PRIORITY_RANK[x["priority"]], -x["severity"], -x["frequency"]))

    participants = {i.participant_id.strip().lower(): i for i in valid}
    participant_overview = {
        "total_interviews": len(interviews),
        "valid_interviews": len(valid),
        "unique_participants": len(participants),
        "roles": dict(Counter(i.participant_role or "Unspecified" for i in participants.values()).most_common()),
        "company_sizes": dict(Counter(i.company_size or "Unspecified" for i in participants.values()).most_common()),
        "plan_tiers": dict(Counter(i.plan_tier or "Unspecified" for i in participants.values()).most_common()),
        "target_segments": project.target_segments,
    }

    is_demo = run.provider == "demo"
    stats = run.stats or {}
    methodology = [
        f"{len(valid)} validated interview notes from {len(participants)} unique participants were analysed "
        f"({len(interviews) - len(valid)} interview(s) excluded for failing validation).",
        "Pain points were extracted per interview, embedded, de-duplicated within each participant and grouped "
        "into themes by similarity. Theme frequency is the number of unique participants mentioning a theme "
        "divided by the total number of participants, calculated in code rather than by the AI.",
        "Every quote shown was checked word-for-word against the original notes; quotes that could not be "
        "verified were discarded.",
        f"Synthesis engine: {run.provider} ({run.model}); embeddings: {run.embedding_provider}."
        + (" This was the offline demo mode: rule-based and illustrative, not an AI model." if is_demo else ""),
        "Findings were reviewed by the research team: themes were approved, rejected, merged or regrouped, "
        "and priorities adjusted where judgement differed from the computed score.",
    ]

    next_steps: list[str] = []
    for x in implications[:3]:
        if x["priority"] == "high":
            next_steps.append(f"Act on “{x['title']}”: {x['implication'] or x['statement']}")
    for t in outliers:
        if t["severity"] >= 4:
            next_steps.append(
                f"Validate “{t['name']}” with more participants: it is high-impact but came from one person "
                f"({', '.join(t['participant_ids'])})."
            )
    for t in theme_refs:
        if t["contradictions"]:
            who = ", ".join(sorted({c["participant_id"] for c in t["contradictions"]}))
            next_steps.append(f"Follow up with {who} to understand why their experience of “{t['name']}” differs.")
    low = [t["name"] for t in theme_refs if t["is_low_confidence"]]
    if low:
        next_steps.append("Re-check the grouping of low-confidence themes: " + "; ".join(f"“{n}”" for n in low) + ".")
    if withheld_sensitive:
        next_steps.append(
            f"Review {len(withheld_sensitive)} sensitive finding(s) (pricing, churn or competitive switching) "
            "awaiting approval before sharing them."
        )
    if len(participants) < 8:
        next_steps.append("Interview more participants: fewer than 8 limits how far these patterns can be trusted.")
    if not next_steps:
        next_steps.append("Share this report with the team and decide which implications to put on the roadmap.")

    limitations = [
        f"Small qualitative sample ({len(participants)} participants). Frequencies describe this sample only "
        "and are not statistically representative.",
        "Findings are based on interviewer notes; verbatim quotes are only as accurate as the notes taken.",
        "Frequency counts how many participants mentioned a problem, not how severe or widespread it is in the "
        "user base. Severity and strategic relevance are judgements.",
    ]
    if stats.get("forced"):
        limitations.append("Synthesis was run on fewer participants than the recommended minimum.")
    if is_demo:
        limitations.append("Themes were produced by the offline demo engine (keyword rules), not an AI model.")
    if stats.get("unverified_quotes"):
        limitations.append(f"{stats['unverified_quotes']} AI-suggested quote(s) failed verification and were left out.")
    if withheld_sensitive:
        limitations.append(
            f"{len(withheld_sensitive)} sensitive finding(s) are withheld until approved: "
            + ", ".join(sorted({_TAG_LABEL.get(tag, tag) for t in withheld_sensitive for tag in t.sensitive_tags}))
            + "."
        )
    if unreviewed_excluded:
        limitations.append(f"{len(unreviewed_excluded)} theme(s) not yet reviewed are excluded from this approved report.")
    if kind == "draft" and any(not t["reviewed"] for t in theme_refs):
        limitations.append("This is a draft: findings marked “unreviewed” have not been approved by the team yet.")
    if project.target_segments:
        limitations.append(
            "Target segments: " + ", ".join(project.target_segments)
            + ". Check that each segment is represented before generalising."
        )

    return {
        "kind": kind,
        "generated_at": datetime.now(UTC).isoformat(),
        "project": {
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
            "objectives": project.objectives,
            "target_segments": project.target_segments,
        },
        "run": {
            "id": str(run.id),
            "provider": run.provider,
            "model": run.model,
            "embedding_provider": run.embedding_provider,
            "is_demo": is_demo,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        },
        "section_titles": SECTION_TITLES,
        "sections": {
            "objective": {"objectives": project.objectives, "context": project.description},
            "participants": participant_overview,
            "methodology": methodology,
            "themes": recurring,
            "frequency": [
                {k: t[k] for k in ("code", "name", "participant_count", "total_participants", "frequency", "is_outlier")}
                for t in theme_refs
            ],
            "quotes": [{"code": t["code"], "name": t["name"], "quotes": t["quotes"]} for t in theme_refs],
            "contradictions": [
                {"code": t["code"], "name": t["name"], **c} for t in theme_refs for c in t["contradictions"]
            ],
            "outliers": outliers,
            "implications": implications,
            "next_steps": next_steps,
            "limitations": limitations,
        },
        "excluded": {
            "sensitive_pending": [{"code": t.code, "name": t.name, "tags": t.sensitive_tags} for t in withheld_sensitive],
            "unreviewed": len(unreviewed_excluded),
            "rejected": len(rejected),
        },
    }


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def _md_escape(text: str) -> str:
    return (text or "").replace("\n", " ").strip()


def to_markdown(c: dict[str, Any], title: str) -> str:
    s = c["sections"]
    p = s["participants"]
    out: list[str] = [f"# {title}", ""]
    status = "Approved report" if c["kind"] == "approved" else "DRAFT — not all findings reviewed"
    out += [
        f"**Project:** {c['project']['name']}  ",
        f"**Status:** {status}  ",
        f"**Generated:** {c['generated_at'][:16].replace('T', ' ')} UTC  ",
        f"**Synthesis:** {c['run']['provider']} · {c['run']['model']}" + (" (offline demo mode)" if c["run"]["is_demo"] else ""),
        "",
    ]
    n = iter(range(1, 12))

    out += [f"## {next(n)}. Research objective", ""]
    out += [f"- {o}" for o in s["objective"]["objectives"]] or ["_No objectives recorded._"]
    if s["objective"]["context"]:
        out += ["", s["objective"]["context"]]

    out += ["", f"## {next(n)}. Participant overview", ""]
    out += [
        f"- **{p['unique_participants']}** unique participants ({p['valid_interviews']} valid of "
        f"{p['total_interviews']} interviews)",
        "- **Roles:** " + ", ".join(f"{k} ({v})" for k, v in p["roles"].items()),
        "- **Company size:** " + ", ".join(f"{k} ({v})" for k, v in p["company_sizes"].items()),
        "- **Plan tier:** " + ", ".join(f"{k} ({v})" for k, v in p["plan_tiers"].items()),
    ]
    if p["target_segments"]:
        out.append("- **Target segments:** " + ", ".join(p["target_segments"]))

    out += ["", f"## {next(n)}. Research methodology", ""] + [f"- {m}" for m in s["methodology"]]

    out += ["", f"## {next(n)}. Top recurring themes", ""]
    if not s["themes"]:
        out.append("_No recurring themes in this report._")
    for t in s["themes"]:
        tags = []
        if not t["reviewed"]:
            tags.append("unreviewed")
        if t["strategic_flag"]:
            tags.append("strategic")
        if t["sensitive_tags"]:
            tags.append("sensitive, approved")
        if t["is_low_confidence"]:
            tags.append("low confidence")
        suffix = f" _({', '.join(tags)})_" if tags else ""
        out += [
            f"### {t['code']} · {t['name']}{suffix}",
            "",
            t["description"],
            "",
            f"- **Participants:** {t['participant_count']} of {t['total_participants']} ({_pct(t['frequency'])}) — "
            + ", ".join(t["participant_ids"]),
            f"- **Severity:** {t['severity']}/5 · **Confidence:** {_pct(t['confidence'])}",
        ]
        if t["implication"]:
            out.append(f"- **Implication:** {t['implication']}")
        out.append("")

    out += [f"## {next(n)}. Participant frequency", "", "| Theme | Participants | Frequency |", "|---|---|---|"]
    for f in s["frequency"]:
        label = f"{f['code']} · {_md_escape(f['name'])}" + (" (outlier)" if f["is_outlier"] else "")
        out.append(f"| {label} | {f['participant_count']} of {f['total_participants']} | {_pct(f['frequency'])} |")

    out += ["", f"## {next(n)}. Supporting quotes", ""]
    for q in s["quotes"]:
        out += [f"**{q['code']} · {q['name']}**", ""]
        if not q["quotes"]:
            out += ["_No verified quote available._", ""]
        for item in q["quotes"]:
            out += [f"> “{_md_escape(item['quote'])}” — {item['participant_id']}", ""]

    out += [f"## {next(n)}. Contradictory findings", ""]
    if not s["contradictions"]:
        out.append("_No contradicting evidence was found._")
    for x in s["contradictions"]:
        quote = f" “{_md_escape(x['quote'])}”" if x["quote"] else ""
        out.append(f"- **{x['code']} · {x['name']}** — {x['participant_id']}:{quote} {_md_escape(x['note'])}".rstrip())

    out += ["", f"## {next(n)}. High-impact outliers", ""]
    if not s["outliers"]:
        out.append("_No single-participant findings._")
    for t in s["outliers"]:
        impact = "High-impact" if t["severity"] >= 4 else "Single-participant"
        out.append(
            f"- **{t['name']}** ({impact}, severity {t['severity']}/5, {', '.join(t['participant_ids'])}): "
            f"{_md_escape(t['description'])}"
        )

    out += ["", f"## {next(n)}. Product implications", ""]
    if not s["implications"]:
        out.append("_No implications included._")
    out += ["| Priority | Insight | Implication | Frequency | Severity | Strategic |", "|---|---|---|---|---|---|"]
    for x in s["implications"]:
        prio = x["priority"].title() + (f" (manual; computed {x['computed_priority']})" if x["overridden"] else "")
        name = (f"{x['theme_code']} · " if x["theme_code"] else "") + _md_escape(x["title"])
        out.append(
            f"| {prio} | {name} | {_md_escape(x['implication'])} | {_pct(x['frequency'])} | "
            f"{x['severity']}/5 | {x['strategic_relevance']}/5 |"
        )

    out += ["", f"## {next(n)}. Recommended next steps", ""] + [f"{i}. {x}" for i, x in enumerate(s["next_steps"], 1)]
    out += ["", f"## {next(n)}. Limitations", ""] + [f"- {x}" for x in s["limitations"]]
    return "\n".join(out).strip() + "\n"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def generate_report(
    db: Session, project: ResearchProject, kind: ReportKind, title: str | None, user: User
) -> ResearchReport:
    content = build_report_content(db, project, kind)
    title = (title or "").strip() or f"{project.name} — {'research report' if kind == 'approved' else 'draft report'}"
    report = ResearchReport(
        project_id=project.id,
        run_id=project.active_run_id,
        title=title[:300],
        status=ReportStatus.APPROVED if kind == "approved" else ReportStatus.DRAFT,
        content_markdown=to_markdown(content, title),
        content_json=content,
        excluded_sensitive_count=len(content["excluded"]["sensitive_pending"]),
        generated_by_id=user.id,
    )
    db.add(report)
    if kind == "approved":
        project.status = ProjectStatus.COMPLETED
    db.flush()
    audit.record(
        db, project_id=project.id, entity_type="report", entity_id=report.id, action="generated",
        after={"kind": kind, "title": report.title, "themes": len(content["sections"]["frequency"]),
               "withheld_sensitive": report.excluded_sensitive_count},
        user=user,
    )
    db.commit()
    db.refresh(report)
    return report
