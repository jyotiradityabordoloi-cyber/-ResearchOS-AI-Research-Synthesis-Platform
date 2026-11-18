"""Acceptance tests 1, 3, 4, 5, 6 and 7 against the offline demo engine.

The demo engine is deterministic, so these assert real pipeline behaviour (dedupe,
frequency arithmetic, evidence linking, contradictions, outliers, sensitivity,
failure safety) without network access.
"""

from pathlib import Path

import pytest

from app.ai.embeddings import HashEmbedder
from app.ai.engine import DemoEngine
from app.ai.providers import LLMError
from app.api.routes.synthesis import AI, get_ai
from app.main import app

SAMPLES = Path(__file__).resolve().parents[2] / "samples"


def _import(client, pid, *files):
    text = "\n---\n".join((SAMPLES / f).read_text(encoding="utf-8") for f in files)
    preview = client.post(f"/api/projects/{pid}/import/preview", json={"text": text}).json()
    items = [{"fields": i["fields"], "raw_content": i["raw_content"], "source": "paste"} for i in preview["items"]]
    res = client.post(f"/api/projects/{pid}/import", json={"items": items}).json()
    assert not res["skipped"], res["skipped"]
    return res["created"]


def _synthesise(client, pid, **body):
    resp = client.post(f"/api/projects/{pid}/synthesis", json=body)
    assert resp.status_code == 202, resp.text
    run = client.get(f"/api/projects/{pid}/synthesis/runs").json()[0]
    return run


def _themes(client, pid):
    return client.get(f"/api/projects/{pid}/themes").json()


# --- Test 1: eight consistent interviews ------------------------------------------


def test_consistent_interviews_produce_reasonable_themes(client, project):
    pid = project["id"]
    interviews = _import(client, pid, "interviews-consistent.md")
    run = _synthesise(client, pid)
    assert run["status"] == "completed", run["error"]
    assert run["is_active"] and run["is_demo"]

    themes = _themes(client, pid)
    assert 4 <= len(themes) <= 6
    ids_by_interview = {i["id"]: i["participant_id"] for i in interviews}
    for t in themes:
        # Frequency is deterministic arithmetic over unique participants.
        assert t["total_participants"] == 8
        assert t["participant_count"] == len(set(t["participant_ids"]))
        assert t["frequency"] == pytest.approx(t["participant_count"] / 8, abs=1e-4)
        supporting = [e for e in t["evidence"] if e["stance"] == "supporting"]
        assert supporting, t["name"]
        for e in supporting:
            # Every piece of evidence links back to a real interview and participant.
            assert ids_by_interview[e["interview_id"]] == e["participant_id"]
            assert e["participant_id"] in t["participant_ids"]
            if e["quote"]:
                assert e["quote_verified"]
        assert t["status"] == "proposed" and t["origin"] == "ai"

    project_after = client.get(f"/api/projects/{pid}").json()
    assert project_after["synthesis_status"] == "completed"
    assert project_after["status"] == "in_review"
    assert project_after["theme_count"] == len(themes)

    insights = client.get(f"/api/projects/{pid}/insights").json()
    assert len(insights) == len(themes)
    assert all(1 <= i["severity"] <= 5 and 1 <= i["strategic_relevance"] <= 5 for i in insights)


def test_quotes_are_exact_substrings_of_the_original_notes(client, project):
    pid = project["id"]
    interviews = {i["id"]: i for i in _import(client, pid, "interviews-consistent.md")}
    _synthesise(client, pid)
    norm = lambda s: " ".join(s.lower().split())  # noqa: E731
    for t in _themes(client, pid):
        for e in t["evidence"]:
            if e["quote_verified"]:
                assert norm(e["quote"]) in norm(interviews[e["interview_id"]]["raw_content"])


# --- Tests 3, 4, 5, 7: edge cases ---------------------------------------------------


@pytest.fixture
def edge_themes(client, project):
    pid = project["id"]
    _import(client, pid, "interviews-consistent.md", "interviews-edge-cases.md")
    run = _synthesise(client, pid)
    assert run["status"] == "completed", run["error"]
    return run, _themes(client, pid)


def test_contradictory_evidence_is_surfaced(edge_themes):
    _, themes = edge_themes
    contra = [(t, e) for t in themes for e in t["evidence"] if e["stance"] == "contradicting"]
    assert contra, "expected P09's positive setup experience to contradict a theme"
    theme, ev = next((t, e) for t, e in contra if e["participant_id"] == "P09")
    assert theme["has_contradictions"]
    assert "easy" in ev["quote"].lower() and ev["quote_verified"]
    # Both sides are visible on the same theme.
    assert any(e["stance"] == "supporting" for e in theme["evidence"])
    assert "P09" not in theme["participant_ids"]


def test_single_participant_high_impact_finding_is_kept_as_outlier(edge_themes):
    run, themes = edge_themes
    soc2 = next(t for t in themes if "P10" in t["participant_ids"])
    assert soc2["participant_ids"] == ["P10"]
    assert soc2["is_outlier"] is True
    assert soc2["severity"] >= 4
    assert soc2["status"] == "proposed"  # not discarded
    assert any(w["code"] == "outliers" for w in run["warnings"])


def test_duplicate_mentions_count_participant_once(edge_themes):
    run, themes = edge_themes
    assert run["stats"]["participants"] == 11  # 12 interviews, P05 twice
    assert run["stats"]["duplicates_merged"] >= 1
    for t in themes:
        assert len(t["participant_ids"]) == len({p.lower() for p in t["participant_ids"]})
        assert t["participant_count"] == len(t["participant_ids"])
        assert t["total_participants"] == 11
    perf = next(t for t in themes if "P05" in t["participant_ids"] and "P07" in t["participant_ids"])
    assert perf["participant_ids"].count("P05") == 1


def test_sensitive_business_themes_require_approval(edge_themes):
    _, themes = edge_themes
    churn = next(t for t in themes if "P12" in t["participant_ids"])
    assert {"churn", "competitive_switching"} <= set(churn["sensitive_tags"])
    assert churn["requires_approval"] is True
    pricing = [t for t in themes if "pricing" in t["sensitive_tags"]]
    assert pricing and all(t["requires_approval"] for t in pricing)
    non_sensitive = [t for t in themes if not t["sensitive_tags"]]
    assert non_sensitive and not any(t["requires_approval"] for t in non_sensitive)


# --- Fallback A: fewer than five interviews ----------------------------------------


def test_small_sample_refused_unless_forced(client, project):
    pid = project["id"]
    text = (SAMPLES / "interviews-consistent.md").read_text(encoding="utf-8").split("\n---\n")
    _import_text = "\n---\n".join(text[1:4])  # three interviews
    preview = client.post(f"/api/projects/{pid}/import/preview", json={"text": _import_text}).json()
    client.post(
        f"/api/projects/{pid}/import",
        json={"items": [{"fields": i["fields"], "raw_content": i["raw_content"]} for i in preview["items"]]},
    )
    refused = client.post(f"/api/projects/{pid}/synthesis", json={})
    assert refused.status_code == 422
    assert "at least 5" in refused.json()["detail"]
    assert client.get(f"/api/projects/{pid}/synthesis/runs").json() == []

    run = _synthesise(client, pid, force=True)
    assert run["status"] == "completed"
    assert any(w["code"] == "insufficient_sample" for w in run["warnings"])


def test_no_valid_interviews_refused(client, project):
    client.post(f"/api/projects/{project['id']}/interviews", json={"participant_id": "P1"})
    resp = client.post(f"/api/projects/{project['id']}/synthesis", json={"force": True})
    assert resp.status_code == 422


# --- Test 6: provider failure -------------------------------------------------------


class _FailingEngine(DemoEngine):
    name, model = "failing", "broken-model"

    def __init__(self, fail_at: str):
        self.fail_at = fail_at

    def name_theme(self, pain_points):
        if self.fail_at == "clustering":
            raise LLMError("provider timed out after 3 attempts")
        return super().name_theme(pain_points)

    def draft_insight(self, *a, **kw):
        if self.fail_at == "insights":
            raise LLMError("provider returned malformed JSON 3 times")
        return super().draft_insight(*a, **kw)


@pytest.fixture
def failing_ai():
    def use(stage):
        app.dependency_overrides[get_ai] = lambda: AI(engine=_FailingEngine(stage), embedder=HashEmbedder())

    yield use
    app.dependency_overrides.pop(get_ai, None)


def test_provider_failure_keeps_previous_results_intact(client, project, failing_ai):
    pid = project["id"]
    _import(client, pid, "interviews-consistent.md")
    good = _synthesise(client, pid)
    before = _themes(client, pid)
    assert good["status"] == "completed" and before

    failing_ai("insights")  # fails late, after themes were computed in memory
    failed = _synthesise(client, pid)
    assert failed["status"] == "failed"
    assert "malformed JSON" in failed["error"]
    assert failed["is_active"] is False

    project_after = client.get(f"/api/projects/{pid}").json()
    assert project_after["synthesis_status"] == "failed"
    after = _themes(client, pid)
    assert [t["id"] for t in after] == [t["id"] for t in before]  # previous synthesis still live
    assert all(t["run_id"] == good["id"] for t in after)


def test_failed_first_run_writes_nothing(client, project, failing_ai):
    from sqlalchemy import func, select

    from app.core.db import SessionLocal
    from app.models import Insight, PainPoint, Theme

    pid = project["id"]
    _import(client, pid, "interviews-consistent.md")
    failing_ai("clustering")
    run = _synthesise(client, pid)
    assert run["status"] == "failed"
    with SessionLocal() as s:
        for model in (PainPoint, Theme, Insight):
            assert s.scalar(select(func.count()).select_from(model)) == 0
    assert _themes(client, pid) == []


def test_concurrent_run_rejected(client, project):
    from app.core.db import SessionLocal
    from app.models import SynthesisRun

    pid = project["id"]
    _import(client, pid, "interviews-consistent.md")
    with SessionLocal() as s:
        s.add(SynthesisRun(project_id=pid, status="running", provider="demo", model="m", embedding_provider="h"))
        s.commit()
    assert client.post(f"/api/projects/{pid}/synthesis", json={}).status_code == 409


def test_rerun_replaces_live_themes(client, project):
    pid = project["id"]
    _import(client, pid, "interviews-consistent.md")
    first = _synthesise(client, pid)
    second = _synthesise(client, pid)
    themes = _themes(client, pid)
    assert all(t["run_id"] == second["id"] for t in themes)
    assert first["id"] != second["id"]
    assert client.get(f"/api/projects/{pid}").json()["theme_count"] == len(themes)
