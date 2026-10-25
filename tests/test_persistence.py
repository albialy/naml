import copy
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from agent_system.core.database import Database, ConversationBusy
from agent_system.core.memory import SharedMemory
from agent_system.core.settings_manager import SettingsManager, settings_manager
from agent_system.core.auth.manager import AuthManager, auth_manager
from agent_system.core.auth.models import UserRole
from agent_system.core.director import Director
from agent_system.core.worker import Worker
from agent_system.api.routes import tasks


def config():
    return {"provider": "openrouter", "model": "qwen/qwen-72b-chat", "temperature": 0.2, "max_tokens": 2048}


def test_settings_survive_new_process(database):
    assert settings_manager.update_director(config(), "admin")
    env = os.environ.copy()
    env["DATABASE_PATH"] = database.path
    result = subprocess.run([sys.executable, "-c", "import json; from agent_system.core.settings_manager import settings_manager; print(json.dumps(settings_manager.get_settings()['director']))"], env=env, capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == config()


def test_defaults_and_repeated_reads_do_not_reset(database):
    defaults = settings_manager.get_settings()
    assert "fast" in defaults["workers"]
    settings_manager.update_director(config(), "admin")
    for _ in range(5):
        assert SettingsManager().get_settings()["director"] == config()


def test_restore_keeps_actual_previous_snapshot(database):
    previous = settings_manager.get_settings()
    settings_manager.add_worker("extra", config(), "admin")
    assert settings_manager.restore_history(0, "admin")
    assert settings_manager.get_settings() == previous
    assert settings_manager.get_settings()["workers"] is not previous["workers"]


def test_settings_transaction_rolls_back(database, monkeypatch):
    previous = settings_manager.get_settings()
    original = database._put
    def fail(conn, key, value):
        if key == "activity_log":
            raise RuntimeError("simulated storage failure")
        return original(conn, key, value)
    monkeypatch.setattr(database, "_put", fail)
    with pytest.raises(RuntimeError):
        settings_manager.update_director(config(), "admin")
    assert settings_manager.get_settings() == previous


def test_director_really_selects_provider(database):
    settings_manager.update_director(config(), "admin")
    assert type(Director()._director_connector()).__name__ == "OpenRouterConnector"
    groq = {**config(), "provider": "groq", "model": "llama-3.3-70b-versatile"}
    settings_manager.update_director(groq, "admin")
    assert type(Director()._director_connector()).__name__ == "GroqConnector"


def test_token_survives_process_restart_and_logout(database):
    token = auth_manager.login("admin", "admin123")
    restarted = AuthManager()
    assert restarted.validate_token(token.token).username == "admin"
    assert restarted.logout(token.token)
    assert auth_manager.validate_token(token.token) is None
    with database.connection() as conn:
        assert conn.execute("SELECT 1 FROM naml_documents WHERE data LIKE ?", ("%" + token.token + "%",)).fetchone() is None


def test_messages_survive_reopen_and_feed_followup(database):
    first = SharedMemory("السؤال الأول", user_id="u")
    saved = database.start_turn(first.to_dict())
    first.conversation_id = saved["conversation_id"]
    first.final_synthesis = "الإجابة الأولى"
    first.status = "complete"
    first.save_to_file()
    first.save_to_file()  # Repeated persistence must not duplicate the reply.
    reopened = Database(backend="sqlite", path=database.path, legacy_dir=Path(database.path).parent / "legacy")
    conversation = reopened.get_conversation(first.conversation_id)
    assert [m["content"] for m in conversation["messages"]] == ["السؤال الأول", "الإجابة الأولى"]
    second = reopened.start_turn(SharedMemory("فسرها أكثر", user_id="u").to_dict(), first.conversation_id)
    assert second["chat_history"] == [{"role": "user", "content": "السؤال الأول"}, {"role": "assistant", "content": "الإجابة الأولى"}]


def test_busy_and_ownership_are_atomic(database):
    initial = database.start_turn(SharedMemory("first", user_id="u").to_dict())
    cid = initial["conversation_id"]
    with pytest.raises(ConversationBusy):
        database.start_turn(SharedMemory("second", user_id="u").to_dict(), cid)
    with pytest.raises(PermissionError):
        database.start_turn(SharedMemory("other", user_id="other").to_dict(), cid)
    assert len(database.get_conversation(cid)["messages"]) == 1


def test_simultaneous_followups_reserve_only_one_turn(database):
    first = database.start_turn(SharedMemory("first", user_id="u").to_dict())
    first.update(status="complete", final_synthesis="answer")
    database.save_session(first)
    def send(index):
        try:
            database.start_turn(SharedMemory(str(index), user_id="u").to_dict(), first["conversation_id"])
            return True
        except ConversationBusy:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(send, range(4))) == 1


def test_legacy_migration_is_idempotent_and_preserves_ids(tmp_path):
    legacy = tmp_path / "legacy"
    (legacy / "sessions").mkdir(parents=True)
    (legacy / "settings.json").write_text(json.dumps({"director": config(), "workers": {}, "system": {}}))
    old = {"session_id": "existing-id", "user_id": "u", "task_original": "old question", "final_synthesis": "old answer", "status": "complete", "created_at": "2026-10-01T12:00:00"}
    (legacy / "sessions" / "old.json").write_text(json.dumps(old))
    for _ in range(2):
        db = Database(backend="sqlite", path=tmp_path / "new.sqlite3", legacy_dir=legacy)
        assert db.get_document("settings")["director"] == config()
        assert len(db.list_sessions()) == 1
        assert len(db.get_conversation("existing-id")["messages"]) == 2
    assert json.loads((legacy / "sessions" / "old.json").read_text()) == old


def test_history_is_sorted_and_user_scoped(database):
    database.start_turn(SharedMemory("older", user_id="a").to_dict())
    database.start_turn(SharedMemory("private", user_id="b").to_dict())
    database.start_turn(SharedMemory("newer", user_id="a").to_dict())
    assert [c["title"] for c in database.list_conversations("a")] == ["newer", "older"]


def test_context_is_bounded_but_saved_messages_are_untouched(database):
    history = [{"role": "user", "content": str(i) + "x" * 8000} for i in range(30)]
    original = copy.deepcopy(history)
    memory = SharedMemory("followup", chat_history=history)
    assert len(memory.conversation_context()) < 25000
    assert memory.chat_history == original


def test_context_reaches_planning_and_worker(database, monkeypatch):
    memory = SharedMemory("وضحها", chat_history=[{"role": "user", "content": "unique previous context"}])
    prompts = []
    director = Director()
    def analyze(task, memory=None):
        prompts.append(task)
        return {"agents": [], "pattern": "A", "real_question": "followup"}
    monkeypatch.setattr(director, "choose_strategy", lambda *args: {"route":"team", "reason":"test"})
    monkeypatch.setattr(director, "analyze_task", analyze)
    monkeypatch.setattr(director, "_synthesize", lambda memory: None)
    monkeypatch.setattr(director, "_critic", lambda memory: None)
    director.run("وضحها", memory)
    assert "unique previous context" in prompts[0]
    worker = Worker("A", "analyst", "test", "general", "none", "fast", None, memory)
    assert "unique previous context" in worker._full_prompt()


def test_api_conversation_continuation_and_permissions(client, headers, database, monkeypatch):
    histories = []
    def finish(self, task, memory):
        histories.append(memory.chat_history)
        memory.final_synthesis = "رد نمل: " + task
        memory.status = "complete"
        memory.confidence_final = 60
        memory.save_to_file()
    monkeypatch.setattr(Director, "run", finish)
    first = client.post("/api/task", json={"task": "مرحبا"}, headers=headers)
    assert first.status_code == 200
    cid = first.json()["conversation_id"]
    assert client.post("/api/task", json={"task": "تابع", "conversation_id": cid}, headers=headers).status_code == 200
    saved = client.get("/api/conversations/" + cid, headers=headers).json()
    assert len(saved["messages"]) == 4
    assert histories[1][-1]["content"] == "رد نمل: مرحبا"
    admin = auth_manager.get_user_by_username("admin")
    auth_manager.create_user("other", "password", UserRole.USER, admin.id)
    token = auth_manager.login("other", "password")
    other = {"Authorization": "Bearer " + token.token}
    assert client.get("/api/conversations/" + cid, headers=other).status_code == 403
    assert client.post("/api/task", json={"task": "steal", "conversation_id": cid}, headers=other).status_code == 403
    assert client.get("/api/conversations", headers=other).json() == []
    assert client.get("/api/conversations/" + cid).status_code in (401, 403)


def test_missing_conversation_and_validation(client, headers):
    assert client.post("/api/task", json={"task": "test", "conversation_id": "missing"}, headers=headers).status_code == 404
    assert client.post("/api/task", json={"task": "   "}, headers=headers).status_code == 400
    assert client.post("/api/task", json={"task": "x" * 20001}, headers=headers).status_code == 422


def test_restart_recovers_interrupted_turn(database, monkeypatch):
    import asyncio
    from agent_system.api.main import startup_event
    from agent_system.core.connectors.groq_connector import GroqConnector
    from agent_system.core.connectors.openrouter_connector import OpenRouterConnector
    monkeypatch.setattr(GroqConnector, "validate_connection", lambda self: False)
    monkeypatch.setattr(OpenRouterConnector, "validate_connection", lambda self: False)
    old = database.start_turn(SharedMemory("interrupted", user_id="u").to_dict())
    asyncio.run(startup_event())
    restored = database.get_conversation(old["conversation_id"])
    assert restored["status"] == "failed"
    assert restored["messages"][-1]["status"] == "failed"
    assert database.start_turn(SharedMemory("continue", user_id="u").to_dict(), old["conversation_id"])


def test_storage_failure_is_not_reported_as_saved(database, monkeypatch):
    def fail(data):
        raise OSError("disk full")
    monkeypatch.setattr(database, "save_session", fail)
    with pytest.raises(OSError):
        SharedMemory("test").save_to_file()


def test_failed_provider_is_failed_turn_not_complete(database):
    memory = SharedMemory("test", user_id="u")
    saved = database.start_turn(memory.to_dict())
    memory.conversation_id = saved["conversation_id"]
    Director().run("test", memory)
    assert memory.status == "failed"
    assert database.get_conversation(memory.conversation_id)["messages"][-1]["status"] == "failed"


def test_concurrent_log_writes_keep_every_entry(database):
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda n: auth_manager._log_activity("test", str(n)), range(20)))
    assert len(database.get_document("activity_log")) == 20


def test_sqlite_migration_keeps_history_and_refuses_overwrite(database, tmp_path):
    from agent_system.migrate_database import from_sqlite
    source = Database(backend="sqlite", path=tmp_path / "old data #1.sqlite3", legacy_dir=tmp_path / "none")
    source.set_document("settings", {"director": config()})
    data = source.start_turn(SharedMemory("old conversation", user_id="u").to_dict())
    data.update(status="complete", final_synthesis="persisted answer")
    source.save_session(data)
    with database.connection(write=True) as conn:
        conn.execute("DELETE FROM naml_documents")
    assert from_sqlite(source.path) == 1
    assert database.get_document("settings") == source.get_document("settings")
    assert database.get_conversation(data["conversation_id"]) == source.get_conversation(data["conversation_id"])
    with pytest.raises(ValueError):
        from_sqlite(source.path)
    assert len(database.get_conversation(data["conversation_id"])["messages"]) == 2


def test_supabase_migration_paginates_and_is_idempotent(database, monkeypatch):
    from agent_system import migrate_database
    offsets = []
    rows = [{"data": {"session_id": "remote-" + str(n), "user_id": "u", "task_original": "legacy", "final_synthesis": "answer", "status": "complete", "created_at": "2026-10-01"}} for n in range(3)]
    class Requests:
        def get(self, endpoint, headers, params, timeout):
            offset = params["offset"]
            offsets.append(offset)
            class Response:
                def raise_for_status(self): pass
                def json(self): return rows[offset:offset+2]
            return Response()
    class Source:
        endpoint = "offline"
        headers = {}
        _requests = Requests()
    monkeypatch.setattr(migrate_database, "SupabaseStorage", Source)
    assert migrate_database.from_supabase() == 3
    assert offsets == [0, 2, 3]
    assert migrate_database.from_supabase() == 0
    assert len(database.list_sessions("u")) == 3
    assert len(database.get_conversation("remote-0")["messages"]) == 2


def test_corrupt_legacy_files_do_not_replace_data(tmp_path):
    legacy = tmp_path / "legacy"
    (legacy / "sessions").mkdir(parents=True)
    (legacy / "settings.json").write_text(json.dumps({"director": config()}))
    (legacy / "sessions" / "broken.json").write_text("{broken")
    with pytest.raises(json.JSONDecodeError):
        Database(backend="sqlite", path=tmp_path / "new.sqlite3", legacy_dir=legacy)
    import sqlite3
    with sqlite3.connect(tmp_path / "new.sqlite3") as conn:
        assert conn.execute("SELECT COUNT(*) FROM naml_documents").fetchone()[0] == 0
