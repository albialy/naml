from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from agent_system.core.auth.models import User
from agent_system.core.auth.middleware import require_super_admin
from agent_system.core.settings_manager import settings_manager, AVAILABLE_MODELS
from agent_system.core.connectors.groq_connector import GroqConnector
from agent_system.core.connectors.openrouter_connector import OpenRouterConnector
import time

router = APIRouter()

class ModelConfigModel(BaseModel):
    provider: str
    model: str
    temperature: float
    max_tokens: int

class AddWorkerModel(BaseModel):
    name: str
    provider: str
    model: str
    temperature: float = 0.5
    max_tokens: int = 2048
    description: Optional[str] = None

class SystemSettingsModel(BaseModel):
    max_agents_per_task: Optional[int] = None
    max_debate_rounds: Optional[int] = None
    allow_user_registration: Optional[bool] = None
    default_language: Optional[str] = None
    session_retention_days: Optional[int] = None

@router.get("/api/settings")
async def get_settings(current_user: User = Depends(require_super_admin)):
    return settings_manager.get_settings()

@router.put("/api/settings/director")
async def update_director(config: ModelConfigModel, current_user: User = Depends(require_super_admin)):
    success = settings_manager.update_director(config.dict(), current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail={"error": "Invalid model configuration", "code": "INVALID_CONFIG"})
    return {"success": True}

@router.put("/api/settings/workers/{worker_type}")
async def update_worker(worker_type: str, config: ModelConfigModel, current_user: User = Depends(require_super_admin)):
    success = settings_manager.update_worker(worker_type, config.dict(), current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail={"error": "Invalid worker configuration or worker not found", "code": "INVALID_CONFIG"})
    return {"success": True}

@router.post("/api/settings/workers")
async def add_worker(config: AddWorkerModel, current_user: User = Depends(require_super_admin)):
    worker_conf = {
        "provider": config.provider,
        "model": config.model,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "description": config.description
    }
    success = settings_manager.add_worker(config.name, worker_conf, current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail={"error": "Invalid worker configuration or worker already exists", "code": "INVALID_CONFIG"})
    return {"success": True}

@router.delete("/api/settings/workers/{worker_type}")
async def delete_worker(worker_type: str, current_user: User = Depends(require_super_admin)):
    success = settings_manager.remove_worker(worker_type, current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail={"error": "Worker not found or cannot delete last remaining worker", "code": "DELETE_FAILED"})
    return {"success": True}

@router.put("/api/settings/system")
async def update_system(config: SystemSettingsModel, current_user: User = Depends(require_super_admin)):
    updates = {k: v for k, v in config.dict().items() if v is not None}
    success = settings_manager.update_system(updates, current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail={"error": "Update failed", "code": "UPDATE_FAILED"})
    return {"success": True}

@router.get("/api/settings/available-models")
async def get_available_models(current_user: User = Depends(require_super_admin)):
    return AVAILABLE_MODELS

@router.get("/api/settings/test-connection/{provider}")
async def test_connection(provider: str, current_user: User = Depends(require_super_admin)):
    if provider not in ["groq", "openrouter"]:
        raise HTTPException(status_code=400, detail={"error": "Unknown provider", "code": "UNKNOWN_PROVIDER"})
        
    connector = None
    if provider == "groq":
        connector = GroqConnector()
    else:
        connector = OpenRouterConnector()
        
    start_time = time.time()
    connected = connector.validate_connection()
    latency_ms = int((time.time() - start_time) * 1000)
    
    return {"connected": connected, "latency_ms": latency_ms}

@router.post("/api/settings/restore/{history_index}")
async def restore_settings(history_index: int, current_user: User = Depends(require_super_admin)):
    success = settings_manager.restore_history(history_index, current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail={"error": "Restore failed or invalid history index", "code": "RESTORE_FAILED"})
    return {"success": True}
