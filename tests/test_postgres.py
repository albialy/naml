"""Optional integration tests with a real, disposable PostgreSQL server."""
import uuid
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

try:
    import pgserver
except ImportError:
    pgserver = None
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from agent_system.core.database import Database, ConversationBusy
from agent_system.core.memory import SharedMemory
from agent_system.core.settings_manager import settings_manager, SettingsManager
from agent_system.core.auth.manager import auth_manager, AuthManager
from agent_system.core import database as database_module, storage
from agent_system.migrate_database import from_sqlite


@pytest.fixture(scope="module")
def pg_uri(tmp_path_factory):
    existing = os.getenv("NAML_TEST_POSTGRES_URL")
    if existing:
        yield existing
        return
    if pgserver is None:
        pytest.skip("Supply NAML_TEST_POSTGRES_URL or install pgserver for PostgreSQL integration tests.")
    try:
        server = pgserver.get_server(tmp_path_factory.mktemp("postgres") / "pgdata", cleanup_mode="stop")
    except (OSError, subprocess.CalledProcessError) as error:
        pytest.skip(f"Local PostgreSQL cannot start in this environment: {type(error).__name__}. Supply NAML_TEST_POSTGRES_URL for a disposable test server.")
    yield server.get_uri()
    server.cleanup()


@pytest.fixture
def postgres_store(pg_uri, tmp_path, monkeypatch):
    schema = "test_" + uuid.uuid4().hex
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    url = make_conninfo(pg_uri, options="-c search_path=" + schema)
    db = Database(backend="postgres", url=url, legacy_dir=tmp_path / "legacy")
    monkeypatch.setattr(database_module, "_database", db)
    monkeypatch.setattr(auth_manager, "database", db)
    monkeypatch.setattr(settings_manager, "database", db)
    auth_manager.__init__()
    settings_manager.__init__()
    monkeypatch.setattr(storage, "_storage_instance", storage.SQLStorage())
    yield db
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_postgres_settings_and_login_survive_reinitialization(postgres_store):
    config = {"provider": "openrouter", "model": "qwen/qwen-72b-chat", "temperature": 0.3, "max_tokens": 2048}
    assert settings_manager.update_director(config, "admin")
    assert SettingsManager().get_settings()["director"] == config
    token = auth_manager.login("admin", "admin123")
    assert AuthManager().validate_token(token.token).username == "admin"


def test_postgres_turns_and_parallel_reservation(postgres_store):
    db = postgres_store
    first = db.start_turn(SharedMemory("سؤال PostgreSQL", user_id="u").to_dict())
    first.update(status="complete", final_synthesis="الرد")
    db.save_session(first)
    db.save_session(first)
    assert len(db.get_conversation(first["conversation_id"])["messages"]) == 2
    def reserve(index):
        try:
            db.start_turn(SharedMemory(str(index), user_id="u").to_dict(), first["conversation_id"])
            return True
        except ConversationBusy:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(reserve, range(4))) == 1
    assert len(db.list_sessions("u")) == 2


def test_postgres_document_writes_are_transactional(postgres_store):
    db = postgres_store
    def append(index):
        db.mutate_document("parallel", lambda values: values + [index], [])
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, range(24)))
    assert sorted(db.get_document("parallel")) == list(range(24))
    with pytest.raises(RuntimeError):
        with db.connection(write=True) as conn:
            db._put(conn, "rollback", {"secret": "temporary"})
            raise RuntimeError("rollback")
    assert db.get_document("rollback") is None


def test_sqlite_to_postgres_preserves_conversations(pg_uri, tmp_path, monkeypatch):
    source = Database(backend="sqlite", path=tmp_path / "source.sqlite3", legacy_dir=tmp_path / "empty")
    source.set_document("settings", {"director": {"provider": "openrouter"}})
    task = source.start_turn(SharedMemory("old SQLite question", user_id="u").to_dict())
    task.update(status="complete", final_synthesis="old answer")
    source.save_session(task)
    schema = "migration_" + uuid.uuid4().hex
    with psycopg.connect(pg_uri, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        target = Database(backend="postgres", url=make_conninfo(pg_uri, options="-c search_path=" + schema), legacy_dir=tmp_path / "empty")
        monkeypatch.setattr(database_module, "_database", target)
        assert from_sqlite(source.path) == 1
        assert target.get_document("settings") == source.get_document("settings")
        assert target.get_conversation(task["conversation_id"]) == source.get_conversation(task["conversation_id"])
        with pytest.raises(ValueError):
            from_sqlite(source.path)
        assert len(target.get_conversation(task["conversation_id"])["messages"]) == 2
    finally:
        with psycopg.connect(pg_uri, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def test_postgres_simulation_claims_are_exclusive_and_cancel_fenced(postgres_store, monkeypatch):
    from agent_system.simulation import service
    from agent_system.simulation.schema import SaveScenario, ProcessSpec, RunRequest, template
    monkeypatch.setenv("NAML_SIMULATION_ENABLED", "true")
    service.pulse()
    scenario = service.save_scenario("owner", SaveScenario(spec=ProcessSpec.model_validate(template())))
    request = RunRequest(scenario_id=scenario["id"], reviewed=True, request_key="same-request")
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = list(pool.map(lambda _: service.enqueue("owner", request), range(3)))
    assert len({j["id"] for j in jobs}) == 1
    with ThreadPoolExecutor(max_workers=3) as pool:
        claims = [c for c in pool.map(lambda _: service.claim(), range(3)) if c]
    assert len(claims) == 1
    job = claims[0]
    service.cancel("owner", job["id"])
    assert not service.finish(job["id"], job["lease_token"], result={"stale": True})
