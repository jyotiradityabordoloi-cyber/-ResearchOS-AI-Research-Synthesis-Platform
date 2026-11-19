"""Dashboard command centre: every panel is computed from live rows."""

from datetime import UTC, datetime

from tests.test_acceptance import CONSISTENT, import_text, new_project, synthesise, themes


def test_empty_dashboard_has_zeroed_panels(client):
    d = client.get("/api/dashboard").json()
    assert d["total_projects"] == 0
    assert len(d["interview_activity"]) == 30
    assert all(day["valid"] == 0 and day["needs_fixes"] == 0 for day in d["interview_activity"])
    assert d["project_progress"] == [] and d["review_queue"] == [] and d["top_findings"] == []
    assert d["review_counts"] == {"proposed": 0, "approved": 0, "rejected": 0}


def test_dashboard_reflects_synthesis_and_review(client):
    pid = new_project(client)
    import_text(client, pid, CONSISTENT)
    synthesise(client, pid)

    d = client.get("/api/dashboard").json()
    today = datetime.now(UTC).date().isoformat()
    assert d["interview_activity"][-1] == {"day": today, "valid": 8, "needs_fixes": 0}

    [progress] = d["project_progress"]
    assert progress["project_id"] == pid
    assert progress["participants"] == 8 and progress["valid_interviews"] == 8
    assert progress["themes"] == d["themes_identified"] > 0
    assert progress["review_done"] == 0 and progress["review_total"] == d["pending_reviews"]

    # The queue lists exactly the pending items, sensitive ones first.
    assert len(d["review_queue"]) == min(8, d["pending_reviews"])
    flags = [i["requires_approval"] for i in d["review_queue"]]
    assert flags == sorted(flags, reverse=True)

    [run] = d["recent_runs"]
    assert run["status"] == "completed" and run["themes"] >= progress["themes"]
    assert d["top_findings"] and {f["priority"] for f in d["top_findings"]} <= {"high", "medium", "low"}

    # Approving a theme moves it from the queue into the reviewed count.
    theme = next(t for t in themes(client, pid) if not t["requires_approval"])
    r = client.post(f"/api/themes/{theme['id']}/review", json={"decision": "approve"})
    assert r.status_code == 200, r.text
    after = client.get("/api/dashboard").json()
    approved = after["review_counts"]["approved"]
    assert approved >= 1  # the theme (approving it may also settle its linked insight)
    assert after["project_progress"][0]["review_done"] == approved
    assert after["pending_reviews"] == d["pending_reviews"] - approved
    assert theme["id"] not in {i["id"] for i in after["review_queue"]}


def test_interview_list_filters_used_by_dashboard_links(client):
    pid = new_project(client)
    import_text(client, pid, CONSISTENT)
    everyone = client.get("/api/interviews", params={"project_id": pid}).json()
    sample = everyone[0]

    today = datetime.now(UTC).date().isoformat()
    assert len(client.get("/api/interviews", params={"created_on": today}).json()) == len(everyone)
    assert client.get("/api/interviews", params={"created_on": "2001-01-01"}).json() == []

    by_role = client.get("/api/interviews", params={"role": sample["participant_role"].upper()}).json()
    assert by_role and all(i["participant_role"] == sample["participant_role"] for i in by_role)
    by_tier = client.get("/api/interviews", params={"plan_tier": sample["plan_tier"]}).json()
    assert by_tier and all(i["plan_tier"] == sample["plan_tier"] for i in by_tier)
