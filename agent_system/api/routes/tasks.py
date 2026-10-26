from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Literal
import datetime
from agent_system.core.memory import SharedMemory
from agent_system.core.director import Director
from agent_system.core.auth.models import User, UserRole
from agent_system.core.auth.middleware import get_current_user, require_super_admin
from agent_system.core.auth.manager import auth_manager
from agent_system.core.storage import get_storage
from agent_system.core.database import get_database, ConversationBusy

router = APIRouter()
director = Director()

class TaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=20000)
    conversation_id: Optional[str] = None
    project_id: Optional[str] = None
    response_detail: Literal["auto", "brief", "detailed"] = "auto"

def run_task_background(task: str, memory: SharedMemory):
    try:
        runner = Director(settings_override=memory.run_settings) if memory.run_settings else director
        runner.run(task, memory)
    except Exception as e:
        memory.status = "failed"
        memory.final_synthesis = str(e)
        memory.save_to_file()

    if (memory.status == "complete" and memory.project_id
            and memory.execution.get("route") not in ("direct", "clarify")
            and memory.execution.get("project_relevant") is True):
        from agent_system.core.projects import request_proposal
        try:
            runtime = getattr(memory, "_runtime", None)
            if runtime:
                runtime.check()
            request_proposal(memory.project_id, memory.user_id, automatic=True, runtime=runtime)
        except Exception:
            pass  # A board proposal must never turn a saved successful reply into a failure.
        finally:
            if getattr(memory, "_runtime", None):
                memory.execution.update(memory._runtime.summary())
                memory.save_to_file()

def _check_user_access(session_data: dict, current_user: User):
    if current_user.role == UserRole.SUPER_ADMIN:
        return
    if session_data.get("user_id") != current_user.id:
        raise HTTPException(status_code=403, detail={"error": "Access denied", "code": "FORBIDDEN"})

def _check_session_limit(current_user: User):
    if current_user.role == UserRole.SUPER_ADMIN or current_user.session_limit == 0:
        return
    today = datetime.datetime.now().date().isoformat()
    count = 0
    for data in get_storage().list_sessions():
        if data.get("user_id") == current_user.id and data.get("created_at", "").startswith(today):
            count += 1
    if count >= current_user.session_limit:
        raise HTTPException(status_code=429, detail={"error": "Session limit exceeded for today", "code": "SESSION_LIMIT_EXCEEDED"})

@router.post("/api/task")
async def create_task(request: TaskRequest, background_tasks: BackgroundTasks, current_user: User = Depends(get_current_user)):
    if not request.task.strip():
        raise HTTPException(status_code=400, detail={"error": "Task cannot be empty", "code": "INVALID_REQUEST"})

    _check_session_limit(current_user)

    memory = SharedMemory(task_original=request.task, user_id=current_user.id)
    memory.response_detail = request.response_detail
    try:
        saved = get_database().start_turn(memory.to_dict(), request.conversation_id, request.project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="المحادثة غير موجودة")
    except PermissionError:
        raise HTTPException(status_code=403, detail="لا يمكنك متابعة محادثة مستخدم آخر")
    except ConversationBusy:
        raise HTTPException(status_code=409, detail="انتظر اكتمال الرد الحالي قبل إرسال رسالة جديدة")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    memory.conversation_id = saved["conversation_id"]
    memory.chat_history = saved["chat_history"]
    memory.project_id = saved.get("project_id")
    memory.project_context = saved.get("project_context", "")
    from agent_system.core.projects import model_settings, get_project
    project = get_project(memory.project_id, current_user.id) if memory.project_id else None
    memory.run_settings = model_settings(current_user.id, project)
    memory.save_to_file()

    auth_manager._log_activity("SUBMIT_TASK", current_user.id, memory.session_id)

    background_tasks.add_task(run_task_background, request.task, memory)

    return {"session_id": memory.session_id, "conversation_id": memory.conversation_id, "status": "started"}

@router.get("/api/task/{session_id}/status")
async def get_task_status(session_id: str, current_user: User = Depends(get_current_user)):
    data = get_storage().get_session(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail={"error": "Session not found", "code": "NOT_FOUND"})
    _check_user_access(data, current_user)
    return data

@router.get("/api/task/{session_id}/result")
async def get_task_result(session_id: str, current_user: User = Depends(get_current_user)):
    data = get_storage().get_session(session_id)
    if data is None:
        raise HTTPException(status_code=404, detail={"error": "Session not found", "code": "NOT_FOUND"})
    _check_user_access(data, current_user)

    if data.get("status") != "complete" and data.get("status") != "failed":
        raise HTTPException(status_code=400, detail={"error": "Task not complete yet", "code": "NOT_COMPLETE"})

    return {
        "final_synthesis": data.get("final_synthesis"),
        "confidence_final": data.get("confidence_final"),
        "stress_test_results": data.get("stress_test_results"),
        "status": data.get("status")
    }

@router.delete("/api/task/{session_id}")
async def delete_task(session_id: str, current_user: User = Depends(require_super_admin)):
    try:
        deleted = get_storage().delete_session(session_id)
    except ConversationBusy:
        raise HTTPException(status_code=409, detail="لا يمكن حذف تحليل جارٍ")
    if deleted:
        auth_manager._log_activity("DELETE_TASK", current_user.id, session_id)
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail={"error": "Session not found", "code": "NOT_FOUND"})
