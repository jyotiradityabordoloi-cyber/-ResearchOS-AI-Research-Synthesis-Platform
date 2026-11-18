from pathlib import Path

import pytest

from app.services.parser import ParseError, parse_csv, parse_file, parse_json, parse_text

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def test_consistent_sample_parses_eight_interviews():
    items = parse_text((SAMPLES / "interviews-consistent.md").read_text(encoding="utf-8"))
    assert [i.fields["participant_id"] for i in items] == [f"P0{n}" for n in range(1, 9)]
    first = items[0].fields
    assert first["participant_role"] == "Head of Data"
    assert first["plan_tier"] == "Trial (Business)"
    assert first["pain"].startswith("Connecting our Postgres warehouse")
    # surrounding quotation marks are stripped from the quote field only
    assert first["verbatim_quote"].startswith("I spent most of the trial")
    assert not first["verbatim_quote"].endswith('"')
    assert all(not i.parse_issues for i in items)


def test_raw_content_is_the_exact_original_block():
    text = "Participant ID: P1\nPain:   lots   of   spaces here\nBehavior: x y z"
    [item] = parse_text(text)
    assert item.raw_content == text


def test_split_on_repeated_participant_id_without_separators():
    text = (
        "Participant ID: A\nPain: one two three\nBehavior: four five six\n"
        "Participant ID: B\nPain: seven eight nine\nBehavior: ten eleven twelve"
    )
    items = parse_text(text)
    assert [i.fields["participant_id"] for i in items] == ["A", "B"]
    assert items[1].raw_content.startswith("Participant ID: B")


def test_multiline_values_and_aliases():
    text = (
        "- **PID:** P9\n"
        "Role: Ops lead\n"
        "Pain points: first line\n"
        "second line continues\n"
        "Behaviour: uses spreadsheets\n"
        "Quote: “It hurts.”"
    )
    [item] = parse_text(text)
    assert item.fields["participant_id"] == "P9"
    assert item.fields["participant_role"] == "Ops lead"
    assert item.fields["pain"] == "first line\nsecond line continues"
    assert item.fields["behavior"] == "uses spreadsheets"
    assert item.fields["verbatim_quote"] == "It hurts."


def test_lowercase_colon_phrase_stays_inside_value():
    [item] = parse_text("Participant ID: P1\nPain: exports fail\nfor example: the PDF one\nBehavior: a b c")
    assert item.fields["pain"] == "exports fail\nfor example: the PDF one"


def test_unknown_labels_are_reported_not_merged():
    [item] = parse_text("Date: 3 May\nInterviewer: Sam\nParticipant ID: P1\nPain: a b c\nBehavior: d e f")
    assert item.fields["participant_id"] == "P1"
    msgs = " ".join(i["message"] for i in item.parse_issues)
    assert "Date" in msgs and "Interviewer" in msgs


def test_block_without_labels_is_reported():
    [item] = parse_text("We chatted about budgeting but captured nothing structured.")
    assert any("No recognised field labels" in i["message"] for i in item.parse_issues)
    assert item.fields["participant_id"] == "" and item.fields["pain"] == ""


def test_inconsistent_sample():
    items = parse_text((SAMPLES / "interviews-inconsistent.txt").read_text(encoding="utf-8"))
    assert len(items) == 5
    assert items[0].fields["participant_id"] == "P11"
    assert items[1].fields["participant_id"] == ""  # missing ID
    assert items[2].fields["pain"] == "n/a"
    assert items[3].fields["participant_id"] == "P14"
    assert items[3].fields["behavior"] == ""


def test_csv_maps_headers_and_flags_unknown_columns():
    items = parse_file("notes.csv", (SAMPLES / "interviews.csv").read_bytes())
    assert [i.fields["participant_id"] for i in items] == ["P21", "P22", "P23"]
    assert items[0].source_filename == "notes.csv"
    assert "Interviewer" in items[0].parse_issues[0]["message"]
    assert "Interviewer: Alex" in items[0].raw_content


def test_csv_without_known_headers_fails():
    with pytest.raises(ParseError):
        parse_csv("a,b\n1,2\n")


def test_json_list_and_wrapper():
    assert parse_json('[{"participant_id": "P1", "pain": "x"}]')[0].fields["participant_id"] == "P1"
    assert parse_json('{"interviews": [{"Participant ID": "P2"}]}')[0].fields["participant_id"] == "P2"
    with pytest.raises(ParseError):
        parse_json("{not json")


def test_unsupported_file_type():
    with pytest.raises(ParseError, match="Unsupported"):
        parse_file("notes.pdf", b"%PDF")
