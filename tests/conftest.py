import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest

# Tests never use application data or real model credentials.
_bootstrap = tempfile.mkdtemp(prefix="naml-tests-")
atexit.register(shutil.rmtree, _bootstrap, ignore_errors=True)
os.environ["NAML_DATA_DIR"] = _bootstrap
os.environ["STORAGE_BACKEND"] = "sqlite"
os.environ.pop("DATABASE_URL", None)
os.environ.pop("GROQ_API_KEY", None)
os.environ.pop("OPENROUTER_API_KEY", None)
for _key in ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET", "GITHUB_REDIRECT_URI"):
    os.environ.pop(_key, None)

from agent_system.core.database import Database
from agent_system.core import database as database_module, storage
from agent_system.core.auth.manager import auth_manager
from agent_system.core.settings_manager import settings_manager
from agent_system.api.main import app
from agent_system.core.connectors.groq_connector import GroqConnector
from agent_system.core.connectors.openrouter_connector import OpenRouterConnector
from fastapi.testclient import TestClient


@pytest.fixture
def database(tmp_path, monkeypatch):
    db = Database(backend="sqlite", path=tmp_path / "app.sqlite3", legacy_dir=tmp_path / "legacy")
    monkeypatch.setattr(database_module, "_database", db)
    monkeypatch.setattr(auth_manager, "database", db)
    monkeypatch.setattr(settings_manager, "database", db)
    auth_manager.__init__()
    settings_manager.__init__()
    monkeypatch.setattr(storage, "_storage_instance", storage.SQLStorage())
    return db


@pytest.fixture
def client(database, monkeypatch):
    monkeypatch.setattr(GroqConnector, "validate_connection", lambda self: False)
    monkeypatch.setattr(OpenRouterConnector, "validate_connection", lambda self: False)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def headers(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}
