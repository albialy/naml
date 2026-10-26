import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from agent_system.core.auth.models import User, UserRole, AuthToken
from agent_system.core.database import get_database


class AuthManager:
    def __init__(self):
        self.database = get_database()
        def initialize(users):
            if users is not None:
                return users
            user = User(id=str(uuid.uuid4()), username="admin", password_hash=self._hash_password("admin123"), role=UserRole.SUPER_ADMIN, is_active=True, created_at=datetime.now(timezone.utc).isoformat(), last_login="", session_limit=0)
            return {user.id: user.to_dict()}
        self.database.mutate_document("users", initialize)

    def _hash_password(self, password):
        # Keep compatibility with existing accounts; password hardening is separate.
        return hashlib.sha256(password.encode()).hexdigest()

    def _decode(self, data):
        if not data:
            return None
        return User(id=data["id"], username=data["username"], password_hash=data["password_hash"], role=UserRole(data["role"]), is_active=data["is_active"], created_at=data["created_at"], last_login=data.get("last_login", ""), session_limit=data.get("session_limit", 0), allowed_models=data.get("allowed_models", []))

    def _log_activity(self, action, performed_by, target=""):
        entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "action": action, "performed_by": performed_by, "target": target}
        self.database.mutate_document("activity_log", lambda logs: logs + [entry], [])

    def get_user(self, user_id):
        return self._decode(self.database.get_document("users", {}).get(user_id))

    def get_user_by_username(self, username):
        users = self.database.get_document("users", {})
        return next((self._decode(user) for user in users.values() if user["username"] == username), None)

    def _save_user(self, user, fields):
        def save(users):
            if user.id not in users:
                raise ValueError("User no longer exists")
            data = user.to_dict()
            for field in fields:
                users[user.id][field] = data[field]
            return users
        self.database.mutate_document("users", save, {})

    def create_user(self, username, password, role, created_by_id, session_limit=0):
        creator = self.get_user(created_by_id)
        if not creator or creator.role != UserRole.SUPER_ADMIN or not username.strip() or not password or session_limit < 0:
            return None
        user = User(id=str(uuid.uuid4()), username=username.strip(), password_hash=self._hash_password(password), role=role, is_active=True, created_at=datetime.now(timezone.utc).isoformat(), last_login="", session_limit=session_limit)
        created = False
        def create(users):
            nonlocal created
            if any(u["username"] == user.username for u in users.values()):
                return users
            users[user.id] = user.to_dict()
            created = True
            return users
        self.database.mutate_document("users", create, {})
        if not created:
            return None
        self._log_activity("CREATE_USER", created_by_id, user.id)
        return user

    def _token_key(self, token):
        return "token:" + hashlib.sha256(token.encode()).hexdigest()

    def login(self, username, password):
        user = self.get_user_by_username(username)
        if not user or not user.is_active or user.password_hash != self._hash_password(password):
            return None
        user.last_login = datetime.now(timezone.utc).isoformat()
        self._save_user(user, ["last_login"])
        created_at = datetime.now(timezone.utc)
        token = AuthToken(token=str(uuid.uuid4()), user_id=user.id, expires_at=created_at + timedelta(hours=24), created_at=created_at)
        self.database.set_document(self._token_key(token.token), {"user_id": user.id, "expires_at": token.expires_at.isoformat(), "created_at": created_at.isoformat()})
        self._log_activity("LOGIN", user.id)
        return token

    def validate_token(self, token):
        key = self._token_key(token)
        data = self.database.get_document(key)
        if not data:
            return None
        if datetime.now(timezone.utc) > datetime.fromisoformat(data["expires_at"]):
            self.database.delete_document(key)
            return None
        user = self.get_user(data["user_id"])
        return user if user and user.is_active else None

    def logout(self, token):
        key = self._token_key(token)
        data = self.database.get_document(key)
        if not data or not self.database.delete_document(key):
            return False
        self._log_activity("LOGOUT", data["user_id"])
        return True

    def change_password(self, user_id, old_password, new_password):
        user = self.get_user(user_id)
        if not user or not new_password or user.password_hash != self._hash_password(old_password):
            return False
        user.password_hash = self._hash_password(new_password)
        self._save_user(user, ["password_hash"])
        self._log_activity("CHANGE_PASSWORD", user_id)
        return True

    def list_users(self, requesting_user_id):
        user = self.get_user(requesting_user_id)
        if not user:
            return []
        if user.role == UserRole.SUPER_ADMIN:
            return list(self.database.get_document("users", {}).values())
        return [user.to_dict()]

    def update_user(self, user_id, requesting_user_id, updates):
        requester = self.get_user(requesting_user_id)
        if not requester or requester.role != UserRole.SUPER_ADMIN:
            return False
        if user_id == requesting_user_id and ("role" in updates or "is_active" in updates):
            return False
        if "session_limit" in updates and updates["session_limit"] < 0:
            return False
        if "role" in updates:
            try:
                UserRole(updates["role"])
            except ValueError:
                return False
        changed = False
        def update(users):
            nonlocal changed
            if user_id in users:
                for key in ("role", "is_active", "session_limit"):
                    if key in updates:
                        users[user_id][key] = updates[key]
                changed = True
            return users
        self.database.mutate_document("users", update, {})
        if changed:
            self._log_activity("UPDATE_USER", requesting_user_id, user_id)
        return changed

    def toggle_user_active(self, user_id, requesting_user_id):
        user = self.get_user(user_id)
        return self.update_user(user_id, requesting_user_id, {"is_active": not user.is_active}) if user else False

    def delete_user(self, user_id, requesting_user_id):
        requester = self.get_user(requesting_user_id)
        if not requester or requester.role != UserRole.SUPER_ADMIN or user_id == requesting_user_id:
            return False
        deleted = False
        def remove(users):
            nonlocal deleted
            deleted = users.pop(user_id, None) is not None
            return users
        self.database.mutate_document("users", remove, {})
        if deleted:
            self._log_activity("DELETE_USER", requesting_user_id, user_id)
        return deleted


auth_manager = AuthManager()
