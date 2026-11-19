"""Module G — research report generation (pipeline stage 9).

Reports are assembled deterministically from reviewed data; nothing is invented.
Inclusion rules:
- Rejected and merged findings are never included.
- Sensitive findings (pricing / churn / competitive switching) are included only once a
  person has approved them (fallback rule D). Withheld items are counted in the report.
- A "draft" report includes approved and not-yet-reviewed findings (marked as unreviewed).
- An "approved" report includes approved findings only, needs at least one approved theme,
  and marks the project as completed so it lives on in the repository.

Report builder options (all optional):
- `sections`: which sections to include, in the standard order. The executive summary is
  a section of its own.
- `excluded_theme_ids`: themes the team leaves out. They are named in Limitations, so a
  report can never quietly drop a finding.
- `executive_summary`: the team's own summary. Without it, one is assembled from the data.
"""

from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Insight, Interview, ResearchProject, ResearchReport, SynthesisRun, Theme, User
from app.models.enums import EvidenceStance, ProjectStatus, ReportStatus, ReviewStatus, ValidationStatus
from app.services import audit
from app.services.review import priority_band

ReportKind = Literal["draft", "approved"]

SECTION_KEYS = [
    "objective",
    "participants",
    "methodology",
    "themes",
    "frequency",
    "quotes",
    "contradictions",
    "outliers",
    "implications",
    "next_steps",
    "limitations",
]
ALL_SECTIONS = ["summary", *SECTION_KEYS]
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


@dataclass
class ReportOptions:
    sections: list[str] | None = None  # None: every section
    excluded_theme_ids: list[uuid.UUID] = field(default_factory=list)
    executive_summary: str | None = None  # None: generated from the data


def section_order(content: dict[str, Any]) -> list[str]:
    """Sections to render, in order. Reports saved before the builder have all eleven."""
    return content.get("included_sections") or SECTION_KEYS


def section_title(content: dict[str, Any], key: str) -> str:
    return content.get("section_labels", {}).get(key) or dict(zip(SECTION_KEYS, SECTION_TITLES))[key]


def numbered_headings(content: dict[str, Any]) -> list[tuple[str, str]]:
    """(key, heading) pairs. The executive summary leads unnumbered; the rest count 1, 2, 3..."""
    out, n = [], 0
    for key in section_order(content):
        if key == "summary":
            out.append((key, section_title(content, key)))
        else:
            n += 1
            out.append((key, f"{n}. {section_title(content, key)}"))
    return out


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


def build_report_content(
    db: Session, project: ResearchProject, kind: ReportKind, options: ReportOptions | None = None
) -> dict[str, Any]:
    options = options or ReportOptions()
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
    left_out = set(options.excluded_theme_ids)
    excluded_by_choice = [t for t in kept if t.id in left_out]
    kept = [t for t in kept if t.id not in left_out]
    if kind == "approved" and not kept:
        raise ReportError(422, "Every approved theme is excluded. Include at least one theme in the report.")
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
    if excluded_by_choice:
        limitations.append(
            f"The team left {len(excluded_by_choice)} theme(s) out of this report: "
            + "; ".join(f"{t.code} “{t.name}” ({t.participant_count} of {t.total_participants} participants)" for t in excluded_by_choice)
            + "."
        )
    if kind == "draft" and any(not t["reviewed"] for t in theme_refs):
        limitations.append("This is a draft: findings marked “unreviewed” have not been approved by the team yet.")
    if project.target_segments:
        limitations.append(
            "Target segments: " + ", ".join(project.target_segments)
            + ". Check that each segment is represented before generalising."
        )

    auto_summary = summarize(
        kind=kind,
        participants=len(participants),
        recurring=recurring,
        outliers=outliers,
        implications=implications,
        contradictions=sum(len(t["contradictions"]) for t in theme_refs),
        withheld=len(withheld_sensitive),
        left_out=len(excluded_by_choice),
    )
    summary_text = (options.executive_summary or "").strip()
    wanted = set(options.sections) if options.sections is not None else set(ALL_SECTIONS)
    included = [k for k in ALL_SECTIONS if k in wanted]
    if not included:
        raise ReportError(422, "Choose at least one section.")

    return {
        "kind": kind,
        "generated_at": datetime.now(UTC).isoformat(),
        "included_sections": included,
        "section_labels": {"summary": "Executive summary", **dict(zip(SECTION_KEYS, SECTION_TITLES))},
        "summary": {
            "text": summary_text or auto_summary,
            "generated": auto_summary,
            "edited": bool(summary_text) and summary_text != auto_summary,
        },
        "options": {
            "sections": included,
            "excluded_theme_ids": [str(t.id) for t in excluded_by_choice],
        },
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
            "by_choice": [{"code": t.code, "name": t.name} for t in excluded_by_choice],
        },
    }


def summarize(
    *, kind: str, participants: int, recurring: list, outliers: list, implications: list,
    contradictions: int, withheld: int, left_out: int,
) -> str:
    """A factual executive summary assembled from the report's own numbers (no AI)."""
    themes = len(recurring) + len(outliers)
    lines = [
        f"This {'approved' if kind == 'approved' else 'draft'} report covers {themes} theme(s) "
        f"from {participants} participant(s)."
    ]
    if recurring:
        top = ", ".join(
            f"{t['name']} ({t['participant_count']} of {t['total_participants']}, {_pct(t['frequency'])})" for t in recurring[:3]
        )
        lines.append(f"The most widespread problems are {top}.")
    high = [x for x in implications if x["priority"] == "high"]
    if high:
        lines.append("Highest priority: " + "; ".join(x["title"] for x in high[:3]) + ".")
    impactful = [t for t in outliers if t["severity"] >= 4]
    if impactful:
        lines.append(f"{len(impactful)} high-impact finding(s) come from a single participant and need validation.")
    if contradictions:
        lines.append(f"{contradictions} quote(s) contradict the themes they relate to.")
    if withheld:
        lines.append(f"{withheld} sensitive finding(s) are withheld until approved.")
    if left_out:
        lines.append(f"{left_out} theme(s) were left out by the team (listed under Limitations).")
    return " ".join(lines)


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

    def summary() -> list[str]:
        return [c["summary"]["text"]]

    def objective() -> list[str]:
        lines = [f"- {o}" for o in s["objective"]["objectives"]] or ["_No objectives recorded._"]
        return lines + (["", s["objective"]["context"]] if s["objective"]["context"] else [])

    def participants() -> list[str]:
        lines = [
            f"- **{p['unique_participants']}** unique participants ({p['valid_interviews']} valid of "
            f"{p['total_interviews']} interviews)",
            "- **Roles:** " + ", ".join(f"{k} ({v})" for k, v in p["roles"].items()),
            "- **Company size:** " + ", ".join(f"{k} ({v})" for k, v in p["company_sizes"].items()),
            "- **Plan tier:** " + ", ".join(f"{k} ({v})" for k, v in p["plan_tiers"].items()),
        ]
        if p["target_segments"]:
            lines.append("- **Target segments:** " + ", ".join(p["target_segments"]))
        return lines

    def methodology() -> list[str]:
        return [f"- {m}" for m in s["methodology"]]

    def themes() -> list[str]:
        if not s["themes"]:
            return ["_No recurring themes in this report._"]
        lines: list[str] = []
        for t in s["themes"]:
            tags = [x for x, on in (("unreviewed", not t["reviewed"]), ("strategic", t["strategic_flag"]),
                                    ("sensitive, approved", bool(t["sensitive_tags"])),
                                    ("low confidence", t["is_low_confidence"])) if on]
            suffix = f" _({', '.join(tags)})_" if tags else ""
            lines += [
                f"### {t['code']} · {t['name']}{suffix}",
                "",
                t["description"],
                "",
                f"- **Participants:** {t['participant_count']} of {t['total_participants']} ({_pct(t['frequency'])}) — "
                + ", ".join(t["participant_ids"]),
                f"- **Severity:** {t['severity']}/5 · **Confidence:** {_pct(t['confidence'])}",
            ]
            if t["implication"]:
                lines.append(f"- **Implication:** {t['implication']}")
            lines.append("")
        return lines

    def frequency() -> list[str]:
        lines = ["| Theme | Participants | Frequency |", "|---|---|---|"]
        for f in s["frequency"]:
            label = f"{f['code']} · {_md_escape(f['name'])}" + (" (outlier)" if f["is_outlier"] else "")
            lines.append(f"| {label} | {f['participant_count']} of {f['total_participants']} | {_pct(f['frequency'])} |")
        return lines

    def quotes() -> list[str]:
        lines: list[str] = []
        for q in s["quotes"]:
            lines += [f"**{q['code']} · {q['name']}**", ""]
            if not q["quotes"]:
                lines += ["_No verified quote available._", ""]
            for item in q["quotes"]:
                lines += [f"> “{_md_escape(item['quote'])}” — {item['participant_id']}", ""]
        return lines

    def contradictions() -> list[str]:
        if not s["contradictions"]:
            return ["_No contradicting evidence was found._"]
        out_ = []
        for x in s["contradictions"]:
            quote = f" “{_md_escape(x['quote'])}”" if x["quote"] else ""
            out_.append(f"- **{x['code']} · {x['name']}** — {x['participant_id']}:{quote} {_md_escape(x['note'])}".rstrip())
        return out_

    def outliers() -> list[str]:
        if not s["outliers"]:
            return ["_No single-participant findings._"]
        return [
            f"- **{t['name']}** ({'High-impact' if t['severity'] >= 4 else 'Single-participant'}, severity "
            f"{t['severity']}/5, {', '.join(t['participant_ids'])}): {_md_escape(t['description'])}"
            for t in s["outliers"]
        ]

    def implications() -> list[str]:
        if not s["implications"]:
            return ["_No implications included._"]
        lines = ["| Priority | Insight | Implication | Frequency | Severity | Strategic |", "|---|---|---|---|---|---|"]
        for x in s["implications"]:
            prio = x["priority"].title() + (f" (manual; computed {x['computed_priority']})" if x["overridden"] else "")
            name = (f"{x['theme_code']} · " if x["theme_code"] else "") + _md_escape(x["title"])
            lines.append(
                f"| {prio} | {name} | {_md_escape(x['implication'])} | {_pct(x['frequency'])} | "
                f"{x['severity']}/5 | {x['strategic_relevance']}/5 |"
            )
        return lines

    def next_steps() -> list[str]:
        return [f"{i}. {x}" for i, x in enumerate(s["next_steps"], 1)]

    def limitations() -> list[str]:
        return [f"- {x}" for x in s["limitations"]]

    render = locals()
    for key, heading in numbered_headings(c):
        out += [f"## {heading}", ""] + render[key]() + [""]
    return "\n".join(out).strip() + "\n"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def default_title(project: ResearchProject, kind: ReportKind) -> str:
    return f"{project.name} — {'research report' if kind == 'approved' else 'draft report'}"


def generate_report(
    db: Session, project: ResearchProject, kind: ReportKind, title: str | None, user: User,
    options: ReportOptions | None = None,
) -> ResearchReport:
    content = build_report_content(db, project, kind, options)
    title = (title or "").strip() or default_title(project, kind)
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
               "withheld_sensitive": report.excluded_sensitive_count,
               "sections": content["included_sections"],
               "left_out": [t["code"] for t in content["excluded"]["by_choice"]],
               "summary_edited": content["summary"]["edited"]},
        user=user,
    )
    db.commit()
    db.refresh(report)
    return report
