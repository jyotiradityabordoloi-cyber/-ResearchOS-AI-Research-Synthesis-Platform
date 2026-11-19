"""Phase 3: theme canvas operations and their exact inverses (undo/redo)."""

import pytest

from tests.test_acceptance import CONSISTENT, import_text, new_project, synthesise


def themes(client, pid):
    return client.get(f"/api/projects/{pid}/themes", params={"include_rejected": True}).json()


def state(client, pid):
    """Everything a reviewer can see about the grouping, independent of evidence ids."""
    return {
        t["id"]: {
            "name": t["name"],
            "description": t["description"],
            "status": t["status"],
            "frequency": t["frequency"],
            "participants": t["participant_ids"],
            "evidence": sorted((e["interview_id"], e["quote"], e["stance"]) for e in t["evidence"]),
        }
        for t in themes(client, pid)
    }


@pytest.fixture
def project(client):
    pid = new_project(client)
    import_text(client, pid, CONSISTENT)
    synthesise(client, pid)
    return pid


def big_theme(client, pid):
    return max(themes(client, pid), key=lambda t: len(t["evidence"]))


def test_observations_cover_every_pain_point(client, project):
    obs = client.get(f"/api/projects/{project}/observations").json()
    assert obs and all(o["participant_role"] for o in obs)
    linked = {e["pain_point_id"] for t in themes(client, project) for e in t["evidence"] if e["pain_point_id"]}
    assert linked <= {o["id"] for o in obs}


def test_create_attach_detach_delete_round_trip(client, project):
    start = state(client, project)
    created = client.post(f"/api/projects/{project}/themes", json={"name": "Onboarding friction", "description": ""})
    assert created.status_code == 201, created.text
    new = created.json()
    assert new["origin"] == "manual" and new["participant_count"] == 0 and new["code"].startswith("T")

    # Drag an observation that already sits in a theme: it moves, and the source is reported.
    source = big_theme(client, project)
    ev = next(e for e in source["evidence"] if e["pain_point_id"] and e["stance"] == "supporting")
    r = client.post(f"/api/themes/{new['id']}/observations", json={"pain_point_id": ev["pain_point_id"]})
    assert r.status_code == 201, r.text
    assert r.json()["moved_from_theme_id"] == source["id"] and r.json()["evidence"]["id"] == ev["id"]
    moved = next(t for t in themes(client, project) if t["id"] == new["id"])
    assert moved["participant_count"] == 1 and moved["frequency"] > 0

    # Undo the move, then delete the (now empty) theme: back to the start.
    r = client.post(f"/api/evidence/{ev['id']}/move", json={"target_theme_id": source["id"]})
    assert r.status_code == 200, r.text
    assert client.delete(f"/api/themes/{new['id']}").status_code == 200
    after = state(client, project)
    for tid in start:  # approval may have been reset by the regrouping, nothing else changes
        after[tid]["status"] = start[tid]["status"]
    assert after == start


def test_attach_unassigned_then_detach(client, project):
    obs = client.get(f"/api/projects/{project}/observations").json()
    target = big_theme(client, project)
    # Free an observation first so it is unassigned.
    ev = next(e for e in target["evidence"] if e["pain_point_id"])
    snap = client.delete(f"/api/evidence/{ev['id']}")
    assert snap.status_code == 200, snap.text
    assert snap.json()["pain_point_id"] == ev["pain_point_id"]
    assert ev["pain_point_id"] in {o["id"] for o in obs}

    r = client.post(
        f"/api/themes/{target['id']}/observations", json={"pain_point_id": ev["pain_point_id"], "stance": "contradicting"}
    )
    assert r.status_code == 201, r.text
    assert r.json()["moved_from_theme_id"] is None
    new_ev = r.json()["evidence"]
    assert new_ev["stance"] == "contradicting" and new_ev["quote"] == ev["quote"]
    t = next(t for t in themes(client, project) if t["id"] == target["id"])
    assert t["has_contradictions"] is True

    # Attaching twice is refused.
    again = client.post(f"/api/themes/{target['id']}/observations", json={"pain_point_id": ev["pain_point_id"]})
    assert again.status_code == 422


def test_stance_toggle_and_guard(client, project):
    theme = big_theme(client, project)
    supporting = [e for e in theme["evidence"] if e["stance"] == "supporting"]
    r = client.patch(f"/api/evidence/{supporting[0]['id']}", json={"stance": "contradicting"})
    assert r.status_code == 200 and r.json()["has_contradictions"] is True
    assert r.json()["participant_count"] <= theme["participant_count"]
    back = client.patch(f"/api/evidence/{supporting[0]['id']}", json={"stance": "supporting"})
    assert back.json()["participant_count"] == theme["participant_count"]

    # Demote all but one supporting item; the last one is protected.
    for e in supporting[1:]:
        assert client.patch(f"/api/evidence/{e['id']}", json={"stance": "contradicting"}).status_code == 200
    only = supporting[0]
    assert client.patch(f"/api/evidence/{only['id']}", json={"stance": "contradicting"}).status_code == 422
    assert client.delete(f"/api/evidence/{only['id']}").status_code == 422  # AI theme keeps its last item


def test_merge_then_unmerge_restores_everything(client, project):
    start = state(client, project)
    a, b, c = sorted(themes(client, project), key=lambda t: -t["participant_count"])[:3]
    r = client.post(
        f"/api/projects/{project}/themes/merge",
        json={"theme_ids": [a["id"], b["id"], c["id"]], "name": "Combined theme", "description": "Merged."},
    )
    assert r.status_code == 200, r.text
    assert {t["id"] for t in themes(client, project)} == set(start) - {b["id"], c["id"]}

    r = client.post(f"/api/themes/{a['id']}/unmerge")
    assert r.status_code == 200, r.text
    assert set(r.json()["restored_theme_ids"]) == {b["id"], c["id"]}
    assert state(client, project) == start

    # A second unmerge has nothing left to undo.
    assert client.post(f"/api/themes/{a['id']}/unmerge").status_code == 409


def test_split_undone_by_deleting_the_new_theme(client, project):
    start = state(client, project)
    theme = big_theme(client, project)
    moving = [e["id"] for e in theme["evidence"] if e["stance"] == "supporting"][:1]
    r = client.post(f"/api/themes/{theme['id']}/split", json={"evidence_ids": moving, "name": "Split part"})
    assert r.status_code == 201, r.text
    new = r.json()
    r = client.delete(f"/api/themes/{new['id']}")
    assert r.status_code == 200 and r.json()["evidence_returned_to"] == theme["id"]
    after = state(client, project)
    after[theme["id"]]["status"] = start[theme["id"]]["status"]
    assert after == start
    insights = client.get(f"/api/projects/{project}/insights").json()
    assert all(i["theme_id"] != new["id"] for i in insights)


def test_ai_themes_cannot_be_deleted(client, project):
    theme = themes(client, project)[0]
    assert client.delete(f"/api/themes/{theme['id']}").status_code == 422


def test_create_theme_requires_synthesis(client):
    pid = new_project(client)
    r = client.post(f"/api/projects/{pid}/themes", json={"name": "Too early"})
    assert r.status_code == 409
