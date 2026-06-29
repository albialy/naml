from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import List

class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    OPERATOR = "operator"
    USER = "user"

@dataclass
class User:
    id: str
    username: str
    password_hash: str
    role: UserRole
    is_active: bool
    created_at: str
    last_login: str
    session_limit: int
    allowed_models: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "password_hash": self.password_hash,
            "role": self.role.value if isinstance(self.role, UserRole) else self.role,
            "is_active": self.is_active,
            "created_at": self.created_at,
            "last_login": self.last_login,
            "session_limit": self.session_limit,
            "allowed_models": self.allowed_models
        }

@dataclass
class AuthToken:
    token: str
    user_id: str
    expires_at: datetime
    created_at: datetime
