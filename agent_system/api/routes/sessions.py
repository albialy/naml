from fastapi import APIRouter, HTTPException, Depends
from agent_system.core.auth.models import User, UserRole
from agent_system.core.auth.middleware import get_current_user
from agent_system.core.storage import get_storage

router = APIRouter()

@router.get("/api/sessions")
async def list_sessions(current_user: User = Depends(get_current_user)):
    sessions = []
    for data in get_storage().list_sessions():
        if current_user.role != UserRole.SUPER_ADMIN and data.get("user_id") != current_user.id:
            continue
        sessions.append({
            "session_id": data.get("session_id"),
            "task_original": data.get("task_original"),
            "status": data.get("status"),
            "created_at": data.get("created_at"),
            "confidence_final": data.get("confidence_final")
        })
    return sessions

@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str, current_user: User = Depends(get_current_user)):
    data = get_storage().get_session(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail={"error": "Session not found", "code": "NOT_FOUND"})
    if current_user.role != UserRole.SUPER_ADMIN and data.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail={"error": "Access denied", "code": "FORBIDDEN"})
    return data
