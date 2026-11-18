"""Module G (reports) and Module H (repository)."""

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


def _themes(client, pid):
    return client.get(f"/api/projects/{pid}/themes").json()


def _report(client, pid, kind="draft"):
    resp = client.post(f"/api/projects/{pid}/reports", json={"kind": kind})
    return resp


# --- Reports ----------------------------------------------------------------------


def test_report_requires_synthesis(client, project):
    assert _report(client, project["id"]).status_code == 422


def test_draft_report_has_all_sections_and_withholds_sensitive(client, synthesised):
    pid = synthesised
    resp = _report(client, pid)
    assert resp.status_code == 201, resp.text
    r = resp.json()
    md = r["content_markdown"]
    for n, title in enumerate(
        [
            "Research objective", "Participant overview", "Research methodology", "Top recurring themes",
            "Participant frequency", "Supporting quotes", "Contradictory findings", "High-impact outliers",
            "Product implications", "Recommended next steps", "Limitations",
        ],
        start=1,
    ):
        assert f"## {n}. {title}" in md
    c = r["content_json"]
    names = {f["name"] for f in c["sections"]["frequency"]}
    sensitive = [t for t in _themes(client, pid) if t["requires_approval"]]
    assert sensitive and not (names & {t["name"] for t in sensitive})  # never in report while unapproved
    assert r["excluded_sensitive_count"] == len(sensitive)
    assert any("sensitive finding" in x for x in c["sections"]["limitations"])
    assert "DRAFT" in md and "unreviewed" in md
    assert c["sections"]["participants"]["unique_participants"] == 11
    # Contradictions and outliers are carried into the report with evidence.
    assert any(x["participant_id"] == "P09" for x in c["sections"]["contradictions"])
    assert any("P10" in t["participant_ids"] for t in c["sections"]["outliers"])
    # Quotes in the report are verified quotes from the notes.
    assert all(q["quote"] for block in c["sections"]["quotes"] for q in block["quotes"])


def test_approved_report_only_contains_approved_findings(client, synthesised):
    pid = synthesised
    assert _report(client, pid, "approved").status_code == 422  # nothing approved yet

    themes = _themes(client, pid)
    plain = next(t for t in themes if not t["requires_approval"] and not t["is_outlier"])
    churn = next(t for t in themes if "P12" in t["participant_ids"])
    client.post(f"/api/themes/{plain['id']}/review", json={"decision": "approve"})
    client.post(
        f"/api/themes/{churn['id']}/review",
        json={"decision": "approve", "acknowledge_sensitive": True, "comment": "Confirmed with CS"},
    )
    r = _report(client, pid, "approved").json()
    assert r["status"] == "approved"
    included = {f["name"] for f in r["content_json"]["sections"]["frequency"]}
    assert included == {plain["name"], churn["name"]}
    assert "sensitive, approved" in r["content_markdown"] or churn["is_outlier"]
    assert all(x["reviewed"] for x in r["content_json"]["sections"]["implications"])
    assert r["content_json"]["excluded"]["unreviewed"] > 0
    assert client.get(f"/api/projects/{pid}").json()["status"] == "completed"
    assert ("report", "generated") in [(e["entity_type"], e["action"]) for e in client.get(f"/api/projects/{pid}/audit").json()]


def test_manual_override_shows_in_report(client, synthesised):
    pid = synthesised
    ins = client.get(f"/api/projects/{pid}/insights").json()
    target = next(i for i in ins if not i["requires_approval"] and i["effective_priority"] != "high")
    client.patch(f"/api/insights/{target['id']}", json={"priority_override": "high", "override_reason": "Exec ask"})
    impl = _report(client, pid).json()["content_json"]["sections"]["implications"]
    row = next(x for x in impl if x["title"] == target["title"])
    assert row["overridden"] and row["priority"] == "high" and row["computed_priority"] == target["computed_priority"]


def test_markdown_and_pdf_exports(client, synthesised):
    rid = _report(client, synthesised).json()["id"]
    md = client.get(f"/api/reports/{rid}/export.md")
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert "attachment" in md.headers["content-disposition"] and md.text.startswith("# ")
    pdf = client.get(f"/api/reports/{rid}/export.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:5] == b"%PDF-" and len(pdf.content) > 3000


def test_report_listing_and_delete(client, synthesised):
    rid = _report(client, synthesised).json()["id"]
    assert [r["id"] for r in client.get("/api/reports").json()] == [rid]
    assert client.get(f"/api/projects/{synthesised}/reports").json()[0]["project_name"]
    assert client.delete(f"/api/reports/{rid}").status_code == 204
    assert client.get(f"/api/reports/{rid}").status_code == 404


# --- Repository ------------------------------------------------------------------------


def test_keyword_search_finds_quotes_and_links_evidence(client, synthesised):
    hits = client.get("/api/repository/search", params={"q": "connector"}).json()
    assert hits
    theme = next(h for h in hits if h["kind"] == "theme")
    assert theme["project_name"] and theme["evidence"]
    iv = client.get(f"/api/interviews/{theme['evidence'][0]['interview_id']}").json()
    assert iv["participant_id"] == theme["evidence"][0]["participant_id"]  # original evidence reachable


def test_theme_mode_matches_names_only(client, synthesised):
    name = _themes(client, synthesised)[0]["name"]
    word = name.split()[0]
    hits = client.get("/api/repository/search", params={"q": word, "mode": "theme"}).json()
    assert hits and all(word.lower() in h["title"].lower() for h in hits)


def test_semantic_search_ranks_by_similarity(client, synthesised):
    hits = client.get(
        "/api/repository/search", params={"q": "dashboards take too long to load", "mode": "semantic"}
    ).json()
    assert hits and hits[0]["kind"] == "theme"
    assert "slow" in hits[0]["title"].lower() or "dashboard" in hits[0]["title"].lower()
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True) and all(0 < s <= 1.0001 for s in scores)
    assert client.get("/api/repository/search", params={"q": " ", "mode": "semantic"}).status_code == 422


def test_segment_and_status_filters(client, synthesised):
    enterprise = client.get("/api/repository/search", params={"plan_tier": "Enterprise pilot"}).json()
    assert enterprise and all({"P07", "P10"} & set(h["participant_ids"]) for h in enterprise)
    assert client.get("/api/repository/search", params={"approved_only": True}).json() == []
    facets = client.get("/api/repository/facets").json()
    assert "Enterprise pilot" in facets["plan_tiers"] and facets["projects"]


def test_rejected_findings_leave_the_repository(client, synthesised):
    t = _themes(client, synthesised)[0]
    client.post(f"/api/themes/{t['id']}/review", json={"decision": "reject"})
    ids = [h["id"] for h in client.get("/api/repository/search").json()]
    assert t["id"] not in ids
