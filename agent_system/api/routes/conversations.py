from fastapi import APIRouter, Depends, HTTPException
from agent_system.core.auth.middleware import get_current_user
from agent_system.core.auth.models import User, UserRole
from agent_system.core.database import get_database

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
    return conversation
