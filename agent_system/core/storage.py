"""
NAML Storage Layer — Repository Pattern
=========================================
Single gateway for all session persistence.
Swap backends via env var STORAGE_BACKEND (json | supabase | ...).
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
            # this file lives in agent_system/core/ -> up one = agent_system/
            base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "storage", "sessions")
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def _path(self, session_id: str) -> str:
        # basic traversal guard
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


# ---------------------------------------------------------------
# Factory + singleton: the ONLY thing the rest of the code imports
# ---------------------------------------------------------------
_storage_instance: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    """Return the active backend. Chosen once per process via
    STORAGE_BACKEND env var. Default: json.
    Future: 'supabase' -> SupabaseStorage (drop-in, one env change)."""
    global _storage_instance
    if _storage_instance is None:
        backend = os.getenv("STORAGE_BACKEND", "json").lower().strip()
        if backend == "json":
            _storage_instance = JSONStorage()
        else:
            # Unknown backend: fail loudly at startup, not silently at runtime
            raise ValueError(f"Unknown STORAGE_BACKEND '{backend}'. Available: json")
    return _storage_instance
