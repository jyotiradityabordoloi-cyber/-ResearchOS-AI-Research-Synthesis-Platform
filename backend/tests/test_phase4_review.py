"""Modules E & F: human review, regrouping and prioritisation."""

from pathlib import Path

import pytest

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


@pytest.fixture
def synthesised(client, project):
    pid = project["id"]
    text = "\n---\n".join(
        (SAMPLES / f).read_text(encoding="utf-8") for f in ("interviews-consistent.md", "interviews-edge-cases.md")
    )
    preview = client.post(f"/api/projects/{pid}/import/preview", json={"text": text}).json()
    client.post(
        f"/api/projects/{pid}/import",
        json={"items": [{"fields": i["fields"], "raw_content": i["raw_content"]} for i in preview["items"]]},
    )
    assert client.post(f"/api/projects/{pid}/synthesis", json={}).status_code == 202
    return pid


def themes(client, pid, **params):
    return client.get(f"/api/projects/{pid}/themes", params=params).json()


def by_participant(client, pid, participant):
    return next(t for t in themes(client, pid) if participant in t["participant_ids"])


def audit_actions(client, pid):
    return [(e["entity_type"], e["action"]) for e in client.get(f"/api/projects/{pid}/audit").json()]


# --- Edit / rename / flag ------------------------------------------------------------


def test_rename_and_edit_are_audited_and_marked(client, synthesised):
    pid = synthesised
    t = themes(client, pid)[0]
    resp = client.patch(f"/api/themes/{t['id']}", json={"name": "Slow dashboards block customer calls", "comment": "clearer"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Slow dashboards block customer calls" and body["human_edited"]

    client.patch(f"/api/themes/{t['id']}", json={"implication": "Cache heavy dashboards.", "strategic_flag": True})
    body = client.get(f"/api/themes/{t['id']}/history").json()
    assert [e["action"] for e in body][:2] == ["edit", "rename"]
    assert body[1]["before"]["name"] == t["name"] and body[1]["comment"] == "clearer"
    insight = next(i for i in client.get(f"/api/projects/{pid}/insights").json() if i["theme_id"] == t["id"])
    assert insight["implication"] == "Cache heavy dashboards."


def test_extra_fields_rejected(client, synthesised):
    t = themes(client, synthesised)[0]
    assert client.patch(f"/api/themes/{t['id']}", json={"frequency": 1.0}).status_code == 422


# --- Approve / reject (fallback D) -----------------------------------------------------


def test_sensitive_theme_needs_acknowledgement(client, synthesised):
    pid = synthesised
    churn = by_participant(client, pid, "P12")
    assert churn["requires_approval"]
    url = f"/api/themes/{churn['id']}/review"
    assert client.post(url, json={"decision": "approve"}).status_code == 422
    assert client.post(url, json={"decision": "approve", "acknowledge_sensitive": True}).status_code == 422  # no reason
    ok = client.post(url, json={"decision": "approve", "acknowledge_sensitive": True, "comment": "Confirmed with CS"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    entry = next(e for e in client.get(f"/api/themes/{churn['id']}/history").json() if e["action"] == "approve")
    assert set(entry["after"]["sensitive_tags"]) >= {"churn", "competitive_switching"}


def test_approve_and_reject_cascade_to_ai_insight_and_counts(client, synthesised):
    pid = synthesised
    before = client.get(f"/api/projects/{pid}").json()["pending_review_count"]
    perf = by_participant(client, pid, "P07")
    assert not perf["requires_approval"]
    client.post(f"/api/themes/{perf['id']}/review", json={"decision": "approve"})
    insight = next(i for i in client.get(f"/api/projects/{pid}/insights").json() if i["theme_id"] == perf["id"])
    assert insight["status"] == "approved"
    assert client.get(f"/api/projects/{pid}").json()["pending_review_count"] == before - 2

    access = next(t for t in themes(client, pid) if t["name"].startswith("Access control"))
    client.post(f"/api/themes/{access['id']}/review", json={"decision": "reject", "comment": "Not a real cluster"})
    assert access["id"] not in [t["id"] for t in themes(client, pid)]
    assert access["id"] in [t["id"] for t in themes(client, pid, include_rejected=True)]
    client.post(f"/api/themes/{access['id']}/review", json={"decision": "reopen"})
    assert access["id"] in [t["id"] for t in themes(client, pid)]


# --- Merge / split / move (fallback F) --------------------------------------------------


def test_merge_counts_each_participant_once(client, synthesised):
    pid = synthesised
    ts = themes(client, pid)
    pricing = next(t for t in ts if t["name"].startswith("Pricing"))
    churn = by_participant(client, pid, "P12")
    client.post(f"/api/themes/{pricing['id']}/review", json={"decision": "approve", "acknowledge_sensitive": True, "comment": "ok"})

    resp = client.post(
        f"/api/projects/{pid}/themes/merge",
        json={"theme_ids": [pricing["id"], churn["id"]], "name": "Cost drives churn risk", "comment": "same root cause"},
    )
    assert resp.status_code == 200, resp.text
    merged = resp.json()
    expected = set(pricing["participant_ids"]) | set(churn["participant_ids"])
    assert set(merged["participant_ids"]) == expected
    assert merged["participant_count"] == len(expected)
    assert merged["frequency"] == pytest.approx(len(expected) / merged["total_participants"], abs=1e-4)
    assert merged["status"] == "proposed"  # evidence changed, approval reset
    assert merged["requires_approval"] and "churn" in merged["sensitive_tags"]
    assert churn["id"] not in [t["id"] for t in themes(client, pid, include_rejected=True)]
    insight = next(i for i in client.get(f"/api/projects/{pid}/insights").json() if i["theme_id"] == merged["id"])
    assert insight["title"] == "Cost drives churn risk"
    assert ("theme", "merge") in audit_actions(client, pid)
    assert ("theme", "approval_reset") in audit_actions(client, pid)


def test_merge_needs_two_themes(client, synthesised):
    t = themes(client, synthesised)[0]
    resp = client.post(f"/api/projects/{synthesised}/themes/merge", json={"theme_ids": [t["id"], t["id"]]})
    assert resp.status_code == 422


def test_split_creates_new_theme_and_recomputes(client, synthesised):
    pid = synthesised
    sharing = next(t for t in themes(client, pid) if t["name"].startswith("Sharing"))
    moving = [e for e in sharing["evidence"] if e["participant_id"] == "P03"]
    assert moving
    resp = client.post(
        f"/api/themes/{sharing['id']}/split",
        json={"evidence_ids": [e["id"] for e in moving], "name": "PDF exports break formatting"},
    )
    assert resp.status_code == 201, resp.text
    new = resp.json()
    assert new["participant_ids"] == ["P03"] and new["is_outlier"] and new["origin"] == "manual"
    assert new["split_from_id"] == sharing["id"]
    after = next(t for t in themes(client, pid) if t["id"] == sharing["id"])
    assert "P03" not in after["participant_ids"]
    assert after["participant_count"] == sharing["participant_count"] - 1
    assert any(i["theme_id"] == new["id"] for i in client.get(f"/api/projects/{pid}/insights").json())


def test_split_cannot_empty_the_source(client, synthesised):
    t = themes(client, synthesised)[0]
    supporting = [e["id"] for e in t["evidence"] if e["stance"] == "supporting"]
    resp = client.post(f"/api/themes/{t['id']}/split", json={"evidence_ids": supporting, "name": "Everything"})
    assert resp.status_code == 422


def test_move_evidence_regroups(client, synthesised):
    pid = synthesised
    ts = themes(client, pid)
    access = next(t for t in ts if t["name"].startswith("Access control"))
    integration = next(t for t in ts if t["name"].startswith("Connecting data"))
    ev = next(e for e in access["evidence"] if e["participant_id"] == "P02")
    resp = client.post(f"/api/evidence/{ev['id']}/move", json={"target_theme_id": integration["id"]})
    assert resp.status_code == 200, resp.text
    source, target = resp.json()
    assert "P02" not in source["participant_ids"] and "P02" in target["participant_ids"]
    assert target["participant_count"] == integration["participant_count"] + 1
    assert ("evidence", "move_evidence") in audit_actions(client, pid)


def test_manual_evidence_must_be_verbatim(client, synthesised):
    pid = synthesised
    t = themes(client, pid)[0]
    iv = next(i for i in client.get(f"/api/projects/{pid}/interviews").json() if i["participant_id"] == "P08")
    bad = client.post(f"/api/themes/{t['id']}/evidence", json={"interview_id": iv["id"], "quote": "I love this product"})
    assert bad.status_code == 422
    good = client.post(
        f"/api/themes/{t['id']}/evidence",
        json={"interview_id": iv["id"], "quote": "PDF department", "stance": "supporting"},
    )
    assert good.status_code == 201 and good.json()["quote_verified"]
    assert "P08" in next(x for x in themes(client, pid) if x["id"] == t["id"])["participant_ids"]


# --- Prioritisation (Module E) ------------------------------------------------------------


def test_override_is_marked_and_keeps_frequency_separate(client, synthesised):
    pid = synthesised
    insights = client.get(f"/api/projects/{pid}/insights").json()
    low = next(i for i in insights if i["effective_priority"] != "high")
    url = f"/api/insights/{low['id']}"
    assert client.patch(url, json={"priority_override": "high"}).status_code == 422  # reason required
    resp = client.patch(url, json={"priority_override": "high", "override_reason": "Blocks enterprise deals"})
    body = resp.json()
    assert body["is_overridden"] and body["effective_priority"] == "high"
    assert body["computed_priority"] == low["computed_priority"]
    assert body["priority_score"] == low["priority_score"] and body["frequency"] == low["frequency"]

    ordered = client.get(f"/api/projects/{pid}/insights").json()
    highs = [i["id"] for i in ordered if i["effective_priority"] == "high"]
    assert low["id"] in highs and ordered.index(next(i for i in ordered if i["id"] == low["id"])) < len(highs)

    cleared = client.patch(url, json={"priority_override": None}).json()
    assert not cleared["is_overridden"] and cleared["override_reason"] is None
    assert ("insight", "override_priority") in audit_actions(client, pid)


def test_severity_change_rescores_but_not_frequency(client, synthesised):
    pid = synthesised
    i = client.get(f"/api/projects/{pid}/insights").json()[-1]
    body = client.patch(f"/api/insights/{i['id']}", json={"severity": 5, "strategic_relevance": 5}).json()
    assert body["priority_score"] > i["priority_score"]
    assert body["frequency"] == i["frequency"]


def test_pm_comment_and_manual_insight(client, synthesised):
    pid = synthesised
    i = client.get(f"/api/projects/{pid}/insights").json()[0]
    assert client.patch(f"/api/insights/{i['id']}", json={"pm_comment": "Discuss in roadmap review"}).json()["pm_comment"]

    plain = client.post(
        f"/api/projects/{pid}/insights",
        json={"title": "Onboarding checklist would help", "severity": 2, "strategic_relevance": 4},
    ).json()
    assert plain["origin"] == "manual" and plain["status"] == "approved" and plain["frequency"] == 0

    sensitive = client.post(
        f"/api/projects/{pid}/insights",
        json={"title": "Customers may switch to Metabase over price", "severity": 4, "strategic_relevance": 5},
    ).json()
    assert sensitive["requires_approval"] and sensitive["status"] == "proposed"
    url = f"/api/insights/{sensitive['id']}/review"
    assert client.post(url, json={"decision": "approve"}).status_code == 422
    assert client.post(url, json={"decision": "approve", "acknowledge_sensitive": True, "comment": "ok"}).status_code == 200


def test_global_insights_endpoint(client, synthesised):
    rows = client.get("/api/insights").json()
    assert rows and all(r["project_name"] for r in rows)
    assert client.get("/api/insights", params={"q": "zzzz-none"}).json() == []


def test_old_run_themes_are_read_only(client, synthesised):
    pid = synthesised
    old = themes(client, pid)[0]
    client.post(f"/api/projects/{pid}/synthesis", json={})
    assert client.patch(f"/api/themes/{old['id']}", json={"name": "Renamed late"}).status_code == 409
