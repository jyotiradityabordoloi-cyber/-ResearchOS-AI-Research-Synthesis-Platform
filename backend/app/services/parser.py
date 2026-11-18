"""Module B — turn pasted notes or uploaded text files into structured interviews.

Deterministic, no AI. The parser never alters text: each interview keeps the exact
block it came from as `raw_content`, and anything it cannot map is reported as a
warning rather than silently dropped.

Supported inputs
- Labelled text (paste, .txt, .md): `Participant ID: P01` style lines. Interviews are
  separated by `---` / `===` / `***` lines, `# Interview` headings, or simply by the
  next `Participant ID:` line. Values may span several lines.
- CSV: one interview per row, headers matched to fields by name.
- JSON: a list of objects (or {"interviews": [...]}) keyed by field name.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field

FIELDS = (
    "participant_id",
    "participant_role",
    "company_size",
    "plan_tier",
    "pain",
    "behavior",
    "verbatim_quote",
)

# Normalised label -> field. Labels are lower-cased with punctuation collapsed.
ALIASES: dict[str, str] = {}
for _field, _labels in {
    "participant_id": ["participant id", "participant", "participant no", "participant number",
                       "pid", "participant code", "interviewee id", "user id", "id"],
    "participant_role": ["participant role", "role", "job title", "title", "position", "persona"],
    "company_size": ["company size", "size", "employees", "employee count", "team size", "org size"],
    "plan_tier": ["plan tier", "plan", "tier", "subscription", "pricing plan", "plan type"],
    "pain": ["pain", "pains", "pain point", "pain points", "problem", "problems", "frustration",
             "frustrations"],
    "behavior": ["behavior", "behaviour", "behaviors", "behaviours", "current behavior",
                 "current behaviour", "workaround", "workarounds"],
    "verbatim_quote": ["verbatim quote", "verbatim", "quote", "quotes", "verbatim quotes"],
}.items():
    for _label in _labels:
        ALIASES[_label] = _field

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | {".csv", ".json"}
MAX_FILE_BYTES = 2 * 1024 * 1024

_SEPARATOR = re.compile(r"^\s*(?:-{3,}|={3,}|\*{3,}|_{3,})\s*$")
_HEADING = re.compile(r"^\s*#{1,6}\s+(?:interview|participant|session)\b.*$", re.IGNORECASE)
# "Label: value" with optional bullets / markdown emphasis around the label.
_LABEL_LINE = re.compile(
    r"^\s*(?:[-*•>]\s+)?(?:\*\*|__)?\s*([A-Za-z][A-Za-z #/_().-]{0,40}?)\s*(?:\*\*|__)?\s*[:：]\s*(?:\*\*|__)?\s*(.*)$"
)
_QUOTE_CHARS = "\"'“”‘’«»"
# 1–3 capitalised words, e.g. "Date", "Interviewer", "Company Name". Lower-case phrases
# such as "For example:" inside a value are treated as part of that value instead.
_UNKNOWN_LABEL = re.compile(r"^[A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*){0,2}$")


def normalise_label(label: str) -> str:
    label = re.sub(r"\(.*?\)", " ", label.lower())
    label = re.sub(r"[_#./-]+", " ", label)
    return re.sub(r"\s+", " ", label).strip()


def field_for_label(label: str) -> str | None:
    return ALIASES.get(normalise_label(label))


@dataclass
class ParsedInterview:
    index: int
    fields: dict[str, str]
    raw_content: str
    parse_issues: list[dict[str, str]] = field(default_factory=list)
    source_filename: str | None = None


class ParseError(ValueError):
    """The input as a whole cannot be read (e.g. invalid JSON)."""


# ---------------------------------------------------------------------------
# Labelled text
# ---------------------------------------------------------------------------


def _split_blocks(text: str) -> list[str]:
    """Split on explicit separators, then on repeated Participant ID lines."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks: list[list[str]] = [[]]
    for line in text.split("\n"):
        if _SEPARATOR.match(line) or _HEADING.match(line):
            chunks.append([] if not _HEADING.match(line) else [line])
            continue
        chunks[-1].append(line)

    blocks: list[str] = []
    for chunk in chunks:
        current: list[str] = []
        seen_id = False
        for line in chunk:
            m = _LABEL_LINE.match(line)
            is_id = bool(m and field_for_label(m.group(1)) == "participant_id")
            if is_id and seen_id:
                blocks.append("\n".join(current))
                current, seen_id = [], False
            if is_id:
                seen_id = True
            current.append(line)
        blocks.append("\n".join(current))
    # Drop blocks that are only blank lines or markdown headings/comments (e.g. a file title).
    return [
        b.strip("\n")
        for b in blocks
        if any(line.strip() and not line.lstrip().startswith("#") for line in b.split("\n"))
    ]


def _clean_value(field_name: str, value: str) -> str:
    value = re.sub(r"[ \t]+\n", "\n", value).strip()
    value = re.sub(r"\n{3,}", "\n\n", value)
    if field_name == "verbatim_quote" and len(value) >= 2 and value[0] in _QUOTE_CHARS and value[-1] in _QUOTE_CHARS:
        value = value[1:-1].strip()
    if field_name in ("participant_id", "participant_role", "company_size", "plan_tier"):
        value = " ".join(value.split())
    return value


def parse_block(block: str, index: int) -> ParsedInterview:
    values: dict[str, list[str]] = {}
    issues: list[dict[str, str]] = []
    current: str | None = None
    unknown_labels: list[str] = []
    stray: list[str] = []

    for line in block.split("\n"):
        if _HEADING.match(line) or (current is None and line.lstrip().startswith("#")):
            continue
        m = _LABEL_LINE.match(line)
        target = field_for_label(m.group(1)) if m else None
        if m and target:
            if target in values and values[target] and any(v.strip() for v in values[target]):
                issues.append(
                    {
                        "field": target,
                        "severity": "warning",
                        "message": f"'{m.group(1).strip()}' appears more than once; values were combined.",
                    }
                )
                values[target].append("")
            current = target
            values.setdefault(target, []).append(m.group(2))
        elif m and _UNKNOWN_LABEL.match(m.group(1).strip()) and not line.lstrip().lower().startswith("http"):
            # A Title-Case label we don't map (e.g. "Date: 3 May", "Interviewer: Sam").
            # Its text stays in raw_content only, and it ends the previous field.
            unknown_labels.append(m.group(1).strip())
            current = None
        elif current is not None:
            values[current].append(line)
        elif line.strip():
            stray.append(line.strip())

    fields = {f: _clean_value(f, "\n".join(values.get(f, []))) for f in FIELDS}

    if unknown_labels:
        issues.append(
            {
                "field": "_format",
                "severity": "warning",
                "message": "Unrecognised field(s) kept in original notes only: " + ", ".join(dict.fromkeys(unknown_labels)) + ".",
            }
        )
    if stray:
        issues.append(
            {
                "field": "_format",
                "severity": "warning",
                "message": f"{len(stray)} line(s) of text were not under a recognised field label "
                "and are kept in the original notes only.",
            }
        )
    if not any(values.values()):
        issues.append(
            {
                "field": "_format",
                # A warning: the missing required fields are reported as errors by validation.
                "severity": "warning",
                "message": "No recognised field labels found. Expected lines like 'Participant ID: P01', 'Pain: …'.",
            }
        )
    return ParsedInterview(index=index, fields=fields, raw_content=block, parse_issues=issues)


def parse_text(text: str) -> list[ParsedInterview]:
    return [parse_block(b, i) for i, b in enumerate(_split_blocks(text))]


# ---------------------------------------------------------------------------
# CSV / JSON
# ---------------------------------------------------------------------------


def _record_to_interview(record: dict[str, object], index: int, raw: str) -> ParsedInterview:
    fields = {f: "" for f in FIELDS}
    unknown: list[str] = []
    for key, value in record.items():
        if key is None:
            continue
        target = field_for_label(str(key))
        text = "" if value is None else str(value)
        if target:
            fields[target] = _clean_value(target, (fields[target] + "\n" + text) if fields[target] else text)
        elif text.strip():
            unknown.append(str(key))
    issues = []
    if unknown:
        issues.append(
            {
                "field": "_format",
                "severity": "warning",
                "message": "Unrecognised column(s) kept in original notes only: " + ", ".join(unknown) + ".",
            }
        )
    return ParsedInterview(index=index, fields=fields, raw_content=raw, parse_issues=issues)


def parse_csv(text: str) -> list[ParsedInterview]:
    text = text.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames or not any(field_for_label(h or "") for h in reader.fieldnames):
        raise ParseError(
            "CSV header row has no recognised columns. Expected headers like "
            "'Participant ID', 'Pain', 'Behavior'."
        )
    header = list(reader.fieldnames)
    out = []
    for row in reader:
        if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
            continue
        # Raw content preserves the original cell values, labelled by their original header.
        raw = "\n".join(f"{h}: {row.get(h) or ''}" for h in header)
        out.append(_record_to_interview(row, len(out), raw))
    return out


def parse_json(text: str) -> list[ParsedInterview]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Invalid JSON: {exc.msg} (line {exc.lineno}).") from exc
    if isinstance(data, dict):
        data = data.get("interviews", [data])
    if not isinstance(data, list) or not all(isinstance(d, dict) for d in data):
        raise ParseError("JSON must be a list of interview objects.")
    return [
        _record_to_interview(d, i, json.dumps(d, ensure_ascii=False, indent=2)) for i, d in enumerate(data)
    ]


def parse_file(filename: str, content: bytes) -> list[ParsedInterview]:
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise ParseError(
            f"Unsupported file type '{ext or filename}'. Supported: "
            + ", ".join(sorted(SUPPORTED_EXTENSIONS))
            + "."
        )
    if len(content) > MAX_FILE_BYTES:
        raise ParseError(f"File is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = content.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise ParseError("File is not readable text (expected UTF-8).") from exc

    if ext == ".csv":
        items = parse_csv(text)
    elif ext == ".json":
        items = parse_json(text)
    else:
        items = parse_text(text)
    for item in items:
        item.source_filename = filename
    return items
