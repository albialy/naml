import json
import os
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from agent_system.core.auth.models import User, UserRole, AuthToken

STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'storage')
USERS_FILE = os.path.join(STORAGE_DIR, 'users.json')
LOGS_FILE = os.path.join(STORAGE_DIR, 'activity_log.json')

class AuthManager:
    def __init__(self):
        self.users: Dict[str, User] = {}
        self.active_tokens: Dict[str, AuthToken] = {}
        os.makedirs(STORAGE_DIR, exist_ok=True)
        self._load_users()

    def _hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    def _log_activity(self, action: str, performed_by: str, target: str = ""):
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "performed_by": performed_by,
            "target": target
        }
        logs = []
        if os.path.exists(LOGS_FILE):
            try:
                with open(LOGS_FILE, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            except:
                pass
        logs.append(log_entry)
        try:
            with open(LOGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2)
        except:
            pass

    def _load_users(self):
        if not os.path.exists(USERS_FILE):
            print("First run detected. Admin created. Username: admin / Password: admin123 Please change password immediately.")
            admin_user = User(
                id=str(uuid.uuid4()),
                username="admin",
                password_hash=self._hash_password("admin123"),
                role=UserRole.SUPER_ADMIN,
                is_active=True,
                created_at=datetime.now().isoformat(),
                last_login="",
                session_limit=0
            )
            self.users[admin_user.id] = admin_user
            self._save_users()
            self._log_activity("SYSTEM_STARTUP_ADMIN_CREATED", "SYSTEM", admin_user.id)
            return

        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for user_id, user_data in data.items():
                    # Handle enum conversion
                    try:
                        role = UserRole(user_data["role"])
                    except:
                        role = UserRole.USER
                        
                    self.users[user_id] = User(
                        id=user_data["id"],
                        username=user_data["username"],
                        password_hash=user_data["password_hash"],
                        role=role,
                        is_active=user_data["is_active"],
                        created_at=user_data["created_at"],
                        last_login=user_data.get("last_login", ""),
                        session_limit=user_data.get("session_limit", 0),
                        allowed_models=user_data.get("allowed_models", [])
                    )
        except Exception as e:
            print(f"Error loading users: {e}")

    def _save_users(self):
        try:
            with open(USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump({user_id: user.to_dict() for user_id, user in self.users.items()}, f, indent=2)
        except Exception as e:
            print(f"Error saving users: {e}")

    def get_user_by_username(self, username: str) -> Optional[User]:
        for user in self.users.values():
            if user.username == username:
                return user
        return None

    def get_user(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    def create_user(self, username: str, password: str, role: UserRole, created_by_id: str, session_limit: int = 0) -> Optional[User]:
        creator = self.get_user(created_by_id)
        if not creator or creator.role != UserRole.SUPER_ADMIN:
            return None

        if self.get_user_by_username(username):
            return None

        new_user = User(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=self._hash_password(password),
            role=role,
            is_active=True,
            created_at=datetime.now().isoformat(),
            last_login="",
            session_limit=session_limit
        )
        self.users[new_user.id] = new_user
        self._save_users()
        self._log_activity("CREATE_USER", created_by_id, new_user.id)
        return new_user

    def login(self, username: str, password: str) -> Optional[AuthToken]:
        user = self.get_user_by_username(username)
        if not user or not user.is_active:
            return None

        if user.password_hash != self._hash_password(password):
            return None

        user.last_login = datetime.now().isoformat()
        self._save_users()

        token_str = str(uuid.uuid4())
        token = AuthToken(
            token=token_str,
            user_id=user.id,
            expires_at=datetime.now() + timedelta(hours=24),
            created_at=datetime.now()
        )
        self.active_tokens[token_str] = token
        self._log_activity("LOGIN", user.id)
        return token

    def logout(self, token: str) -> bool:
        if token in self.active_tokens:
            user_id = self.active_tokens[token].user_id
            del self.active_tokens[token]
            self._log_activity("LOGOUT", user_id)
            return True
        return False

    def validate_token(self, token: str) -> Optional[User]:
        if token not in self.active_tokens:
            return None
        auth_token = self.active_tokens[token]
        if datetime.now() > auth_token.expires_at:
            del self.active_tokens[token]
            return None
        user = self.get_user(auth_token.user_id)
        if not user or not user.is_active:
            return None
        return user

    def change_password(self, user_id: str, old_password: str, new_password: str) -> bool:
        user = self.get_user(user_id)
        if not user or user.password_hash != self._hash_password(old_password):
            return False
        user.password_hash = self._hash_password(new_password)
        self._save_users()
        self._log_activity("CHANGE_PASSWORD", user_id)
        return True

    def list_users(self, requesting_user_id: str) -> List[dict]:
        user = self.get_user(requesting_user_id)
        if not user:
            return []
        if user.role == UserRole.SUPER_ADMIN:
            return [u.to_dict() for u in self.users.values()]
        return [user.to_dict()]

    def toggle_user_active(self, user_id: str, requesting_user_id: str) -> bool:
        req_user = self.get_user(requesting_user_id)
        if not req_user or req_user.role != UserRole.SUPER_ADMIN:
            return False
        target = self.get_user(user_id)
        if not target or target.id == requesting_user_id:
            return False
        target.is_active = not target.is_active
        self._save_users()
        self._log_activity(f"TOGGLE_ACTIVE_{target.is_active}", requesting_user_id, target.id)
        return True

    def delete_user(self, user_id: str, requesting_user_id: str) -> bool:
        req_user = self.get_user(requesting_user_id)
        if not req_user or req_user.role != UserRole.SUPER_ADMIN:
            return False
        if user_id == requesting_user_id or user_id not in self.users:
            return False
        del self.users[user_id]
        self._save_users()
        self._log_activity("DELETE_USER", requesting_user_id, user_id)
        return True

    def update_user(self, user_id: str, requesting_user_id: str, updates: dict) -> bool:
        req_user = self.get_user(requesting_user_id)
        if not req_user or req_user.role != UserRole.SUPER_ADMIN:
            return False
        target = self.get_user(user_id)
        if not target:
            return False
            
        if "is_active" in updates and target.id != requesting_user_id:
            target.is_active = updates["is_active"]
        if "session_limit" in updates:
            target.session_limit = updates["session_limit"]
        if "role" in updates and target.id != requesting_user_id:
            try:
                target.role = UserRole(updates["role"])
            except:
                pass
                
        self._save_users()
        self._log_activity("UPDATE_USER", requesting_user_id, target.id)
        return True

auth_manager = AuthManager()
