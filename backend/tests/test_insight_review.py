"""Phase 4: insight review context, evidence, comments and manual sensitive flags."""

import pytest

from tests.test_acceptance import CONSISTENT, import_text, new_project, synthesise


@pytest.fixture
def project(client):
    pid = new_project(client)
    import_text(client, pid, CONSISTENT)
    synthesise(client, pid)
    return pid


def insights(client, pid):
    return client.get(f"/api/projects/{pid}/insights").json()


def test_insights_carry_theme_and_evidence_counts(client, project):
    themes = {t["id"]: t for t in client.get(f"/api/projects/{project}/themes").json()}
    rows = insights(client, project)
    assert rows
    for i in rows:
        theme = themes[i["theme_id"]]
        assert i["theme_name"] == theme["name"]
        assert i["participant_count"] == theme["participant_count"]
        assert i["evidence_count"] == sum(e["stance"] == "supporting" for e in theme["evidence"])
        assert i["contradicting_count"] == sum(e["stance"] == "contradicting" for e in theme["evidence"])
        # Frequency, severity and strategic relevance stay separate numbers.
        assert {"frequency", "severity", "strategic_relevance", "confidence"} <= set(i)
    everywhere = client.get("/api/insights", params={"project_id": project}).json()
    assert {i["id"]: i["evidence_count"] for i in everywhere} == {i["id"]: i["evidence_count"] for i in rows}


def test_insight_evidence_traces_to_interviews(client, project):
    insight = insights(client, project)[0]
    r = client.get(f"/api/insights/{insight['id']}/evidence")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["theme"]["id"] == insight["theme_id"]
    assert len([e for e in body["evidence"] if e["stance"] == "supporting"]) == insight["evidence_count"]
    for e in body["evidence"]:
        interview = client.get(f"/api/interviews/{e['interview_id']}").json()
        assert interview["participant_id"] == e["participant_id"]
        assert e["participant_role"] == interview["participant_role"]
        if e["quote_verified"]:
            assert e["quote"].lower() in interview["raw_content"].lower()


def test_comments_thread_and_history(client, project):
    insight = insights(client, project)[0]
    url = f"/api/insights/{insight['id']}"
    assert client.post(f"{url}/comments", json={"text": ""}).status_code == 422
    r = client.post(f"{url}/comments", json={"text": "Check this against the churn survey."})
    assert r.status_code == 201 and r.json()["action"] == "review_comment"
    client.post(f"{url}/comments", json={"text": "Agreed, it matches."})
    after = next(i for i in insights(client, project) if i["id"] == insight["id"])
    assert after["comment_count"] == 2

    client.post(f"{url}/review", json={"decision": "reject", "comment": "Too thin"})
    history = client.get(f"{url}/history").json()
    assert [h["action"] for h in history][:3] == ["reject", "review_comment", "review_comment"]
    assert history[1]["comment"] == "Agreed, it matches." and history[1]["actor"]


def test_flag_sensitive_requires_acknowledged_approval(client, project):
    plain = next(i for i in insights(client, project) if not i["requires_approval"])
    url = f"/api/insights/{plain['id']}"
    assert client.post(f"{url}/review", json={"decision": "approve"}).json()["status"] == "approved"

    bad = client.post(f"{url}/sensitive", json={"tags": ["gossip"], "reason": "x"})
    assert bad.status_code == 422
    r = client.post(f"{url}/sensitive", json={"tags": ["pricing"], "reason": "Mentions a discount we can't share."})
    assert r.status_code == 200, r.text
    flagged = r.json()
    assert flagged["requires_approval"] is True and "pricing" in flagged["sensitive_tags"]
    assert flagged["status"] == "proposed"  # approval was reset

    assert client.post(f"{url}/review", json={"decision": "approve"}).status_code == 422
    ok = client.post(f"{url}/review", json={"decision": "approve", "acknowledge_sensitive": True, "comment": "Reviewed with legal"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"

    # Flagging the same tag again changes nothing and writes no audit entry.
    n = len(client.get(f"{url}/history").json())
    client.post(f"{url}/sensitive", json={"tags": ["pricing"], "reason": "again"})
    assert len(client.get(f"{url}/history").json()) == n
