from fastapi import APIRouter, Depends, HTTPException, Security
from pydantic import BaseModel
from ...core.auth.manager import auth_manager
from ...core.auth.models import User
from ...core.auth.middleware import get_current_user
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

router = APIRouter()
security = HTTPBearer()

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

@router.post("/api/auth/login")
async def login(request: LoginRequest):
    token = auth_manager.login(request.username, request.password)
    if not token:
        raise HTTPException(status_code=401, detail={"error": "Invalid credentials or inactive user", "code": "INVALID_CREDENTIALS"})
    
    user = auth_manager.get_user(token.user_id)
    return {
        "token": token.token,
        "role": user.role.value if hasattr(user.role, 'value') else user.role,
        "username": user.username
    }

@router.post("/api/auth/logout")
async def logout(credentials: HTTPAuthorizationCredentials = Security(security)):
    success = auth_manager.logout(credentials.credentials)
    if not success:
        raise HTTPException(status_code=401, detail={"error": "Invalid token", "code": "INVALID_TOKEN"})
    return {"success": True}

@router.get("/api/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    user_dict = current_user.to_dict()
    user_dict.pop("password_hash", None)
    return user_dict

@router.post("/api/auth/change-password")
async def change_password(request: ChangePasswordRequest, current_user: User = Depends(get_current_user)):
    success = auth_manager.change_password(current_user.id, request.old_password, request.new_password)
    if not success:
        raise HTTPException(status_code=400, detail={"error": "Invalid old password", "code": "INVALID_PASSWORD"})
    return {"success": True}
