"""Phase 2: project cards and the interview explorer (facets + interview -> findings)."""

from tests.test_acceptance import CONSISTENT, import_text, new_project, synthesise, themes


def test_project_list_carries_progress_fields(client):
    pid = new_project(client)
    [p] = client.get("/api/projects").json()
    assert p["review_total"] == 0 and p["report_count"] == 0 and p["min_participants"] == 5
    assert p["last_activity_at"] is not None

    import_text(client, pid, CONSISTENT)
    synthesise(client, pid)
    p = client.get(f"/api/projects/{pid}").json()
    assert p["review_total"] == p["pending_review_count"] > 0
    assert p["review_done"] == 0
    assert p["last_activity_at"] >= p["updated_at"]


def test_interview_facets_count_values(client):
    pid = new_project(client)
    import_text(client, pid, CONSISTENT)
    facets = client.get("/api/interviews/facets").json()
    for key in ("roles", "company_sizes", "plan_tiers"):
        assert facets[key], key
        assert sum(v["count"] for v in facets[key]) <= 8
    counts = [v["count"] for v in facets["plan_tiers"]]
    assert counts == sorted(counts, reverse=True)

    other = new_project(client, "Empty")
    assert client.get("/api/interviews/facets", params={"project_id": other}).json()["roles"] == []


def test_interview_findings_trace_forward_to_themes(client):
    pid = new_project(client)
    import_text(client, pid, CONSISTENT)
    interview = client.get("/api/interviews", params={"project_id": pid}).json()[0]

    before = client.get(f"/api/interviews/{interview['id']}/findings").json()
    assert before == {"synthesised": False, "pain_points": [], "themes": [], "insights": []}

    synthesise(client, pid)
    found = client.get(f"/api/interviews/{interview['id']}/findings").json()
    assert found["synthesised"] is True
    assert found["pain_points"], "every valid interview yields at least one pain point"

    # Each linked theme really cites this interview, and quotes come from its notes.
    live = {t["id"]: t for t in themes(client, pid)}
    for link in found["themes"]:
        theme = live[link["theme_id"]]
        assert any(e["interview_id"] == interview["id"] for e in theme["evidence"])
        assert interview["participant_id"] in theme["participant_ids"]
        for q in link["quotes"]:
            if q["verified"]:
                assert q["quote"].lower() in interview["raw_content"].lower()

    # Pain points that were clustered point at one of those themes.
    linked = {t["theme_id"] for t in found["themes"]}
    assert all(pp["theme_id"] in linked for pp in found["pain_points"] if pp["theme_id"])
    assert {i["theme_code"] for i in found["insights"]} <= {t["code"] for t in found["themes"]}


def test_interview_findings_404(client):
    r = client.get("/api/interviews/00000000-0000-0000-0000-000000000000/findings")
    assert r.status_code == 404
