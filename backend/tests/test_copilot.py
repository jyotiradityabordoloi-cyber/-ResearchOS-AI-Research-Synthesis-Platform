"""Phase 5: research copilot. Grounded answers, checked citations, honest demo/fallback modes."""

import json

import pytest

from app.ai.engine import LLMEngine
from app.ai.providers import LLMProvider, TransientLLMError
from app.api.routes.copilot import get_copilot_engine
from app.main import app
from tests.test_acceptance import CONSISTENT, import_text, new_project, synthesise


class ScriptedProvider(LLMProvider):
    """A real LLMProvider (same JSON parsing and validation) with a scripted reply."""

    name, model = "scripted", "test-model"

    def __init__(self, reply=None, fail=False):
        super().__init__(max_retries=1, backoff_seconds=0)
        self.reply, self.fail, self.prompts = reply, fail, []

    def _chat(self, messages, json_schema):
        self.prompts.append(messages[-1]["content"])
        if self.fail:
            raise TransientLLMError("model overloaded")
        return json.dumps(self.reply)


@pytest.fixture
def project(client):
    pid = new_project(client)
    import_text(client, pid, CONSISTENT)
    synthesise(client, pid)
    return pid


@pytest.fixture
def use_provider():
    def install(provider):
        app.dependency_overrides[get_copilot_engine] = lambda: (LLMEngine(provider), None)
        return provider

    yield install
    app.dependency_overrides.pop(get_copilot_engine, None)


def ask(client, pid, question, **kw):
    r = client.post(f"/api/projects/{pid}/copilot", json={"question": question, **kw})
    assert r.status_code == 200, r.text
    return r.json()


SUGGESTED = [
    "Why is this theme important?",
    "Show contradictory evidence.",
    "What do enterprise users think?",
    "Compare two themes.",
    "Identify missing research coverage.",
    "Summarize the strongest evidence.",
]


@pytest.mark.parametrize("question", SUGGESTED)
def test_demo_mode_answers_suggested_questions_from_data(client, project, question):
    theme = client.get(f"/api/projects/{project}/themes").json()[0]
    out = ask(client, project, question, theme_id=theme["id"])
    assert out["mode"] == "demo" and out["notice"] and "rules" in out["notice"]
    assert out["answer"].strip()
    assert out["theme_code"] == theme["code"]
    # Every citation resolves to real data; every quote cited exists verbatim in its interview.
    for c in out["citations"]:
        assert f"[{c['key']}]" in out["answer"]
        if c["kind"] == "evidence":
            raw = client.get(f"/api/interviews/{c['interview_id']}").json()["raw_content"].lower()
            assert c["quote"].lower() in raw or not c["quote"]


def test_demo_importance_uses_real_numbers(client, project):
    theme = client.get(f"/api/projects/{project}/themes").json()[0]
    out = ask(client, project, "Why is this theme important?", theme_id=theme["id"])
    assert f"{theme['participant_count']} of {theme['total_participants']} participants" in out["answer"]
    assert any(c["kind"] == "theme" and c["theme_id"] == theme["id"] for c in out["citations"])


def test_ai_answer_keeps_only_real_citations(client, project, use_provider):
    provider = use_provider(
        ScriptedProvider({"answer": "Slow dashboards matter [T1] and [E1]; one quote is made up [E999] [T42].", "citations": ["T1", "E1", "X9"]})
    )
    out = ask(client, project, "Why does this matter?")
    assert out["mode"] == "ai" and out["provider"] == "scripted" and out["notice"] is None
    assert "[E999]" not in out["answer"] and "[T42]" not in out["answer"]
    assert [c["key"] for c in out["citations"]] == ["T1", "E1"]
    # The model saw the grounded context, including real participant counts.
    prompt = provider.prompts[0]
    assert "THEMES (frequency" in prompt and "QUOTES" in prompt and "QUESTION: Why does this matter?" in prompt


def test_ranges_and_lists_are_normalised(client, project, use_provider):
    theme = client.get(f"/api/projects/{project}/themes").json()[0]
    provider = use_provider(
        ScriptedProvider({"answer": "Everything matters [T1-T9, I1-I9]. Two quotes agree [E1, E2]. See (I am a note).", "citations": []})
    )
    out = ask(client, project, "Why is this theme important?", theme_id=theme["id"])
    assert "[T1-T9" not in out["answer"] and "[E1] [E2]" in out["answer"]
    assert [c["key"] for c in out["citations"]] == ["E1", "E2"]
    assert f"FOCUS: the user is looking at theme [{theme['code']}]" in provider.prompts[0]


def test_history_and_interview_context_reach_the_model(client, project, use_provider):
    provider = use_provider(ScriptedProvider({"answer": "They struggled with setup [P].", "citations": ["P"]}))
    iv = client.get("/api/interviews", params={"project_id": project}).json()[0]
    out = ask(
        client, project, "And this participant?", interview_id=iv["id"],
        history=[{"role": "user", "content": "What blocks trials?"}, {"role": "assistant", "content": "Setup [T1]."}],
    )
    assert out["interview_participant"] == iv["participant_id"]
    assert out["citations"][0]["kind"] == "interview" and out["citations"][0]["interview_id"] == iv["id"]
    assert "EARLIER IN THIS CONVERSATION" in provider.prompts[0] and iv["pain"][:30] in provider.prompts[0]


def test_provider_failure_falls_back_and_says_so(client, project, use_provider):
    use_provider(ScriptedProvider(fail=True))
    out = ask(client, project, "Show contradictory evidence.")
    assert out["mode"] == "fallback" and "did not answer" in out["notice"]
    assert out["answer"].strip()


def test_project_without_themes(client):
    pid = new_project(client)
    out = ask(client, pid, "What do users think?")
    assert "no synthesised themes" in out["answer"] and out["citations"] == []


def test_foreign_ids_are_ignored(client, project):
    other = new_project(client, "Other")
    import_text(client, other, CONSISTENT)
    synthesise(client, other)
    foreign = client.get(f"/api/projects/{other}/themes").json()[0]
    out = ask(client, project, "Why is this theme important?", theme_id=foreign["id"])
    assert out["theme_code"] is None
    mine = {t["id"] for t in client.get(f"/api/projects/{project}/themes").json()}
    assert all(c["theme_id"] in mine for c in out["citations"] if c["theme_id"])
