"""Offline regression tests: orchestration, budgets, provider failures and persistence.

Scripted model responses test the execution contract, not a live model's accuracy/latency.
"""
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import pytest

from agent_system.core.director import Director
from agent_system.core.memory import SharedMemory
from agent_system.core.settings_manager import settings_manager
from agent_system.core.execution_runtime import ExecutionRuntime, ExecutionLimit, ProviderGate
from agent_system.core import execution_runtime, projects
from agent_system.core.orchestrator import Orchestrator


class Model:
    def __init__(self, replies, provider="groq", model="test", usage=True, status=200, finish="stop"):
        self.replies = list(replies)
        self.provider, self.model_name = provider, model
        self.usage, self.status, self.finish = usage, status, finish
        self.seen, self.last_result = [], {}

    def complete(self, **kwargs):
        self.seen.append(kwargs)
        self.last_result = {"status_code": self.status, "retry_after": 60, "finish_reason": self.finish}
        if self.usage:
            self.last_result["usage"] = {"prompt_tokens": 30, "completion_tokens": 10, "total_tokens": 40}
        reply = self.replies.pop(0)
        return json.dumps(reply, ensure_ascii=False) if isinstance(reply, dict) else reply

    def get_model_name(self):
        return self.model_name


@pytest.fixture(autouse=True)
def reset_gate(monkeypatch):
    monkeypatch.setattr(execution_runtime, "PROVIDER_GATE", ProviderGate())


def runner(monkeypatch, router, answer=None):
    d = Director()
    monkeypatch.setattr(d, "_role_connector", lambda role: router if role == "fast" else answer)
    return d


@pytest.mark.parametrize("question,answer", [("ما هي عاصمة فرنسا؟", "باريس."), ("شكرا", "على الرحب والسعة.")])
def test_direct_contract_is_one_call_without_planner_or_workers(database, monkeypatch, question, answer):
    model = Model([{"route": "direct", "answer": answer}])
    d = runner(monkeypatch, model)
    monkeypatch.setattr(d, "analyze_task", lambda *a: pytest.fail("unexpected planner"))
    monkeypatch.setattr(d, "_critic", lambda *a: pytest.fail("unexpected review"))
    m = SharedMemory(question)
    d.run(question, m)
    assert m.status == "complete" and m.final_synthesis == answer
    assert m.execution["model_calls"] == 1 and m.execution["reported_tokens"] == 40
    assert m.execution["usage_complete"] and not m.findings
    assert database.get_session(m.session_id)["execution"]["model_calls"] == 1
    assert model.seen[0]["max_tokens"] == 1024


def test_substantial_answer_is_two_calls_and_can_use_another_provider(database, monkeypatch):
    router = Model([{"route": "single", "detail": "detailed"}])
    answer = Model(["شرح مفصل"], provider="openrouter")
    d = runner(monkeypatch, router, answer)
    m = SharedMemory("اشرح بالتفصيل")
    d.run(m.task_original, m)
    assert m.final_synthesis == "شرح مفصل" and m.execution["model_calls"] == 2
    assert {r["provider"] for r in m.execution["calls"]} == {"groq", "openrouter"}
    assert "selected detailed" in answer.seen[0]["system_prompt"]


@pytest.mark.parametrize("reply,finish", [("not JSON", "stop"), ({"route": "direct", "answer": "partial"}, "length")])
def test_invalid_or_truncated_routing_uses_one_bounded_recovery(database, monkeypatch, reply, finish):
    d = runner(monkeypatch, Model([reply], finish=finish), Model(["إجابة مكتملة"]))
    m = SharedMemory("سؤال")
    d.run(m.task_original, m)
    assert m.execution["route"] == "single" and m.execution["model_calls"] == 2
    assert m.final_synthesis == "إجابة مكتملة"


def test_research_skips_general_planning_and_keeps_evidence(database, monkeypatch):
    from agent_system.core import worker
    router = Model([{"route": "research"}])
    researcher = Model(["Evidence [1](https://example.org/source). CONFIDENCE: 70%"])
    synthesis = Model(["النتيجة [1](https://example.org/source)"])
    d = runner(monkeypatch, router)
    monkeypatch.setattr(d, "_connector_for", lambda *a: researcher)
    monkeypatch.setattr(d, "_director_connector", lambda: synthesis)
    monkeypatch.setattr(d, "analyze_task", lambda *a: pytest.fail("research should not plan a team"))
    seen = []
    def search(*args, **kwargs):
        seen.append(args)
        return [{"title": "Source", "snippet": "Evidence", "domain": "example.org", "url": "https://example.org/source"}]
    monkeypatch.setattr(worker, "get_search", lambda: SimpleNamespace(search=search))
    m = SharedMemory("ابحث عن معلومة حديثة")
    d.run(m.task_original, m)
    assert m.status == "complete" and seen
    assert m.execution["model_calls"] == 3 and len(m.findings) == 1
    assert "https://example.org/source" in researcher.seen[0]["system_prompt"]


def test_missing_material_plan_never_starts_workers(database, monkeypatch):
    d = runner(monkeypatch, Model([{"route": "team"}]))
    monkeypatch.setattr(d, "analyze_task", lambda *a: {"missing_input": True, "missing_description": "أرفق الملف."})
    monkeypatch.setattr(d, "_build_workers", lambda *a: pytest.fail("must not invent missing material"))
    m = SharedMemory("راجع الملف")
    d.run(m.task_original, m)
    assert m.execution["route"] == "clarify" and m.final_synthesis == "أرفق الملف."


def test_compact_context_avoids_duplicate_current_message_and_labels_omissions(database):
    m = SharedMemory("current")
    m.chat_history = [{"role": "user", "content": "older" * 2000},
                      {"role": "user", "content": "current", "session_id": m.session_id}]
    m.project_context = "project" * 2000
    text = m.conversation_context(compact=True)
    assert "current" not in text and "incomplete" in text and len(text) < 7200
    assert len(m.chat_history[0]["content"]) == 10000


def test_fallback_requires_explicit_role_and_transient_status(database):
    settings = settings_manager.get_settings()
    primary = Model(["Error: offline"], status=503)
    runtime = ExecutionRuntime(SharedMemory("test"), settings)
    assert runtime.call(primary, "route", "s", "u", 0, 64).startswith("Error:")
    assert runtime.summary()["model_calls"] == 1
    backup = Model(["ok"], provider="openrouter")
    runtime = ExecutionRuntime(SharedMemory("test"), settings, lambda: backup)
    assert runtime.call(Model(["Error: offline"], status=503), "answer", "s", "u", 0, 64) == "ok"
    assert runtime.summary()["calls"][-1]["fallback"]
    forbidden = Model(["Error: unauthorized"], status=401)
    assert runtime.call(forbidden, "answer", "s", "u", 0, 64).startswith("Error:")
    assert len(backup.seen) == 1


def test_retry_after_is_shared_and_does_not_rotate_keys(database):
    runtime = ExecutionRuntime(SharedMemory("test"), settings_manager.get_settings())
    model = Model(["Error: quota"], status=429)
    runtime.call(model, "route", "s", "u", 0, 64)
    assert runtime.call(Model(["must not call"]), "route", "s", "u", 0, 64).startswith("Error:")
    assert runtime.summary()["model_calls"] == 1
    assert execution_runtime.PROVIDER_GATE.cooldown[("groq", "test")] > time.monotonic() + 50


def test_call_budget_and_expired_deadline_prevent_paid_attempts(database):
    settings = settings_manager.get_settings()
    settings["execution"]["max_model_calls"] = 4
    runtime = ExecutionRuntime(SharedMemory("test"), settings)
    model = Model(["ok"] * 6)
    for _ in range(4):
        runtime.call(model, "answer", "s", "u", 0, 64)
    with pytest.raises(ExecutionLimit):
        runtime.call(model, "answer", "s", "u", 0, 64)
    assert len(model.seen) == 4
    runtime = ExecutionRuntime(SharedMemory("test"), settings)
    runtime.deadline = 0
    with pytest.raises(ExecutionLimit):
        runtime.call(model, "answer", "s", "u", 0, 64)
    assert len(model.seen) == 4


def test_unknown_usage_is_never_reported_as_complete_zero(database):
    runtime = ExecutionRuntime(SharedMemory("test"), settings_manager.get_settings())
    runtime.call(Model(["ok"], usage=False), "answer", "s", "u", 0, 64)
    summary = runtime.summary()
    assert summary["reported_tokens"] == 0 and summary["usage_complete"] is False
    assert summary["calls"][0]["total_tokens"] is None


def test_provider_gate_applies_across_simultaneous_turns(database):
    settings = settings_manager.get_settings()
    settings["execution"]["provider_concurrency"] = 1
    lock = threading.Lock()
    active, peak = 0, 0
    class SlowModel(Model):
        def complete(self, **kwargs):
            nonlocal active, peak
            with lock:
                active += 1; peak = max(peak, active)
            time.sleep(0.015)
            with lock:
                active -= 1
            return super().complete(**kwargs)
    def call(_):
        return ExecutionRuntime(SharedMemory("test"), settings).call(SlowModel(["ok"]), "answer", "s", "u", 0, 64)
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(call, range(4))) == ["ok"] * 4
    assert peak == 1


def test_dependency_failure_blocks_only_dependent_work(database):
    memory = SharedMemory("project")
    ran = []
    class Worker:
        def __init__(self, id, deps, fail=False):
            self.task_id, self.depends_on, self.fail = id, deps, fail
            self.name = self.sub_question = str(id)
        def execute(self):
            ran.append(self.task_id)
            memory.add_finding(self.name, self.sub_question, "result", 80, status="failed" if self.fail else "complete")
    Orchestrator().run_dependencies([Worker(1, [], True), Worker(2, [1]), Worker(3, [])], memory)
    assert set(ran) == {1, 3}
    assert next(f for f in memory.findings if f["agent_name"] == "2")["status"] == "failed"
    with pytest.raises(ValueError, match="دائرية"):
        Orchestrator().run_dependencies([Worker(1, [2]), Worker(2, [1])], memory)


def test_api_saves_detail_and_direct_project_chat_does_not_generate_board(client, headers, database, monkeypatch):
    monkeypatch.setattr(Director, "choose_strategy", lambda *a: {"route": "direct", "answer": "باريس.", "project_relevant": True})
    monkeypatch.setattr(projects, "request_proposal", lambda *a, **k: pytest.fail("no board call for a simple question"))
    project = client.post("/api/projects", headers=headers, json={"name": "test"}).json()
    result = client.post("/api/task", headers=headers, json={"task": "عاصمة فرنسا؟", "project_id": project["id"], "response_detail": "brief"})
    assert result.status_code == 200
    saved = database.get_session(result.json()["session_id"])
    assert saved["response_detail"] == "brief" and saved["status"] == "complete"
    assert client.post("/api/task", headers=headers, json={"task": "x", "response_detail": "wrong"}).status_code == 422


def test_policy_settings_validate_roles_persist_and_preserve_overrides(client, headers, database):
    settings = client.get("/api/settings", headers=headers).json()
    policy = settings["execution"]
    policy["research_role"] = "creative"
    policy["provider_concurrency"] = 1
    assert client.put("/api/settings/execution", headers=headers, json=policy).status_code == 200
    assert database.get_document("settings")["execution"]["research_role"] == "creative"
    policy["research_role"] = "missing"
    assert client.put("/api/settings/execution", headers=headers, json=policy).status_code == 400
    policy["max_model_calls"] = 0
    assert client.put("/api/settings/execution", headers=headers, json=policy).status_code == 422
    choice = {"provider": "openrouter", "model": "user/model", "temperature": 0.2, "max_tokens": 2048}
    database.set_document("preferences:owner", {"director": choice})
    effective = projects.model_settings("owner")
    assert effective["execution"]["router_role"] == "director" and effective["director"] == choice
