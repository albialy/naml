"""
NAML Storage Layer — Repository Pattern
=========================================
Single gateway for all session persistence.
Swap backends via env var STORAGE_BACKEND (json | supabase).
The rest of the system NEVER touches files or databases directly.
"""
import os
import json
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class StorageBackend(ABC):
    """The contract every storage backend must fulfill."""

    @abstractmethod
    def save_session(self, session: Dict[str, Any]) -> None:
        """Create or update a session (upsert by session_id)."""
        ...

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Return full session dict, or None if not found."""
        ...

    @abstractmethod
    def list_sessions(self) -> List[Dict[str, Any]]:
        """Return all sessions (full dicts). Callers filter/shape."""
        ...

    @abstractmethod
    def delete_session(self, session_id: str) -> bool:
        """Delete a session. Return True if it existed."""
        ...


class JSONStorage(StorageBackend):
    """File-based backend. Same paths as the legacy system,
    so existing data keeps working with zero migration."""

    def __init__(self, base_dir: Optional[str] = None):
        if base_dir is None:
            base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "sessions")
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _path(self, session_id: str) -> str:
        safe_id = os.path.basename(str(session_id))
        return os.path.join(self.base_dir, f"{safe_id}.json")

    def save_session(self, session: Dict[str, Any]) -> None:
        session_id = session.get("session_id")
        if not session_id:
            raise ValueError("session dict must contain 'session_id'")
        try:
            with open(self._path(session_id), "w", encoding="utf-8") as f:
                json.dump(session, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[storage] save failed / فشل الحفظ: {e}")

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        path = self._path(session_id)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[storage] read failed / فشل القراءة: {e}")
            return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        sessions: List[Dict[str, Any]] = []
        if not os.path.exists(self.base_dir):
            return sessions
        for filename in os.listdir(self.base_dir):
            if not filename.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.base_dir, filename), "r", encoding="utf-8") as f:
                    sessions.append(json.load(f))
            except Exception:
                continue
        return sessions

    def delete_session(self, session_id: str) -> bool:
        path = self._path(session_id)
        if not os.path.exists(path):
            return False
        try:
            os.remove(path)
            return True
        except Exception as e:
            print(f"[storage] delete failed / فشل الحذف: {e}")
            return False


class SupabaseStorage(StorageBackend):
    """The Queen's body — persistent memory that survives every deploy.
    Uses Supabase PostgREST API directly via requests (no extra SDK needed).
    Table schema: sessions(session_id text pk, user_id text, data jsonb,
                           status text, created_at, updated_at)."""

    def __init__(self):
        import requests  # already in requirements
        self._requests = requests
        self.url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.key = os.getenv("SUPABASE_SECRET_KEY", "")
        if not self.url or not self.key:
            raise ValueError(
                "SupabaseStorage requires SUPABASE_URL and SUPABASE_SECRET_KEY env vars / "
                "متغيرات Supabase غير مضبوطة"
            )
        self.endpoint = f"{self.url}/rest/v1/sessions"
        self.headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def save_session(self, session: Dict[str, Any]) -> None:
        session_id = session.get("session_id")
        if not session_id:
            raise ValueError("session dict must contain 'session_id'")
        row = {
            "session_id": session_id,
            "user_id": session.get("user_id", ""),
            "data": session,
            "status": session.get("status", "pending"),
        }
        try:
            resp = self._requests.post(
                self.endpoint,
                headers={**self.headers, "Prefer": "resolution=merge-duplicates"},
                json=row,
                timeout=15,
            )
            if resp.status_code >= 400:
                print(f"[supabase] save failed {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[supabase] save error / خطأ الحفظ: {e}")

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        try:
            resp = self._requests.get(
                self.endpoint,
                headers=self.headers,
                params={"session_id": f"eq.{session_id}", "select": "data"},
                timeout=15,
            )
            if resp.status_code == 200:
                rows = resp.json()
                if rows:
                    return rows[0].get("data")
            return None
        except Exception as e:
            print(f"[supabase] read error / خطأ القراءة: {e}")
            return None

    def list_sessions(self) -> List[Dict[str, Any]]:
        try:
            resp = self._requests.get(
                self.endpoint,
                headers=self.headers,
                params={"select": "data", "order": "created_at.desc", "limit": "500"},
                timeout=20,
            )
            if resp.status_code == 200:
                return [row.get("data") for row in resp.json() if row.get("data")]
            print(f"[supabase] list failed {resp.status_code}: {resp.text[:200]}")
            return []
        except Exception as e:
            print(f"[supabase] list error / خطأ القائمة: {e}")
            return []

    def delete_session(self, session_id: str) -> bool:
        try:
            resp = self._requests.delete(
                self.endpoint,
                headers={**self.headers, "Prefer": "return=representation"},
                params={"session_id": f"eq.{session_id}"},
                timeout=15,
            )
            return resp.status_code in (200, 204) and bool(resp.text and resp.text != "[]")
        except Exception as e:
            print(f"[supabase] delete error / خطأ الحذف: {e}")
            return False


# ---------------------------------------------------------------
# Factory + singleton: the ONLY thing the rest of the code imports
# ---------------------------------------------------------------
_storage_instance: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    """Return the active backend. Chosen once per process via
    STORAGE_BACKEND env var. Default: json."""
    global _storage_instance
    if _storage_instance is None:
        backend = os.getenv("STORAGE_BACKEND", "json").lower().strip()
        if backend == "json":
            _storage_instance = JSONStorage()
        elif backend == "supabase":
            _storage_instance = SupabaseStorage()
        else:
            raise ValueError(f"Unknown STORAGE_BACKEND '{backend}'. Available: json, supabase")
    return _storage_instance
