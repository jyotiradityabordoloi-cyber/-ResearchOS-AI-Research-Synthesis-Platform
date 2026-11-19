"""PDF export for research reports (fpdf2, pure Python, free).

Rendered from the report's structured JSON so the PDF and Markdown always agree.
Uses the built-in Helvetica font, so text is transliterated to Latin-1 (curly quotes
become straight quotes, unsupported characters become '?').
"""

from __future__ import annotations

from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos
from fpdf.fonts import FontFace

from app.services.report import numbered_headings

_TRANSLATE = str.maketrans(
    {
        "“": '"', "”": '"', "‘": "'", "’": "'", "–": "-", "—": " - ", "…": "...", "•": "-",
        " ": " ", "→": "->", "≥": ">=", "≤": "<=", "·": "-",
    }
)
INK = (23, 23, 23)
MUTED = (110, 110, 110)
ACCENT = (67, 56, 202)
RULE = (225, 225, 225)


def _t(text: object) -> str:
    return str(text or "").translate(_TRANSLATE).encode("latin-1", "replace").decode("latin-1")


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


class _ReportPDF(FPDF):
    def __init__(self, title: str):
        super().__init__(format="A4")
        self.report_title = title
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(18, 18, 18)
        self.set_title(_t(title))
        self.set_creator("ResearchOS")

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", size=8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, _t(f"{self.report_title}  |  page {self.page_no()}"), align="C")

    # -- building blocks -------------------------------------------------------
    def h1(self, text: str) -> None:
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(*INK)
        self.multi_cell(0, 8, _t(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(1)

    def h2(self, text: str) -> None:
        if self.get_y() > 250:
            self.add_page()
        self.ln(4)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*ACCENT)
        self.multi_cell(0, 7, _t(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*RULE)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)

    def h3(self, text: str) -> None:
        self.ln(1)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(*INK)
        self.multi_cell(0, 6, _t(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def para(self, text: str, muted: bool = False, size: int = 10, italic: bool = False) -> None:
        self.set_font("Helvetica", "I" if italic else "", size)
        self.set_text_color(*(MUTED if muted else INK))
        self.multi_cell(0, 5, _t(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def bullet(self, text: str, marker: str = "-") -> None:
        self.set_font("Helvetica", size=10)
        self.set_text_color(*INK)
        x = self.l_margin
        self.set_x(x)
        self.cell(6, 5, _t(marker))
        self.multi_cell(0, 5, _t(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def quote(self, text: str, who: str) -> None:
        self.set_font("Helvetica", "I", 10)
        self.set_text_color(*INK)
        y0 = self.get_y()
        self.set_x(self.l_margin + 4)
        self.multi_cell(0, 5, _t(f'"{text}"  - {who}'), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*ACCENT)
        self.line(self.l_margin + 1, y0, self.l_margin + 1, self.get_y())
        self.ln(1)

    def table(self, header: list[str], rows: list[list[str]], widths: tuple[int, ...]) -> None:  # type: ignore[override]
        self.set_font("Helvetica", size=9)
        self.set_text_color(*INK)
        self.set_draw_color(*RULE)
        with super().table(
            col_widths=widths,
            text_align="LEFT",
            line_height=5,
            headings_style=FontFace(emphasis="BOLD", fill_color=(245, 245, 245)),
            first_row_as_headings=True,
        ) as tbl:
            head = tbl.row()
            for h in header:
                head.cell(_t(h))
            for r in rows:
                row = tbl.row()
                for c in r:
                    row.cell(_t(c))


def render_pdf(content: dict[str, Any], title: str) -> bytes:
    s = content["sections"]
    p = s["participants"]
    pdf = _ReportPDF(title)
    pdf.add_page()
    pdf.h1(title)
    status = "Approved report" if content["kind"] == "approved" else "DRAFT - not all findings reviewed"
    pdf.para(
        f"{content['project']['name']}  |  {status}  |  generated {content['generated_at'][:10]}  |  "
        f"{content['run']['provider']} ({content['run']['model']})"
        + ("  |  offline demo mode" if content["run"]["is_demo"] else ""),
        muted=True,
        size=9,
    )

    def summary() -> None:
        pdf.para(content["summary"]["text"])

    def objective() -> None:
        for o in s["objective"]["objectives"] or ["No objectives recorded."]:
            pdf.bullet(o)
        if s["objective"]["context"]:
            pdf.para(s["objective"]["context"], muted=True)

    def participants() -> None:
        pdf.bullet(
            f"{p['unique_participants']} unique participants ({p['valid_interviews']} valid of {p['total_interviews']} interviews)"
        )
        pdf.bullet("Roles: " + ", ".join(f"{k} ({v})" for k, v in p["roles"].items()))
        pdf.bullet("Company size: " + ", ".join(f"{k} ({v})" for k, v in p["company_sizes"].items()))
        pdf.bullet("Plan tier: " + ", ".join(f"{k} ({v})" for k, v in p["plan_tiers"].items()))
        if p["target_segments"]:
            pdf.bullet("Target segments: " + ", ".join(p["target_segments"]))

    def methodology() -> None:
        for m in s["methodology"]:
            pdf.bullet(m)

    def themes() -> None:
        if not s["themes"]:
            pdf.para("No recurring themes in this report.", muted=True)
        for t in s["themes"]:
            flags = [x for x, on in (("unreviewed", not t["reviewed"]), ("strategic", t["strategic_flag"]),
                                     ("sensitive, approved", bool(t["sensitive_tags"]))) if on]
            pdf.h3(f"{t['code']} - {t['name']}" + (f"  ({', '.join(flags)})" if flags else ""))
            pdf.para(t["description"])
            pdf.para(
                f"{t['participant_count']} of {t['total_participants']} participants ({_pct(t['frequency'])}): "
                f"{', '.join(t['participant_ids'])}  |  severity {t['severity']}/5  |  confidence {_pct(t['confidence'])}",
                muted=True,
                size=9,
            )
            if t["implication"]:
                pdf.para(f"Implication: {t['implication']}", size=9)

    def frequency() -> None:
        pdf.table(
            ["Theme", "Participants", "Frequency"],
            [
                [f"{f['code']} - {f['name']}" + (" (outlier)" if f["is_outlier"] else ""),
                 f"{f['participant_count']} of {f['total_participants']}", _pct(f["frequency"])]
                for f in s["frequency"]
            ],
            (110, 40, 24),
        )

    def quotes() -> None:
        for q in s["quotes"]:
            pdf.h3(f"{q['code']} - {q['name']}")
            if not q["quotes"]:
                pdf.para("No verified quote available.", muted=True)
            for item in q["quotes"]:
                pdf.quote(item["quote"], item["participant_id"])

    def contradictions() -> None:
        if not s["contradictions"]:
            pdf.para("No contradicting evidence was found.", muted=True)
        for x in s["contradictions"]:
            pdf.h3(f"{x['code']} - {x['name']}")
            if x["quote"]:
                pdf.quote(x["quote"], x["participant_id"])
            if x["note"]:
                pdf.para(x["note"], muted=True, size=9)

    def outliers() -> None:
        if not s["outliers"]:
            pdf.para("No single-participant findings.", muted=True)
        for t in s["outliers"]:
            impact = "High-impact" if t["severity"] >= 4 else "Single participant"
            pdf.bullet(f"{t['name']} ({impact}, severity {t['severity']}/5, {', '.join(t['participant_ids'])}): {t['description']}")

    def implications() -> None:
        if s["implications"]:
            pdf.table(
                ["Priority", "Insight", "Implication", "Freq.", "Sev.", "Strat."],
                [
                    [
                        x["priority"].title() + (" (manual)" if x["overridden"] else ""),
                        (f"{x['theme_code']} - " if x["theme_code"] else "") + x["title"],
                        x["implication"],
                        _pct(x["frequency"]),
                        f"{x['severity']}/5",
                        f"{x['strategic_relevance']}/5",
                    ]
                    for x in s["implications"]
                ],
                (22, 48, 60, 14, 14, 16),
            )
        else:
            pdf.para("No implications included.", muted=True)

    def next_steps() -> None:
        for i, x in enumerate(s["next_steps"], 1):
            pdf.bullet(x, marker=f"{i}.")

    def limitations() -> None:
        for x in s["limitations"]:
            pdf.bullet(x)

    render = locals()
    for key, heading in numbered_headings(content):
        pdf.h2(heading)
        render[key]()

    return bytes(pdf.output())
