from fastapi import APIRouter, HTTPException, Depends
import os
import json
from agent_system.core.auth.models import User, UserRole
from agent_system.core.auth.middleware import get_current_user

router = APIRouter()

@router.get("/api/sessions")
async def list_sessions(current_user: User = Depends(get_current_user)):
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
                    
                    if current_user.role != UserRole.SUPER_ADMIN and data.get("user_id") != current_user.id:
                        continue
                        
                    sessions.append({
                        "session_id": data.get("session_id"),
                        "task_original": data.get("task_original"),
                        "status": data.get("status"),
                        "created_at": data.get("created_at"),
                        "confidence_final": data.get("confidence_final")
                    })
            except Exception:
                continue
                
    return sessions

@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str, current_user: User = Depends(get_current_user)):
    storage_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'storage', 'sessions')
    file_path = os.path.join(storage_dir, f"{session_id}.json")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail={"error": "Session not found", "code": "NOT_FOUND"})
        
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if current_user.role != UserRole.SUPER_ADMIN and data.get("user_id") != current_user.id:
                raise HTTPException(status_code=403, detail={"error": "Access denied", "code": "FORBIDDEN"})
            return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail={"error": str(e), "code": "INTERNAL_ERROR"})
