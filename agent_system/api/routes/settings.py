from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from agent_system.core.auth.models import User
from agent_system.core.auth.middleware import require_super_admin
from agent_system.core.settings_manager import settings_manager, AVAILABLE_MODELS
from agent_system.core.connectors.groq_connector import GroqConnector
from agent_system.core.connectors.openrouter_connector import OpenRouterConnector
import time
import os
from agent_system.core.execution_policy import ExecutionPolicy
from agent_system.core.role_cards import RoleCard, card_for

router = APIRouter()

class ModelConfigModel(BaseModel):
    provider: str
    model: str
    temperature: float
    max_tokens: int
    role_card: Optional[RoleCard] = None

class AddWorkerModel(BaseModel):
    name: str
    provider: str
    model: str
    temperature: float = 0.5
    max_tokens: int = 2048
    description: Optional[str] = None
    role_card: Optional[RoleCard] = None

class SystemSettingsModel(BaseModel):
    max_agents_per_task: Optional[int] = None
    max_debate_rounds: Optional[int] = None
    allow_user_registration: Optional[bool] = None
    default_language: Optional[str] = None
    session_retention_days: Optional[int] = None

@router.get("/api/settings")
async def get_settings(current_user: User = Depends(require_super_admin)):
    settings = settings_manager.get_settings()
    settings["director"]["role_card"] = card_for(settings["director"], "director")
    for role, config in settings.get("workers", {}).items():
        config["role_card"] = card_for(config, role)
    return {**settings, "source_status": {"groq": bool(os.getenv("GROQ_API_KEY")),
                                          "openrouter": bool(os.getenv("OPENROUTER_API_KEY"))}}

@router.put("/api/settings/execution")
def update_execution(config: ExecutionPolicy, current_user: User = Depends(require_super_admin)):
    if not settings_manager.update_execution(config.model_dump(), current_user.id):
        raise HTTPException(400, detail="اختر أدوارًا موجودة في إعدادات النماذج")
    return {"success": True}

@router.put("/api/settings/director")
async def update_director(config: ModelConfigModel, current_user: User = Depends(require_super_admin)):
    success = settings_manager.update_director(config.model_dump(exclude_none=True), current_user.id)
    if not success:
        raise HTTPException(status_code=400, detail={"error": "Invalid model configuration", "code": "INVALID_CONFIG"})
    return {"success": True}

@router.put("/api/settings/workers/{worker_type}")
async def update_worker(worker_type: str, config: ModelConfigModel, current_user: User = Depends(require_super_admin)):
    success = settings_manager.update_worker(worker_type, config.model_dump(exclude_none=True), current_user.id)
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
    if config.role_card is not None:
        worker_conf["role_card"] = config.role_card.model_dump()
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

@router.get('/api/settings/catalog/{provider}')
def live_catalog(provider:str,current_user:User=Depends(require_super_admin)):
    if provider not in ('groq','openrouter'):raise HTTPException(400,detail='مزود غير معروف')
    from agent_system.core.model_catalog import catalog
    try:return {'provider':provider,'models':catalog(provider)}
    except ValueError as e:raise HTTPException(400,detail=str(e))

@router.post('/api/settings/test-model')
def test_model(config:ModelConfigModel,current_user:User=Depends(require_super_admin)):
    if not settings_manager._validate_model_config(config.model_dump()):raise HTTPException(400,detail='إعدادات غير صالحة')
    from agent_system.core.director import Director
    from agent_system.core.worker import _is_error_response
    connector=Director()._connector_for(config.model_dump())
    answer=connector.complete('Reply only OK.','Connectivity test',0,64)
    if _is_error_response(answer):raise HTTPException(400,detail=answer)
    return {'success':True,'provider':config.provider,'model':config.model}

@router.get('/api/settings/retired-models')
def retired_models(current_user:User=Depends(require_super_admin)):
    from agent_system.core.model_catalog import replacements
    return replacements(settings_manager.get_settings())

@router.post('/api/settings/repair-models')
def repair_models(current_user:User=Depends(require_super_admin)):
    from agent_system.core.model_catalog import replacements, RETIRED_GROQ
    def repair(settings):
        for config in [settings['director']]+list(settings.get('workers',{}).values()):
            if config.get('provider')=='groq' and config.get('model') in RETIRED_GROQ:config['model']=RETIRED_GROQ[config['model']]
    changes=replacements(settings_manager.get_settings())
    settings_manager._change(current_user.id,'retired_models_repair',repair)
    return {'changes':changes}
