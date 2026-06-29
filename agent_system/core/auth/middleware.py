from fastapi import Request, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from .manager import auth_manager
from .models import User, UserRole

security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security)) -> User:
    token = credentials.credentials
    user = auth_manager.validate_token(token)
    if not user:
        raise HTTPException(
            status_code=401,
            detail={"error": "Invalid or expired token", "code": "UNAUTHORIZED"}
        )
    return user

async def require_super_admin(current_user: User = Security(get_current_user)) -> User:
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=403,
            detail={"error": "Requires SUPER_ADMIN role", "code": "FORBIDDEN"}
        )
    return current_user

async def require_operator_or_above(current_user: User = Security(get_current_user)) -> User:
    if current_user.role not in [UserRole.SUPER_ADMIN, UserRole.OPERATOR]:
        raise HTTPException(
            status_code=403,
            detail={"error": "Requires OPERATOR or higher role", "code": "FORBIDDEN"}
        )
    return current_user
