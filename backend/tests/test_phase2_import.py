from pathlib import Path

from tests.conftest import VALID_INTERVIEW

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
CONSISTENT = (SAMPLES / "interviews-consistent.md").read_text(encoding="utf-8")
INCONSISTENT = (SAMPLES / "interviews-inconsistent.txt").read_text(encoding="utf-8")


def _preview(client, pid, text):
    resp = client.post(f"/api/projects/{pid}/import/preview", json={"text": text})
    assert resp.status_code == 200, resp.text
    return resp.json()


def _as_import_items(preview):
    return [
        {
            "fields": it["fields"],
            "parsed_fields": it["fields"],
            "raw_content": it["raw_content"],
            "source": it["source"],
            "source_filename": it["source_filename"],
        }
        for it in preview["items"]
    ]


# --- Test 1 dataset: eight consistent interviews ----------------------------------


def test_consistent_notes_preview_then_import(client, project):
    pid = project["id"]
    preview = _preview(client, pid, CONSISTENT)
    s = preview["summary"]
    assert s["total"] == 8 and s["valid"] == 8 and s["invalid"] == 0
    assert s["sample_sufficient"] is True
    # preview saves nothing
    assert client.get(f"/api/projects/{pid}").json()["interview_count"] == 0

    result = client.post(f"/api/projects/{pid}/import", json={"items": _as_import_items(preview)})
    assert result.status_code == 201, result.text
    body = result.json()
    assert len(body["created"]) == 8 and body["skipped"] == []
    assert body["created"][0]["source"] == "paste"

    report = client.get(f"/api/projects/{pid}/validation-report").json()
    assert report["unique_valid_participants"] == 8
    assert report["can_run_standard_synthesis"] is True


# --- Test 2 dataset: inconsistent notes -------------------------------------------


def test_inconsistent_notes_fail_validation_and_block_synthesis(client, project):
    pid = project["id"]
    preview = _preview(client, pid, INCONSISTENT)
    s = preview["summary"]
    assert s["total"] == 5
    assert s["valid"] == 1 and s["invalid"] == 4
    assert s["sample_sufficient"] is False

    statuses = {it["fields"]["participant_id"] or f"#{it['index']}": it["status"] for it in preview["items"]}
    assert statuses["P11"] == "valid"
    assert statuses["P13"] == "invalid"  # n/a and TBD are not meaningful
    assert statuses["P14"] == "invalid"  # missing Behavior

    # Default import skips invalid items, and reports why.
    result = client.post(f"/api/projects/{pid}/import", json={"items": _as_import_items(preview)}).json()
    assert [c["participant_id"] for c in result["created"]] == ["P11"]
    assert len(result["skipped"]) == 4
    assert any("Behavior is missing" in s["reason"] for s in result["skipped"])

    report = client.get(f"/api/projects/{pid}/validation-report").json()
    assert report["can_run_standard_synthesis"] is False
    assert {c["key"]: c["status"] for c in report["checks"]}["sample_size"] == "fail"


def test_server_revalidates_and_does_not_trust_client(client, project):
    item = {
        "fields": {**VALID_INTERVIEW, "pain": ""},
        "raw_content": "Participant ID: P01\nPain:",
        "source": "paste",
    }
    result = client.post(f"/api/projects/{project['id']}/import", json={"items": [item]}).json()
    assert result["created"] == [] and len(result["skipped"]) == 1


def test_can_save_invalid_when_explicitly_requested(client, project):
    item = {"fields": {"participant_id": "P5"}, "raw_content": "Participant ID: P5", "source": "paste"}
    result = client.post(
        f"/api/projects/{project['id']}/import", json={"items": [item], "skip_invalid": False}
    ).json()
    assert result["created"][0]["validation_status"] == "invalid"


def test_corrections_before_import_are_audited_and_raw_kept(client, project):
    pid = project["id"]
    preview = _preview(client, pid, "Participant ID: P7\nPain: n/a\nBehavior: logs bugs in Jira daily")
    item = _as_import_items(preview)[0]
    item["fields"] = {**item["fields"], "pain": "Cannot see which bugs customers care about."}
    created = client.post(f"/api/projects/{pid}/import", json={"items": [item]}).json()["created"][0]
    assert created["validation_status"] == "valid"
    assert "Pain: n/a" in created["raw_content"]  # original preserved verbatim

    entry = next(e for e in client.get(f"/api/projects/{pid}/audit").json() if e["action"] == "imported")
    assert entry["after"]["corrected_before_import"]["pain"] == {
        "parsed": "n/a",
        "saved": "Cannot see which bugs customers care about.",
    }


# --- Duplicates (Test 5 groundwork) ------------------------------------------------


def test_duplicate_participants_are_flagged_and_counted_once(client, project):
    pid = project["id"]
    client.post(f"/api/projects/{pid}/interviews", json=VALID_INTERVIEW)  # existing P01
    text = (
        "Participant ID: P01\nPain: export breaks layout often\nBehavior: rebuilds charts by hand\n"
        "---\nParticipant ID: P02\nPain: slow dashboards every monday\nBehavior: exports to excel weekly\n"
        "---\nParticipant ID: p02\nPain: also pricing is unclear\nBehavior: asked sales for a quote\n"
    )
    preview = _preview(client, pid, text)
    s = preview["summary"]
    assert s["existing_valid_participants"] == 1
    assert s["valid_participants_after_import"] == 2  # P01 + P02, case-insensitive
    assert sorted(s["duplicate_participants"]) == ["P02", "p02"]
    msgs = [i["message"] for it in preview["items"] for i in it["context_issues"]]
    assert any("already has 1 interview" in m for m in msgs)
    assert any("appears more than once" in m for m in msgs)

    client.post(f"/api/projects/{pid}/import", json={"items": _as_import_items(preview)})
    report = client.get(f"/api/projects/{pid}/validation-report").json()
    assert report["valid_interviews"] == 4
    assert report["unique_valid_participants"] == 2
    assert report["duplicate_participants"] == {"P01": 2, "P02": 2}


# --- Files -------------------------------------------------------------------------


def test_preview_files_mixed_with_errors(client, project):
    files = [
        ("files", ("notes.csv", (SAMPLES / "interviews.csv").read_bytes(), "text/csv")),
        ("files", ("consistent.md", CONSISTENT.encode(), "text/markdown")),
        ("files", ("deck.pdf", b"%PDF-1.4", "application/pdf")),
        ("files", ("empty.txt", b"   \n", "text/plain")),
    ]
    body = client.post(f"/api/projects/{project['id']}/import/preview-files", files=files).json()
    assert body["summary"]["total"] == 11
    assert {i["source"] for i in body["items"]} == {"upload"}
    assert {i["source_filename"] for i in body["items"]} == {"notes.csv", "consistent.md"}
    errs = {e["filename"]: e["message"] for e in body["file_errors"]}
    assert "Unsupported" in errs["deck.pdf"]
    assert "No interviews" in errs["empty.txt"]


def test_validate_endpoint(client):
    ok = client.post("/api/interviews/validate", json=VALID_INTERVIEW).json()
    assert ok["status"] == "valid"
    bad = client.post("/api/interviews/validate", json={"participant_id": "P1"}).json()
    assert bad["status"] == "invalid"


def test_empty_paste_rejected(client, project):
    assert client.post(f"/api/projects/{project['id']}/import/preview", json={"text": ""}).status_code == 422
