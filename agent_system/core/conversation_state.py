"""Conversation branches live in the existing transactional document store."""
import copy
import uuid

ACTIVE = ("pending", "running", "synthesizing")
TERMINAL = ("complete", "failed", "cancelled")
FIELDS = ("messages", "active_session_id", "status")


def initialize(conversation):
    conversation.setdefault("revision", 0)
    conversation.setdefault("branch_id", "main")
    conversation.setdefault("branches", {})
    if conversation["branch_id"] not in conversation["branches"]:
        conversation["branches"][conversation["branch_id"]] = {
            "id": conversation["branch_id"], "label": "المسار الأصلي",
            "created_at": conversation["created_at"], "parent_id": None,
        }
    stash(conversation)


def stash(conversation):
    branch = conversation["branches"][conversation["branch_id"]]
    for key in FIELDS:
        branch[key] = copy.deepcopy(conversation.get(key, [] if key == "messages" else None))


def activate(conversation, branch_id):
    branch = conversation["branches"].get(branch_id)
    if not branch:
        raise KeyError("المسار غير موجود")
    for key in FIELDS:
        conversation[key] = copy.deepcopy(branch.get(key, [] if key == "messages" else None))
    conversation["branch_id"] = branch_id


def fork(conversation, message_id, action, created_at):
    messages = conversation["messages"]
    index = next((i for i, m in enumerate(messages) if m["id"] == message_id), None)
    if index is None:
        raise KeyError("الرسالة غير موجودة في هذا المسار")
    target = messages[index]
    if target["role"] != ("user" if action == "edit" else "assistant"):
        raise ValueError("نوع الرسالة لا يناسب هذا الإجراء")
    if action == "retry":
        index = next((i for i in range(index - 1, -1, -1)
                      if messages[i]["role"] == "user" and messages[i]["session_id"] == target["session_id"]), None)
        if index is None:
            raise ValueError("لا توجد رسالة مستخدم مرتبطة بهذا الرد")
        target = messages[index]
    if len(conversation["branches"]) >= 30:
        raise ValueError("وصلت المحادثة إلى حد 30 مسارًا. ابدأ محادثة جديدة لمزيد من المسارات.")
    stash(conversation)
    bid = uuid.uuid4().hex
    conversation["branches"][bid] = {
        "id": bid, "label": ("تعديل" if action == "edit" else "إعادة رد") + f" {len(conversation['branches'])}",
        "created_at": created_at, "parent_id": conversation["branch_id"],
        "fork_message_id": message_id, "messages": copy.deepcopy(messages[:index]),
        "status": "complete", "active_session_id": None,
    }
    activate(conversation, bid)
    return target


def public(conversation, summary=False):
    if conversation is None:
        return None
    result = copy.deepcopy(conversation)
    initialize(result)
    result["branches"] = [{k: v for k, v in b.items() if k not in FIELDS}
                          | {"message_count": len(b.get("messages", []))}
                          for b in result["branches"].values()]
    result["message_count"] = len(result["messages"])
    if summary:
        result.pop("messages", None)
        result.pop("branches", None)
    return result
