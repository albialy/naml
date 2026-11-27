import json
import pytest
from agent_system.core.auth.manager import auth_manager
from agent_system.core.auth.models import UserRole
from agent_system.core.memory import SharedMemory
from agent_system.core.director import Director
from agent_system.core.orchestrator import Orchestrator

@pytest.fixture
def customer(client):
    admin = auth_manager.get_user_by_username("admin")
    user = auth_manager.create_user("customer", "password123", UserRole.USER, admin.id)
    return auth_manager.get_user_by_username("customer"), {"Authorization": "Bearer " + auth_manager.login("customer", "password123").token}

def seed(database, owner):
    memory = SharedMemory("اختبار", user_id=owner.id)
    saved = database.start_turn(memory.to_dict())
    saved.update(status="complete", final_synthesis="نتيجة مفيدة",
                 run_settings={"model": "PRIVATE_ENGINE"}, findings=[{"response": "PRIVATE_FINDING"}],
                 execution={"route": "team", "calls": [{"model": "PRIVATE_ENGINE"}], "suggest_simulation": True},
                 coordination={"events": [{"task_id": "PRIVATE_TASK"}]})
    database.save_session(saved)
    return saved

def assert_public(response):
    assert response.status_code == 200, response.text
    text = response.text
    for marker in ("PRIVATE_", "run_settings", "coordination", "agents_plan", '"execution"', '"findings"'):
        assert marker not in text
    return response.json()

def test_all_customer_session_and_conversation_reads_project_safe_contract(client, customer, headers, database):
    owner, h = customer
    saved = seed(database, owner)
    for path in ("/api/sessions/", "/api/task/"):
        suffix = "" if path.endswith("sessions/") else "/status"
        data = assert_public(client.get(path + saved["session_id"] + suffix, headers=h))
        assert data["final_synthesis"] == "نتيجة مفيدة"
        assert data["simulation_suggested"] is True
    assert_public(client.get("/api/task/" + saved["session_id"] + "/result", headers=h))
    cid = saved["conversation_id"]
    conv = assert_public(client.get("/api/conversations/" + cid, headers=h))
    assert conv["messages"][-1]["simulation_suggested"] is True
    assert_public(client.post("/api/conversations/" + cid + "/branch", headers=h,
                 json={"branch_id": conv["branch_id"], "revision": conv["revision"]}))
    assert "PRIVATE_ENGINE" in client.get("/api/sessions/" + saved["session_id"], headers=headers).text
    assert client.get("/api/sessions/" + saved["session_id"], headers=headers).json()["simulation_suggested"] is True
    assert client.get("/api/conversations/" + cid, headers=headers).json()["messages"][-1]["simulation_suggested"] is True

def test_customer_keeps_material_limitations_without_diagnostic_details(client, customer, database):
    owner, h = customer
    saved = seed(database, owner)
    limitation = "التحليل جزئي: تعذر إكمال بعض الجوانب؛ لا تعتبرها نتائج مؤكدة."
    saved["warnings"] = [limitation, "PRIVATE_PROVIDER diagnostic"]
    database.save_session(saved)
    data = assert_public(client.get("/api/sessions/" + saved["session_id"], headers=h))
    assert limitation in data["warnings"]
    assert len(data["warnings"]) == 2

def test_failed_response_and_stop_do_not_leak_internal_errors(client, customer, database):
    owner, h = customer
    saved = seed(database, owner)
    saved.update(status="failed", final_synthesis="PRIVATE_PROVIDER exception")
    database.save_session(saved)
    assert_public(client.get("/api/task/" + saved["session_id"] + "/result", headers=h))
    second = SharedMemory("انتظار", user_id=owner.id)
    pending = database.start_turn(second.to_dict(), saved["conversation_id"])
    conv = database.get_conversation(saved["conversation_id"])
    assert_public(client.post("/api/conversations/" + saved["conversation_id"] + "/stop", headers=h,
                 json={"session_id": pending["session_id"], "branch_id": conv["branch_id"], "revision": conv["revision"]}))

def test_model_controls_require_admin_and_project_returns_no_configuration(client, customer):
    owner, h = customer
    assert client.get("/api/preferences", headers=h).status_code == 403
    assert client.put("/api/preferences", headers=h, json={"director": None}).status_code == 403
    p = client.post("/api/projects", headers=h, json={"name": "تجربة"}).json()
    assert "director" not in p
    denied = client.patch("/api/projects/" + p["id"], headers=h, json={"revision": p["revision"], "director": None})
    assert denied.status_code == 403
    assert "allowed_models" not in client.get("/api/auth/me", headers=h).json()
    assert client.get("/api/settings", headers=h).status_code == 403

def test_simulation_requires_login_and_review_and_never_launches_on_save(client, customer, database):
    _, h = customer
    assert client.get("/api/simulation/scenarios").status_code in (401, 403)
    spec = client.get("/api/simulation/templates/workflow", headers=h).json()
    saved = client.post("/api/simulation/scenarios", headers=h, json={"spec": spec})
    assert saved.status_code == 201
    assert database.get_document("simulation:queue", []) == []
    assert client.post("/api/simulation/runs", headers=h, json={"scenario_id": saved.json()["id"], "reviewed": False, "request_key": "request-one"}).status_code == 422

def test_router_suggestion_does_not_run_simulation(database, monkeypatch):
    d = Director()
    monkeypatch.setattr(d, "choose_strategy", lambda *a: {"route": "direct", "answer": "يمكن اختبار أثر زيادة الموارد", "suggest_simulation": True})
    m = SharedMemory("ماذا لو زدنا الموارد")
    d.run(m.task_original, m)
    assert m.status == "complete" and m.execution["suggest_simulation"] is True
    assert database.get_document("simulation:queue", []) == []

def test_dependency_handoffs_are_versioned_and_unverified(database):
    m = SharedMemory("اختبار أجزاء مترابطة")
    class Worker:
        def __init__(self, key, deps, fail=False):
            self.task_id, self.depends_on, self.name, self.sub_question = key, deps, str(key), "جزء"
            self.fail = fail
        def execute(self):
            m.add_finding(self.name, self.sub_question, "دليل أولي", 80, "يحتاج مراجعة", status="failed" if self.fail else "complete")
    Orchestrator().run_dependencies([Worker(1, []), Worker(2, [1], True), Worker(3, [2])], m)
    assert m.coordination["tasks"]["1"]["state"] == "completed_unverified"
    assert m.coordination["tasks"]["2"]["state"] == "failed"
    assert m.coordination["tasks"]["3"]["state"] == "blocked"
    events = m.coordination["events"]
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    assert all(e["verification"] == "unverified" for e in events)
    assert database.get_session(m.session_id)["coordination"] == m.coordination
