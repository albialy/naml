from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from agent_system.core.auth.middleware import get_current_user
from agent_system.core.auth.models import User, UserRole
from agent_system.core.database import get_database, ConversationBusy

from agent_system.api.presentation import conversation as present_conversation

router = APIRouter(prefix="/api/conversations")


@router.get("")
async def list_conversations(current_user: User = Depends(get_current_user)):
    return get_database().list_conversations(current_user.id)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str, current_user: User = Depends(get_current_user)):
    conversation = get_database().get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="المحادثة غير موجودة")
    if conversation["user_id"] != current_user.id and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="لا يمكنك الوصول لهذه المحادثة")
    return present_conversation(conversation, current_user)


class StopRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    branch_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=0)


class BranchRequest(BaseModel):
    branch_id: str = Field(min_length=1, max_length=100)
    revision: int = Field(ge=0)


def change(action):
    try:
        return action()
    except KeyError:
        raise HTTPException(404, "المحادثة أو المسار غير موجود")
    except PermissionError:
        raise HTTPException(403, "لا يمكنك تعديل محادثة مستخدم آخر")
    except ConversationBusy as exc:
        raise HTTPException(409, str(exc))


@router.post("/{conversation_id}/stop")
def stop(conversation_id: str, body: StopRequest, user: User = Depends(get_current_user)):
    return present_conversation(change(lambda: get_database().cancel_turn(conversation_id, user.id, body.session_id, body.revision, body.branch_id)), user)


@router.post("/{conversation_id}/branch")
def branch(conversation_id: str, body: BranchRequest, user: User = Depends(get_current_user)):
    return present_conversation(change(lambda: get_database().switch_branch(conversation_id, user.id, body.branch_id, body.revision)), user)
