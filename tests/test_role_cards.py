"""Role cards persist and reach the real planning/execution paths without paid calls."""
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from agent_system.core.director import Director
from agent_system.core.memory import SharedMemory
from agent_system.core.settings_manager import settings_manager
from agent_system.core.role_cards import RoleCard, card_for
from agent_system.core import projects


def config(model="custom-model", card=None):
    result = {"provider": "groq", "model": model, "temperature": 0.2, "max_tokens": 2048}
    if card is not None:
        result["role_card"] = card
    return result


CARD = {"specialization": "إصلاح أخطاء Python", "when_to_use": "عند طلب إصلاح شيفرة Python",
        "instructions": "INSTRUCTION_MARKER: قدم أقل تعديل ممكن، ولا تدع تشغيل الاختبارات.",
        "expected_input": "رسالة الخطأ والشيفرة", "expected_output": "التعديل المقترح وطريقة التحقق"}


class Model:
    provider = "groq"
    last_result = {}

    def __init__(self, name, replies):
        self.model_name, self.replies, self.seen = name, list(replies), []

    def get_model_name(self):
        return self.model_name

    def complete(self, *args, **kwargs):
        self.seen.append(kwargs or dict(zip(("system_prompt", "user_message", "temperature", "max_tokens"), args)))
        self.last_result = {"status_code": 200, "finish_reason": "stop"}
        value = self.replies.pop(0)
        return json.dumps(value, ensure_ascii=False) if isinstance(value, dict) else value


def test_legacy_cards_are_read_only_defaults_and_models_do_not_change(client, headers, database):
    raw = database.get_document("settings")
    settings = client.get("/api/settings", headers=headers).json()
    assert settings["workers"]["fast"]["role_card"]["specialization"]
    assert settings["director"]["model"] == raw["director"]["model"]
    assert database.get_document("settings") == raw


def test_add_update_and_reload_card_preserve_model_choices(client, headers, database):
    response = client.post("/api/settings/workers", headers=headers,
                           json={"name": "programmer", **config(card=CARD)})
    assert response.status_code == 200
    env = {**os.environ, "DATABASE_PATH": database.path}
    result = subprocess.run([sys.executable, "-c", "import json; from agent_system.core.settings_manager import settings_manager; print(json.dumps(settings_manager.get_settings()['workers']['programmer']))"],
                            env=env, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)["role_card"] == CARD
    # An old client changing only the model must not erase the saved card.
    assert client.put("/api/settings/workers/programmer", headers=headers, json=config("new-engine")).status_code == 200
    saved = client.get("/api/settings", headers=headers).json()["workers"]["programmer"]
    assert saved["model"] == "new-engine" and saved["role_card"] == CARD
    policy = client.get("/api/settings", headers=headers).json()["execution"]
    policy["single_role"] = "programmer"
    assert client.put("/api/settings/execution", headers=headers, json=policy).status_code == 200
    empty = RoleCard().model_dump()
    assert client.put("/api/settings/workers/programmer", headers=headers, json=config("new-engine", empty)).status_code == 200
    assert card_for(settings_manager.get_settings()["workers"]["programmer"], "programmer") == empty


@pytest.mark.parametrize("bad_card", [{"instructions": "x" * 2001}, {"specialization": ["bad"]}, {"tools": ["shell"]}])
def test_invalid_cards_are_rejected_without_saved_changes(client, headers, database, bad_card):
    before = database.get_document("settings")
    response = client.put("/api/settings/director", headers=headers, json=config(card=bad_card))
    assert response.status_code == 422
    assert database.get_document("settings") == before


@pytest.mark.parametrize("name", ["director", "wrong/name", "", "X" * 65])
def test_role_ids_cannot_shadow_director_or_break_routes(client, headers, name):
    assert client.post("/api/settings/workers", headers=headers, json={"name": name, **config(card=CARD)}).status_code == 400


def test_card_and_authorization_cannot_be_changed_anonymously(client):
    assert client.put("/api/settings/director", json=config(card=CARD)).status_code in (401, 403)


def test_project_model_override_keeps_director_card(database):
    assert settings_manager.update_director(config(card=CARD), "admin")
    choice = {**config("project-engine"), "provider": "openrouter"}
    effective = projects.model_settings("owner", {"director": choice})
    assert effective["director"]["model"] == "project-engine"
    assert effective["director"]["role_card"] == CARD


def test_team_selects_custom_roles_and_passes_cards_to_dependent_work(database, monkeypatch):
    assert settings_manager.add_worker("programmer", config("code-engine", CARD), "admin")
    reviewer_card = {**CARD, "specialization": "مراجعة التعديل", "instructions": "REVIEW_MARKER: راجع نتيجة المطور فقط"}
    assert settings_manager.add_worker("reviewer", config("review-engine", reviewer_card), "admin")
    settings = settings_manager.get_settings()
    settings["execution"]["critic_role"] = "reviewer"
    plan = {"sub_questions": [{"id": 1, "question": "أصلح الخطأ"}, {"id": 2, "question": "راجع التصحيح"}],
            "agents": [{"name": "Coder", "worker_type": "programmer", "sub_question_id": 1},
                       {"name": "Reviewer", "worker_type": "reviewer", "sub_question_id": 2, "depends_on": [1]}]}
    router = Model("route", [{"route": "team"}])
    director = Model("director", [plan, "النتيجة النهائية"])
    coder = Model("code-engine", ["تصحيح مقترح. CONFIDENCE: 80%\n===PHEROMONE===\nDISCOVERY: FIX_HANDOFF\n===END==="])
    reviewer = Model("review-engine", ["مراجعة. CONFIDENCE: 80%", {"severity": 0, "flaws": []}])
    d = Director(settings_override=settings)
    monkeypatch.setattr(d, "_director_connector", lambda: director)
    monkeypatch.setattr(d, "_role_connector", lambda role: router if role == "fast" else reviewer)
    monkeypatch.setattr(d, "_connector_for", lambda c: coder if c["model"] == "code-engine" else reviewer)
    m = SharedMemory("أصلح الشيفرة وراجعها")
    d.run(m.task_original, m)
    assert m.status == "complete", m.warnings
    assert m.execution["model_calls"] == 6  # cards add no model calls
    planning = director.seen[0]["system_prompt"]
    assert CARD["specialization"] in planning and CARD["when_to_use"] in planning
    assert "INSTRUCTION_MARKER" not in planning
    assert "INSTRUCTION_MARKER" in coder.seen[0]["system_prompt"]
    assert CARD["expected_output"] in coder.seen[0]["system_prompt"]
    assert "FIX_HANDOFF" in reviewer.seen[0]["system_prompt"]
    assert "REVIEW_MARKER" in reviewer.seen[-1]["system_prompt"]
    assert "valid JSON" in reviewer.seen[-1]["system_prompt"]


def test_research_path_receives_its_selected_role_card(database, monkeypatch):
    from agent_system.core import worker
    model = Model("research-engine", ["نتيجة. CONFIDENCE: 70%"])
    d = Director()
    monkeypatch.setattr(d, "_connector_for", lambda c: model)
    settings = settings_manager.get_settings()
    settings["workers"]["researcher"] = config("research-engine", CARD)
    d.settings_override = settings
    m = SharedMemory("ابحث")
    m.run_settings = settings
    plan = {"sub_questions": [{"id": 1, "question": "بحث محدد"}],
            "agents": [{"worker_type": "researcher", "needs_web": True, "sub_question_id": 1}]}
    monkeypatch.setattr(worker, "get_search", lambda: SimpleNamespace(search=lambda *a, **kw: [
        {"title": "Source", "snippet": "Evidence", "domain": "example.org", "url": "https://example.org"}]))
    d._build_workers(plan, m)[0].execute()
    assert "INSTRUCTION_MARKER" in model.seen[0]["system_prompt"]
    assert "using ONLY the evidence" in model.seen[0]["system_prompt"]


def test_simple_question_still_uses_one_call_and_custom_fast_card(database, monkeypatch):
    settings = settings_manager.get_settings()
    settings["workers"]["fast"]["role_card"] = CARD
    model = Model("route", [{"route": "direct", "answer": "باريس."}])
    d = Director(settings_override=settings)
    monkeypatch.setattr(d, "_role_connector", lambda role: model)
    monkeypatch.setattr(d, "analyze_task", lambda *a: pytest.fail("must not schedule cards for every question"))
    m = SharedMemory("ما عاصمة فرنسا؟")
    d.run(m.task_original, m)
    assert m.final_synthesis == "باريس." and m.execution["model_calls"] == 1
    assert "INSTRUCTION_MARKER" in model.seen[0]["system_prompt"]
