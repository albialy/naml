from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from agent_system.core.auth.manager import auth_manager
from agent_system.core.database import get_database
from agent_system.core.storage import get_storage
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
    sessions = []
    for data in get_storage().list_sessions():
        user = auth_manager.get_user(data.get("user_id", ""))
        sessions.append({key: data.get(key) for key in ["session_id", "conversation_id", "task_original", "status", "created_at", "confidence_final", "user_id"]} | {"username": user.username if user else "unknown"})
    return sessions

@router.get("/api/admin/logs")
async def get_logs(current_user: User = Depends(require_super_admin)):
    return get_database().get_document("activity_log", [])

@router.get("/api/debug/search-test")
async def debug_search_test(q: str = "Egypt earthquake 2026"):
    """Temporary diagnostic endpoint - REMOVE after debugging."""
    try:
        from agent_system.core.search_provider import get_search
        results = get_search().search(q)
        return {
            "query": q,
            "count": len(results),
            "results": [
                {"score": r["score"], "domain": r["domain"], "title": r["title"][:80]}
                for r in results
            ]
        }
    except Exception as e:
        return {"error": str(e), "type": type(e).__name__}
