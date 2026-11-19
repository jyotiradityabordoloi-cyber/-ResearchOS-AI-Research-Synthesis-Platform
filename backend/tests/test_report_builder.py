"""Phase 6: report builder options, live preview and exports."""

import pytest

from tests.test_acceptance import CONSISTENT, import_text, new_project, synthesise


@pytest.fixture
def project(client):
    pid = new_project(client)
    import_text(client, pid, CONSISTENT)
    synthesise(client, pid)
    return pid


def preview(client, pid, **body):
    r = client.post(f"/api/projects/{pid}/reports/preview", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_preview_does_not_save_and_matches_saved_report(client, project):
    pv = preview(client, project, kind="draft")
    assert client.get(f"/api/projects/{project}/reports").json() == []
    c = pv["content"]
    assert c["included_sections"][0] == "summary" and len(c["included_sections"]) == 12
    assert pv["markdown"].startswith(f"# {pv['title']}")
    assert "## Executive summary" in pv["markdown"] and "## 1. Research objective" in pv["markdown"]
    assert "## 11. Limitations" in pv["markdown"]
    assert c["summary"]["edited"] is False and c["summary"]["text"] == c["summary"]["generated"]

    saved = client.post(f"/api/projects/{project}/reports", json={"kind": "draft"}).json()
    assert saved["content_json"]["sections"]["frequency"] == c["sections"]["frequency"]


def test_auto_summary_uses_report_numbers(client, project):
    c = preview(client, project, kind="draft")["content"]
    text = c["summary"]["text"]
    top = c["sections"]["themes"][0]
    assert f"{top['participant_count']} of {top['total_participants']}" in text
    assert f"from {c['sections']['participants']['unique_participants']} participant" in text


def test_sections_subset_renumbers_everywhere(client, project):
    body = {"kind": "draft", "options": {"sections": ["limitations", "themes", "summary"]}}
    pv = preview(client, project, **body)
    assert pv["content"]["included_sections"] == ["summary", "themes", "limitations"]  # standard order
    md = pv["markdown"]
    assert "## 1. Top recurring themes" in md and "## 2. Limitations" in md
    assert "Research objective" not in md and "Supporting quotes" not in md

    saved = client.post(f"/api/projects/{project}/reports", json=body).json()
    pdf = client.get(f"/api/reports/{saved['id']}/export.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    md_export = client.get(f"/api/reports/{saved['id']}/export.md").text
    assert "## 2. Limitations" in md_export

    assert client.post(f"/api/projects/{project}/reports/preview", json={"options": {"sections": []}}).status_code == 422


def test_excluded_themes_are_disclosed(client, project):
    themes = client.get(f"/api/projects/{project}/themes").json()
    drop = next(t for t in themes if not t["requires_approval"])
    c = preview(client, project, kind="draft", options={"excluded_theme_ids": [drop["id"]]})["content"]
    codes = {f["code"] for f in c["sections"]["frequency"]}
    assert drop["code"] not in codes
    assert all(x["theme_code"] != drop["code"] for x in c["sections"]["implications"])
    assert c["excluded"]["by_choice"] == [{"code": drop["code"], "name": drop["name"]}]
    assert any(drop["name"] in line and "left" in line for line in c["sections"]["limitations"])
    assert "left out by the team" in c["summary"]["text"]


def test_custom_summary_and_audit(client, project):
    body = {"kind": "draft", "title": "Board pack", "options": {"executive_summary": "  Our own words.  "}}
    pv = preview(client, project, **body)
    assert pv["content"]["summary"] == {
        "text": "Our own words.", "generated": pv["content"]["summary"]["generated"], "edited": True,
    }
    assert pv["title"] == "Board pack" and "Our own words." in pv["markdown"]
    saved = client.post(f"/api/projects/{project}/reports", json=body).json()
    entry = next(a for a in client.get(f"/api/projects/{project}/audit").json() if a["entity_type"] == "report")
    assert entry["entity_id"] == saved["id"] and entry["after"]["summary_edited"] is True


def test_sensitive_findings_cannot_be_forced_in(client, project):
    themes = client.get(f"/api/projects/{project}/themes").json()
    sensitive = [t for t in themes if t["requires_approval"]]
    if not sensitive:
        pytest.skip("sample produced no sensitive theme")
    c = preview(client, project, kind="draft", options={"excluded_theme_ids": []})["content"]
    codes = {f["code"] for f in c["sections"]["frequency"]}
    assert not codes & {t["code"] for t in sensitive}
    assert {x["code"] for x in c["excluded"]["sensitive_pending"]} == {t["code"] for t in sensitive}


def test_approved_report_needs_an_included_theme(client, project):
    theme = next(t for t in client.get(f"/api/projects/{project}/themes").json() if not t["requires_approval"])
    client.post(f"/api/themes/{theme['id']}/review", json={"decision": "approve"})
    ok = client.post(f"/api/projects/{project}/reports/preview", json={"kind": "approved"})
    assert ok.status_code == 200
    r = client.post(
        f"/api/projects/{project}/reports/preview",
        json={"kind": "approved", "options": {"excluded_theme_ids": [theme["id"]]}},
    )
    assert r.status_code == 422 and "excluded" in r.json()["detail"]
