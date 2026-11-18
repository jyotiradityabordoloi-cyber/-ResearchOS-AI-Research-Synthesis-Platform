from tests.conftest import VALID_INTERVIEW


def test_health_reports_pgvector(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["pgvector"]


def test_interrupted_runs_are_recovered_on_startup(client, project):
    from app.core.db import SessionLocal
    from app.main import recover_interrupted_runs
    from app.models import SynthesisRun

    with SessionLocal() as s:
        s.add(SynthesisRun(project_id=project["id"], status="running", provider="demo", model="m", embedding_provider="h"))
        s.commit()
    assert recover_interrupted_runs() == 1
    run = client.get(f"/api/projects/{project['id']}/synthesis/runs").json()[0]
    assert run["status"] == "failed" and "restarted" in run["error"]


def test_unhandled_errors_return_clean_json(project, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.routes import projects as projects_route
    from app.main import app

    def boom(*_a, **_k):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(projects_route, "serialize_projects", boom)
    resp = TestClient(app, raise_server_exceptions=False).get("/api/projects")
    assert resp.status_code == 500
    assert "secret" not in resp.text and resp.json()["detail"].startswith("Something went wrong")


def test_ai_settings_default_is_labelled_demo(client):
    body = client.get("/api/settings/ai").json()
    assert body["llm"]["name"] == "demo"
    assert body["llm"]["is_demo"] is True
    assert body["embeddings"]["is_demo"] is True
    assert body["min_interviews_for_synthesis"] == 5


# --- Module A: projects -----------------------------------------------------


def test_create_and_list_project(client, project):
    assert project["status"] == "draft"
    assert project["synthesis_status"] == "not_started"
    assert project["objectives"] == ["Understand activation drop-off"]
    assert project["interview_count"] == 0
    assert project["owner_name"] == "Research Lead"

    listed = client.get("/api/projects").json()
    assert [p["id"] for p in listed] == [project["id"]]


def test_project_name_required(client):
    assert client.post("/api/projects", json={"name": "   "}).status_code == 422


def test_project_lists_are_deduplicated(client):
    body = client.post(
        "/api/projects", json={"name": "X", "target_segments": ["SMB", " SMB ", "", "Enterprise"]}
    ).json()
    assert body["target_segments"] == ["SMB", "Enterprise"]


def test_update_project_is_audited(client, project):
    resp = client.patch(f"/api/projects/{project['id']}", json={"name": "Activation research"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Activation research"

    log = client.get(f"/api/projects/{project['id']}/audit").json()
    actions = [(e["entity_type"], e["action"]) for e in log]
    assert ("project", "updated") in actions
    upd = next(e for e in log if e["action"] == "updated")
    assert upd["before"] == {"name": "Onboarding research"}
    assert upd["after"] == {"name": "Activation research"}


def test_missing_project_404(client):
    assert client.get("/api/projects/00000000-0000-0000-0000-000000000000").status_code == 404


def test_delete_project_cascades(client, project):
    client.post(f"/api/projects/{project['id']}/interviews", json=VALID_INTERVIEW)
    assert client.delete(f"/api/projects/{project['id']}").status_code == 204
    assert client.get("/api/interviews").json() == []


# --- Module B/C: interviews -------------------------------------------------


def test_valid_interview_moves_project_to_collecting(client, project):
    resp = client.post(f"/api/projects/{project['id']}/interviews", json=VALID_INTERVIEW)
    assert resp.status_code == 201, resp.text
    interview = resp.json()
    assert interview["validation_status"] == "valid"
    assert "Participant ID: P01" in interview["raw_content"]

    p = client.get(f"/api/projects/{project['id']}").json()
    assert p["status"] == "collecting"
    assert p["interview_count"] == 1
    assert p["valid_interview_count"] == 1
    assert p["ready_for_synthesis"] is False  # fewer than 5 participants


def test_invalid_interview_reports_errors(client, project):
    resp = client.post(
        f"/api/projects/{project['id']}/interviews",
        json={"participant_id": "", "pain": "n/a", "behavior": ""},
    )
    body = resp.json()
    assert body["validation_status"] == "invalid"
    errors = {(i["field"], i["severity"]) for i in body["validation_errors"]}
    assert ("participant_id", "error") in errors
    assert ("pain", "error") in errors
    assert ("behavior", "error") in errors


def test_correction_never_touches_raw_content(client, project):
    raw = "Participant ID: P07\nPain: \nBehavior: logs bugs in Jira"
    created = client.post(
        f"/api/projects/{project['id']}/interviews",
        json={"participant_id": "P07", "behavior": "logs bugs in Jira daily", "raw_content": raw},
    ).json()
    assert created["validation_status"] == "invalid"

    fixed = client.patch(
        f"/api/interviews/{created['id']}",
        json={"pain": "Cannot see which bugs customers care about most.", "comment": "from recording"},
    ).json()
    assert fixed["validation_status"] == "valid"
    assert fixed["raw_content"] == raw  # original preserved

    # raw_content is not an accepted field on corrections
    assert (
        client.patch(f"/api/interviews/{created['id']}", json={"raw_content": "x"}).status_code
        == 422
    )

    log = client.get(f"/api/projects/{project['id']}/audit").json()
    corr = next(e for e in log if e["action"] == "corrected")
    assert corr["before"] == {"pain": ""}
    assert corr["comment"] == "from recording"


def test_correction_logs_only_changed_fields(client, project):
    created = client.post(f"/api/projects/{project['id']}/interviews", json=VALID_INTERVIEW).json()
    # Clients typically send every field back; only the edited one should be logged.
    client.patch(f"/api/interviews/{created['id']}", json={**VALID_INTERVIEW, "plan_tier": "Enterprise"})
    corr = next(e for e in client.get(f"/api/projects/{project['id']}/audit").json() if e["action"] == "corrected")
    assert corr["before"] == {"plan_tier": "Pro"}

    # A no-op save writes no audit entry.
    client.patch(f"/api/interviews/{created['id']}", json={**VALID_INTERVIEW, "plan_tier": "Enterprise"})
    log = client.get(f"/api/projects/{project['id']}/audit").json()
    assert sum(1 for e in log if e["action"] == "corrected") == 1


def test_ready_for_synthesis_counts_unique_participants(client, project):
    pid = project["id"]
    for n in range(4):
        client.post(f"/api/projects/{pid}/interviews", json={**VALID_INTERVIEW, "participant_id": f"P{n}"})
    # same participant twice must not count twice
    client.post(f"/api/projects/{pid}/interviews", json={**VALID_INTERVIEW, "participant_id": "p0"})
    p = client.get(f"/api/projects/{pid}").json()
    assert p["valid_interview_count"] == 5
    assert p["participant_count"] == 4
    assert p["ready_for_synthesis"] is False

    client.post(f"/api/projects/{pid}/interviews", json={**VALID_INTERVIEW, "participant_id": "P9"})
    assert client.get(f"/api/projects/{pid}").json()["ready_for_synthesis"] is True


def test_interview_search(client, project):
    client.post(f"/api/projects/{project['id']}/interviews", json=VALID_INTERVIEW)
    assert len(client.get("/api/interviews", params={"q": "spreadsheets"}).json()) == 1
    assert client.get("/api/interviews", params={"q": "zebra"}).json() == []


# --- Dashboard ---------------------------------------------------------------


def test_dashboard_uses_real_counts(client, project):
    empty = client.get("/api/dashboard").json()
    assert empty["total_projects"] == 1
    assert empty["total_interviews"] == 0

    client.post(f"/api/projects/{project['id']}/interviews", json=VALID_INTERVIEW)
    client.post(f"/api/projects/{project['id']}/interviews", json={"participant_id": "P2"})
    body = client.get("/api/dashboard").json()
    assert body["total_interviews"] == 2
    assert body["valid_interviews"] == 1
    assert body["themes_identified"] == 0
    assert body["projects_by_status"] == {"collecting": 1}
    kinds = [a["kind"] for a in body["recent_activity"]]
    assert "interview.created" in kinds and "project.created" in kinds
