from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from agent_system.core.auth.manager import auth_manager, LOGS_FILE
from agent_system.core.auth.models import User, UserRole
from agent_system.core.auth.middleware import require_super_admin
import os
import json

router = APIRouter()

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str
    session_limit: int = 0

class UpdateUserRequest(BaseModel):
    is_active: Optional[bool] = None
    session_limit: Optional[int] = None
    role: Optional[str] = None

@router.get("/api/admin/users")
async def get_all_users(current_user: User = Depends(require_super_admin)):
    users = auth_manager.list_users(current_user.id)
    for u in users:
        u.pop("password_hash", None)
    return users

@router.post("/api/admin/users")
async def create_user(request: CreateUserRequest, current_user: User = Depends(require_super_admin)):
    try:
        role = UserRole(request.role)
    except:
        raise HTTPException(status_code=400, detail={"error": "Invalid role", "code": "INVALID_ROLE"})
        
    new_user = auth_manager.create_user(request.username, request.password, role, current_user.id, request.session_limit)
    if not new_user:
        raise HTTPException(status_code=400, detail={"error": "Username already exists or invalid request", "code": "USER_CREATION_FAILED"})
        
    user_dict = new_user.to_dict()
    user_dict.pop("password_hash", None)
    return user_dict

@router.put("/api/admin/users/{user_id}")
async def update_user(user_id: str, request: UpdateUserRequest, current_user: User = Depends(require_super_admin)):
    updates = {k: v for k, v in request.dict().items() if v is not None}
    success = auth_manager.update_user(user_id, current_user.id, updates)
    if not success:
        raise HTTPException(status_code=400, detail={"error": "User not found or cannot update self role/status", "code": "USER_UPDATE_FAILED"})
    return {"success": True}

@router.delete("/api/admin/users/{user_id}")
async def delete_user(user_id: str, current_user: User = Depends(require_super_admin)):
    success = auth_manager.delete_user(user_id, current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail={"error": "User not found or cannot delete self", "code": "USER_DELETION_FAILED"})
    return {"success": True}

@router.get("/api/admin/sessions")
async def get_all_sessions(current_user: User = Depends(require_super_admin)):
    storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'storage', 'sessions')
    if not os.path.exists(storage_dir):
        return []
        
    sessions = []
    for filename in os.listdir(storage_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(storage_dir, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    user_id = data.get("user_id", "")
                    user = auth_manager.get_user(user_id)
                    username = user.username if user else "unknown"
                    
                    sessions.append({
                        "session_id": data.get("session_id"),
                        "task_original": data.get("task_original"),
                        "status": data.get("status"),
                        "created_at": data.get("created_at"),
                        "confidence_final": data.get("confidence_final"),
                        "user_id": user_id,
                        "username": username
                    })
            except Exception:
                continue
                
    return sessions

@router.get("/api/admin/logs")
async def get_logs(current_user: User = Depends(require_super_admin)):
    if not os.path.exists(LOGS_FILE):
        return []
    try:
        with open(LOGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return []
