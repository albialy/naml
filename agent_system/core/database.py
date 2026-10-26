"""Durable application data on SQLite or PostgreSQL. No external API required."""
import copy
import hashlib
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def now():
    return datetime.now(timezone.utc).isoformat()


class ConversationBusy(ValueError):
    pass


class Database:
    def __init__(self, backend=None, path=None, url=None, legacy_dir=None):
        self.backend = backend or os.getenv("STORAGE_BACKEND", "postgres" if os.getenv("DATABASE_URL") else "sqlite")
        self.backend = self.backend.lower().strip()
        if self.backend == "postgresql":
            self.backend = "postgres"
        if self.backend not in ("sqlite", "postgres"):
            raise ValueError("STORAGE_BACKEND must be sqlite or postgres. Legacy JSON files are imported automatically.")
        original_dir = Path(__file__).resolve().parents[1] / "storage"
        self.data_dir = Path(os.getenv("NAML_DATA_DIR", str(original_dir))).resolve()
        self.path = str(Path(path or os.getenv("DATABASE_PATH", str(self.data_dir / "naml.sqlite3"))).resolve())
        self.url = url or os.getenv("DATABASE_URL", "")
        if self.backend == "sqlite":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self.path, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
        elif not self.url:
            raise ValueError("PostgreSQL requires DATABASE_URL")
        with self.connection(write=True) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS naml_documents (key TEXT PRIMARY KEY, data TEXT NOT NULL)")
            conn.execute("CREATE TABLE IF NOT EXISTS naml_sessions (session_id TEXT PRIMARY KEY, user_id TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL)")
            conn.execute("CREATE INDEX IF NOT EXISTS naml_sessions_user_date ON naml_sessions (user_id, created_at)")
        self.import_legacy(Path(legacy_dir) if legacy_dir else original_dir)

    @contextmanager
    def connection(self, write=False):
        if self.backend == "sqlite":
            conn = sqlite3.connect(self.path, timeout=30)
            conn.execute("PRAGMA busy_timeout=30000")
            if write:
                conn.execute("BEGIN IMMEDIATE")
        else:
            import psycopg
            conn = psycopg.connect(self.url, connect_timeout=10)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def execute(self, conn, sql, args=()):
        return conn.execute(sql.replace("?", "%s") if self.backend == "postgres" else sql, args)

    def lock(self, conn, key):
        if self.backend == "postgres":
            value = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big", signed=True)
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (value,))

    def _get(self, conn, key, default=None):
        row = self.execute(conn, "SELECT data FROM naml_documents WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else copy.deepcopy(default)

    def _put(self, conn, key, value):
        self.execute(conn, "INSERT INTO naml_documents (key,data) VALUES (?,?) ON CONFLICT (key) DO UPDATE SET data=excluded.data", (key, json.dumps(value, ensure_ascii=False)))

    def get_document(self, key, default=None):
        with self.connection() as conn:
            return self._get(conn, key, default)

    def set_document(self, key, value):
        with self.connection(write=True) as conn:
            self.lock(conn, key)
            self._put(conn, key, value)

    def mutate_document(self, key, callback, default=None):
        with self.connection(write=True) as conn:
            self.lock(conn, key)
            value = callback(self._get(conn, key, default))
            self._put(conn, key, value)
            return copy.deepcopy(value)

    def delete_document(self, key):
        with self.connection(write=True) as conn:
            self.lock(conn, key)
            return self.execute(conn, "DELETE FROM naml_documents WHERE key=?", (key,)).rowcount > 0

    def _save_session(self, conn, data):
        self.execute(conn, "INSERT INTO naml_sessions (session_id,user_id,created_at,status,data) VALUES (?,?,?,?,?) ON CONFLICT (session_id) DO UPDATE SET user_id=excluded.user_id,created_at=excluded.created_at,status=excluded.status,data=excluded.data", (data["session_id"], data.get("user_id", ""), data.get("created_at", now()), data.get("status", "pending"), json.dumps(data, ensure_ascii=False)))

    def _update_conversation(self, conn, data):
        cid = data.get("conversation_id")
        if not cid:
            return
        key = "conversation:" + cid
        self.lock(conn, key)
        conversation = self._get(conn, key)
        if not conversation:
            return
        if conversation.get("active_session_id") == data["session_id"]:
            conversation["status"] = data.get("status", "pending")
            conversation["updated_at"] = now()
        if data.get("status") in ("complete", "failed"):
            message_id = data["session_id"] + ":assistant"
            message = {"id": message_id, "role": "assistant", "content": data.get("final_synthesis", ""), "session_id": data["session_id"], "created_at": data.get("completed_at") or now(), "status": data["status"], "confidence": data.get("confidence_final", 0), "execution": data.get("execution", {}), "warnings": data.get("warnings", [])}
            existing = next((m for m in conversation["messages"] if m["id"] == message_id), None)
            if existing:
                existing.update(message)
            else:
                conversation["messages"].append(message)
        self._put(conn, key, conversation)

    def save_session(self, data):
        with self.connection(write=True) as conn:
            cid = data.get("conversation_id")
            if cid:
                self.lock(conn, "conversation:" + cid)
            self._save_session(conn, data)
            self._update_conversation(conn, data)

    def get_session(self, session_id):
        with self.connection() as conn:
            row = self.execute(conn, "SELECT data FROM naml_sessions WHERE session_id=?", (session_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def list_sessions(self, user_id=None):
        with self.connection() as conn:
            sql = "SELECT data FROM naml_sessions"
            args = ()
            if user_id is not None:
                sql += " WHERE user_id=?"
                args = (user_id,)
            rows = self.execute(conn, sql + " ORDER BY created_at DESC,session_id DESC", args).fetchall()
            return [json.loads(row[0]) for row in rows]

    def delete_session(self, session_id):
        with self.connection(write=True) as conn:
            data_row = self.execute(conn, "SELECT data FROM naml_sessions WHERE session_id=?", (session_id,)).fetchone()
            if not data_row:
                return False
            data = json.loads(data_row[0])
            cid = data.get("conversation_id")
            if cid:
                key = "conversation:" + cid
                self.lock(conn, key)
                conversation = self._get(conn, key)
                if conversation:
                    if conversation.get("active_session_id") == session_id and conversation.get("status") in ("pending", "running", "synthesizing"):
                        raise ConversationBusy("Cannot delete an active analysis")
                    conversation["messages"] = [m for m in conversation["messages"] if m.get("session_id") != session_id]
                    remaining = [m for m in conversation["messages"] if m["role"] == "user"]
                    if remaining:
                        conversation["active_session_id"] = remaining[-1]["session_id"]
                        self._put(conn, key, conversation)
                    else:
                        self.execute(conn, "DELETE FROM naml_documents WHERE key=?", (key,))
            return self.execute(conn, "DELETE FROM naml_sessions WHERE session_id=?", (session_id,)).rowcount > 0

    def start_turn(self, data, conversation_id=None, project_id=None):
        cid = conversation_id or str(uuid.uuid4())
        key = "conversation:" + cid
        with self.connection(write=True) as conn:
            self.lock(conn, key)
            conversation = self._get(conn, key)
            if conversation_id and conversation is None:
                raise KeyError("Conversation not found")
            if conversation:
                if conversation["user_id"] != data["user_id"]:
                    raise PermissionError("Access denied")
                if conversation.get("status") in ("pending", "running", "synthesizing"):
                    raise ConversationBusy("This conversation already has an active analysis")
            else:
                conversation = {"conversation_id": cid, "user_id": data["user_id"], "title": data["task_original"][:100], "created_at": data["created_at"], "updated_at": data["created_at"], "messages": []}
            linked = conversation.get("project_id")
            if linked and project_id and linked != project_id:
                raise ValueError("المحادثة مرتبطة بمشروع آخر")
            project_id = linked or project_id
            if project_id:
                self.lock(conn, "project:" + project_id)
                project = self._get(conn, "project:" + project_id)
                if not project or project["user_id"] != data["user_id"]:
                    raise KeyError("المشروع غير موجود")
                conversation["project_id"] = project_id
                from agent_system.core.projects import project_context
                data = copy.deepcopy(data)
                data["project_context"] = project_context(project)
            data = copy.deepcopy(data)
            data["project_id"] = project_id
            history = [{"role": m["role"], "content": m["content"]} for m in conversation["messages"] if m.get("status") != "failed"]
            data = copy.deepcopy(data)
            data.update(conversation_id=cid, chat_history=history[-20:])
            conversation["messages"].append({"id": data["session_id"] + ":user", "role": "user", "content": data["task_original"], "session_id": data["session_id"], "created_at": data["created_at"]})
            conversation.update(active_session_id=data["session_id"], status="pending", updated_at=now())
            self._put(conn, key, conversation)
            self._save_session(conn, data)
            return data

    def get_conversation(self, cid):
        return self.get_document("conversation:" + cid)

    def list_conversations(self, user_id):
        with self.connection() as conn:
            rows = self.execute(conn, "SELECT data FROM naml_documents WHERE key LIKE ?", ("conversation:%",)).fetchall()
            conversations = [json.loads(row[0]) for row in rows]
        summaries = [{k: v for k, v in c.items() if k != "messages"} | {"message_count": len(c["messages"])} for c in conversations if c["user_id"] == user_id]
        return sorted(summaries, key=lambda c: c["updated_at"], reverse=True)

    def import_legacy(self, directory):
        """One-time, transactional import; leave original JSON files untouched."""
        marker = "legacy_import:" + str(directory.resolve())
        with self.connection(write=True) as conn:
            self.lock(conn, marker)
            if self._get(conn, marker):
                return
            for filename, key in [("settings.json", "settings"), ("settings_history.json", "settings_history"), ("users.json", "users"), ("activity_log.json", "activity_log")]:
                path = directory / filename
                if path.exists() and self._get(conn, key) is None:
                    self._put(conn, key, json.loads(path.read_text(encoding="utf-8")))
            for path in sorted((directory / "sessions").glob("*.json")):
                data = json.loads(path.read_text(encoding="utf-8"))
                if not data.get("session_id"):
                    continue
                exists = self.execute(conn, "SELECT 1 FROM naml_sessions WHERE session_id=?", (data["session_id"],)).fetchone()
                if exists:
                    continue
                cid = data.get("conversation_id") or data["session_id"]
                data["conversation_id"] = cid
                self._save_session(conn, data)
                key = "conversation:" + cid
                conversation = self._get(conn, key) or {"conversation_id": cid, "user_id": data.get("user_id", ""), "title": data.get("task_original", "")[:100], "created_at": data.get("created_at", now()), "updated_at": data.get("completed_at") or data.get("created_at", now()), "active_session_id": data["session_id"], "status": data.get("status", "complete"), "messages": []}
                conversation["messages"].append({"id": data["session_id"] + ":user", "role": "user", "content": data.get("task_original", ""), "session_id": data["session_id"], "created_at": data.get("created_at", now())})
                self._put(conn, key, conversation)
                self._update_conversation(conn, data)
            self._put(conn, marker, {"imported_at": now()})

    def import_session(self, data):
        """Import a legacy remote analysis without changing its identifier."""
        data = copy.deepcopy(data)
        cid = data.get("conversation_id") or data["session_id"]
        data["conversation_id"] = cid
        with self.connection(write=True) as conn:
            key = "conversation:" + cid
            self.lock(conn, key)
            if self.execute(conn, "SELECT 1 FROM naml_sessions WHERE session_id=?", (data["session_id"],)).fetchone():
                return False
            conversation = self._get(conn, key) or {"conversation_id": cid, "user_id": data.get("user_id", ""), "title": data.get("task_original", "")[:100], "created_at": data.get("created_at", now()), "updated_at": data.get("completed_at") or data.get("created_at", now()), "active_session_id": data["session_id"], "status": data.get("status", "complete"), "messages": []}
            conversation["messages"].append({"id": data["session_id"] + ":user", "role": "user", "content": data.get("task_original", ""), "session_id": data["session_id"], "created_at": data.get("created_at", now())})
            self._put(conn, key, conversation)
            self._save_session(conn, data)
            self._update_conversation(conn, data)
            return True


_database = None
_database_lock = threading.Lock()


def get_database():
    global _database
    with _database_lock:
        if _database is None:
            _database = Database()
        return _database
