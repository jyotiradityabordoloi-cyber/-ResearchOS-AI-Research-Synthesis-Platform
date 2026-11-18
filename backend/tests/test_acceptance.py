"""Acceptance suite: the seven test scenarios and ten final acceptance criteria from the brief.

Each test name maps to the brief so the suite doubles as a checklist:
    pytest tests/test_acceptance.py -v

Runs against the offline demo engine (deterministic). Test 6 also exercises a real
HTTP provider pointed at a port where nothing is listening.
"""

from pathlib import Path

import pytest

from app.ai.embeddings import HashEmbedder
from app.ai.engine import DemoEngine, LLMEngine
from app.ai.providers import LLMError, OllamaProvider
from app.api.routes.synthesis import AI, get_ai
from app.main import app

SAMPLES = Path(__file__).resolve().parents[2] / "samples"
CONSISTENT = (SAMPLES / "interviews-consistent.md").read_text(encoding="utf-8")
INCONSISTENT = (SAMPLES / "interviews-inconsistent.txt").read_text(encoding="utf-8")
EDGE = (SAMPLES / "interviews-edge-cases.md").read_text(encoding="utf-8")


# --- helpers -------------------------------------------------------------------------


def new_project(client, name="Acceptance project"):
    r = client.post(
        "/api/projects",
        json={"name": name, "objectives": ["Understand why trials do not convert"], "target_segments": ["SMB", "Enterprise"]},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def preview(client, pid, text):
    r = client.post(f"/api/projects/{pid}/import/preview", json={"text": text})
    assert r.status_code == 200, r.text
    return r.json()


def import_text(client, pid, text, skip_invalid=True):
    items = [
        {"fields": i["fields"], "parsed_fields": i["fields"], "raw_content": i["raw_content"], "source": "paste"}
        for i in preview(client, pid, text)["items"]
    ]
    r = client.post(f"/api/projects/{pid}/import", json={"items": items, "skip_invalid": skip_invalid})
    assert r.status_code == 201, r.text
    return r.json()


def synthesise(client, pid, **body):
    r = client.post(f"/api/projects/{pid}/synthesis", json=body)
    assert r.status_code == 202, r.text
    return client.get(f"/api/projects/{pid}/synthesis/runs").json()[0]


def themes(client, pid, **params):
    return client.get(f"/api/projects/{pid}/themes", params=params).json()


@pytest.fixture
def use_engine():
    def set_engine(engine):
        app.dependency_overrides[get_ai] = lambda: AI(engine=engine, embedder=HashEmbedder())

    yield set_engine
    app.dependency_overrides.pop(get_ai, None)


# --- Test 1 ----------------------------------------------------------------------------


def test_spec_1_eight_consistent_interviews_give_reasonable_themes(client):
    """Expected: 4-6 reasonable themes, participant frequency, supporting quotes."""
    pid = new_project(client)
    created = import_text(client, pid, CONSISTENT)["created"]
    assert len(created) == 8
    run = synthesise(client, pid)
    assert run["status"] == "completed"

    ts = themes(client, pid)
    assert 4 <= len(ts) <= 6
    for t in ts:
        assert t["frequency"] == pytest.approx(t["participant_count"] / 8, abs=1e-4)
        assert t["participant_count"] == len(t["participant_ids"])
        quotes = [e for e in t["evidence"] if e["stance"] == "supporting" and e["quote_verified"]]
        assert quotes, f"{t['name']} has no verified supporting quote"


# --- Test 2 ----------------------------------------------------------------------------


def test_spec_2_inconsistent_format_fails_validation_and_blocks_synthesis(client):
    """Expected: validation failure, no synthesis execution."""
    pid = new_project(client)
    report = preview(client, pid, INCONSISTENT)
    assert report["summary"]["invalid"] == 4 and report["summary"]["valid"] == 1
    reasons = " ".join(i["message"] for item in report["items"] for i in item["issues"])
    assert "Participant ID is missing" in reasons and "Behavior is missing" in reasons

    # Even if every interview is saved (including invalid ones), synthesis must not run.
    import_text(client, pid, INCONSISTENT, skip_invalid=False)
    refused = client.post(f"/api/projects/{pid}/synthesis", json={})
    assert refused.status_code == 422
    assert client.get(f"/api/projects/{pid}/synthesis/runs").json() == []
    assert themes(client, pid) == []
    v = client.get(f"/api/projects/{pid}/validation-report").json()
    assert v["can_run_standard_synthesis"] is False and v["invalid_interviews"] == 4


# --- Test 3 ----------------------------------------------------------------------------


def test_spec_3_contradictory_interview_shows_both_sides(client):
    """Expected: supporting and opposing evidence both visible."""
    pid = new_project(client)
    import_text(client, pid, CONSISTENT + "\n---\n" + EDGE)
    synthesise(client, pid)
    t = next(t for t in themes(client, pid) if t["has_contradictions"])
    supporting = [e for e in t["evidence"] if e["stance"] == "supporting"]
    opposing = [e for e in t["evidence"] if e["stance"] == "contradicting"]
    assert supporting and opposing
    assert opposing[0]["participant_id"] == "P09" and opposing[0]["quote_verified"]
    report = client.post(f"/api/projects/{pid}/reports", json={"kind": "draft"}).json()
    assert any(c["participant_id"] == "P09" for c in report["content_json"]["sections"]["contradictions"])


# --- Test 4 ----------------------------------------------------------------------------


def test_spec_4_single_participant_high_impact_is_flagged_not_discarded(client):
    """Expected: flagged as an outlier, not discarded."""
    pid = new_project(client)
    import_text(client, pid, CONSISTENT + "\n---\n" + EDGE)
    run = synthesise(client, pid)
    soc2 = next(t for t in themes(client, pid) if t["participant_ids"] == ["P10"])
    assert soc2["is_outlier"] and soc2["severity"] >= 4 and soc2["status"] == "proposed"
    assert run["stats"]["high_impact_outliers"] >= 1
    report = client.post(f"/api/projects/{pid}/reports", json={"kind": "draft"}).json()
    assert any("P10" in o["participant_ids"] for o in report["content_json"]["sections"]["outliers"])


# --- Test 5 ----------------------------------------------------------------------------


def test_spec_5_duplicate_pain_points_count_participant_once(client):
    """Expected: participant counted only once."""
    pid = new_project(client)
    import_text(client, pid, CONSISTENT)
    # Same participant again, repeating the same pain twice in one note.
    dup = (
        "Participant ID: P05\nParticipant Role: Customer Success Manager\nCompany Size: 10-50\nPlan Tier: Team\n"
        "Pain: Dashboards are slow to refresh on Monday mornings when everyone opens them. "
        "Dashboards are slow to refresh on Monday mornings when everyone opens them.\n"
        "Behavior: Still downloads the data to Excel every Monday.\n"
        'Verbatim Quote: "Monday mornings are still painful."'
    )
    import_text(client, pid, dup)
    run = synthesise(client, pid)
    assert run["stats"]["participants"] == 8  # 9 interviews, 8 people
    assert run["stats"]["duplicates_merged"] >= 2
    for t in themes(client, pid):
        assert t["participant_ids"].count("P05") <= 1
        assert t["total_participants"] == 8
        assert t["frequency"] == pytest.approx(len(set(t["participant_ids"])) / 8, abs=1e-4)


# --- Test 6 ----------------------------------------------------------------------------


class _FailsLate(DemoEngine):
    name, model = "flaky", "breaks-at-insights"

    def draft_insight(self, *a, **kw):
        raise LLMError("provider returned malformed JSON after 3 attempts")


def test_spec_6_provider_failure_handled_without_corrupting_data(client, use_engine):
    """Expected: error handling, no corrupted research data."""
    pid = new_project(client)
    import_text(client, pid, CONSISTENT)
    good = synthesise(client, pid)
    before = themes(client, pid)
    report_before = client.post(f"/api/projects/{pid}/reports", json={"kind": "draft"}).json()

    # 1) The AI fails late in the pipeline.
    use_engine(_FailsLate())
    failed = synthesise(client, pid)
    assert failed["status"] == "failed" and "malformed JSON" in failed["error"]
    assert [t["id"] for t in themes(client, pid)] == [t["id"] for t in before]

    # 2) The AI provider is unreachable (real HTTP client, nothing listening on the port).
    unreachable = OllamaProvider("http://127.0.0.1:9", "missing-model", timeout=2, max_retries=2, backoff_seconds=0)
    use_engine(LLMEngine(unreachable))
    down = synthesise(client, pid)
    assert down["status"] == "failed" and "failed after 2 attempts" in down["error"]

    project = client.get(f"/api/projects/{pid}").json()
    assert project["synthesis_status"] == "failed"
    after = themes(client, pid)
    assert [t["id"] for t in after] == [t["id"] for t in before]
    assert all(t["run_id"] == good["id"] for t in after)
    assert client.get(f"/api/reports/{report_before['id']}").status_code == 200
    assert len(client.get(f"/api/projects/{pid}/interviews").json()) == 8


# --- Test 7 ----------------------------------------------------------------------------


def test_spec_7_sensitive_themes_need_human_approval(client):
    """Expected: pricing, churn and competitive-switching findings require human approval."""
    pid = new_project(client)
    import_text(client, pid, CONSISTENT + "\n---\n" + EDGE)
    synthesise(client, pid)
    ts = themes(client, pid)
    sensitive = [t for t in ts if t["requires_approval"]]
    tags = {tag for t in sensitive for tag in t["sensitive_tags"]}
    assert {"pricing", "churn", "competitive_switching"} <= tags

    plain = next(t for t in ts if not t["requires_approval"])
    client.post(f"/api/themes/{plain['id']}/review", json={"decision": "approve"})
    report = client.post(f"/api/projects/{pid}/reports", json={"kind": "approved"}).json()
    included = {f["name"] for f in report["content_json"]["sections"]["frequency"]}
    assert not included & {t["name"] for t in sensitive}
    assert report["excluded_sensitive_count"] == len(sensitive)

    target = sensitive[0]
    url = f"/api/themes/{target['id']}/review"
    assert client.post(url, json={"decision": "approve"}).status_code == 422
    assert client.post(url, json={"decision": "approve", "acknowledge_sensitive": True, "comment": "Checked"}).status_code == 200
    report = client.post(f"/api/projects/{pid}/reports", json={"kind": "approved"}).json()
    assert target["name"] in {f["name"] for f in report["content_json"]["sections"]["frequency"]}


# --- Final acceptance criteria 1-10 -------------------------------------------------------


def test_final_acceptance_criteria_end_to_end(client):
    # 1. Create a research project.
    pid = new_project(client, "Trial conversion research")

    # 2. Import at least 8 interview notes (paste + file upload).
    import_text(client, pid, CONSISTENT)
    files = [("files", ("edge-cases.md", EDGE.encode(), "text/markdown"))]
    upload = client.post(f"/api/projects/{pid}/import/preview-files", files=files).json()
    client.post(
        f"/api/projects/{pid}/import",
        json={"items": [{"fields": i["fields"], "raw_content": i["raw_content"], "source": "upload",
                         "source_filename": i["source_filename"]} for i in upload["items"]]},
    )
    assert client.get(f"/api/projects/{pid}").json()["interview_count"] == 12

    # 3. Validate interview structure.
    v = client.get(f"/api/projects/{pid}/validation-report").json()
    assert v["can_run_standard_synthesis"] and v["unique_valid_participants"] == 11

    # 4. Run AI-powered theme clustering.
    run = synthesise(client, pid)
    assert run["status"] == "completed"
    ts = themes(client, pid)

    # 5. See participant frequency and supporting quotes.
    top = ts[0]
    assert top["participant_count"] >= 3 and 0 < top["frequency"] <= 1
    assert any(e["quote_verified"] for e in top["evidence"])

    # 6. Review contradictory evidence.
    assert any(t["has_contradictions"] for t in ts)

    # 7. Flag high-impact outliers.
    assert any(t["is_outlier"] and t["severity"] >= 4 for t in ts)

    # 8. Edit and approve insights.
    client.patch(f"/api/themes/{top['id']}", json={"name": "Dashboards are too slow for customer calls"})
    client.post(f"/api/themes/{top['id']}/review", json={"decision": "approve", "comment": "Matches support tickets"})
    insight = next(i for i in client.get(f"/api/projects/{pid}/insights").json() if i["theme_id"] == top["id"])
    assert insight["status"] == "approved" and insight["title"] == "Dashboards are too slow for customer calls"
    edited = client.patch(f"/api/insights/{insight['id']}", json={"priority_override": "high", "override_reason": "CEO priority"})
    assert edited.json()["is_overridden"]

    # 9. Generate a research report (Markdown + PDF).
    report = client.post(f"/api/projects/{pid}/reports", json={"kind": "approved"}).json()
    assert "## 11. Limitations" in report["content_markdown"]
    assert client.get(f"/api/reports/{report['id']}/export.pdf").content[:5] == b"%PDF-"
    assert client.get(f"/api/projects/{pid}").json()["status"] == "completed"

    # 10. Search previously generated insights.
    by_word = client.get("/api/repository/search", params={"q": "customer calls"}).json()
    assert any(h["id"] == top["id"] for h in by_word)
    by_meaning = client.get(
        "/api/repository/search", params={"q": "reports are slow to load", "mode": "semantic"}
    ).json()
    assert by_meaning and by_meaning[0]["score"] > 0
    approved_only = client.get("/api/repository/search", params={"approved_only": True}).json()
    assert [h["id"] for h in approved_only] == [top["id"]]

    # Every human action above is in the audit log.
    actions = {(e["entity_type"], e["action"]) for e in client.get(f"/api/projects/{pid}/audit").json()}
    assert {("theme", "rename"), ("theme", "approve"), ("insight", "override_priority"), ("report", "generated")} <= actions
