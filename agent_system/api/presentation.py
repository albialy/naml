"""Customer response contracts. Technical records stay server-side."""
from agent_system.core.auth.models import UserRole

FAILURE = "تعذر إكمال الطلب. يمكنك إعادة المحاولة."
SESSION_FIELDS = ("session_id", "user_id", "conversation_id", "project_id", "branch_id",
                  "task_original", "status", "created_at", "completed_at", "response_detail")
CONVERSATION_FIELDS = ("conversation_id", "user_id", "project_id", "title", "status",
                       "created_at", "updated_at", "active_session_id", "message_count",
                       "revision", "branch_id")
MESSAGE_FIELDS = ("id", "role", "content", "session_id", "created_at", "status")
SAFE_WARNINGS = {
    "التحليل جزئي: تعذر إكمال بعض الجوانب؛ لا تعتبرها نتائج مؤكدة.",
    "تعذرت مراجعة الصياغة؛ توجد ملاحظات نقد لم تُحسم.",
    "عُدّلت الإجابة بعد مراجعة نقدية واحدة؛ لم تخضع النسخة المعدلة لمراجعة مستقلة أخرى.",
    "لم تكتمل المراجعة النقدية لهذه الإجابة.",
    "قد يكون الرد غير مكتمل. يمكنك طلب المتابعة.",
}

def warnings(data):
    # Preserve limitations that matter to the decision without echoing arbitrary diagnostics.
    return list(dict.fromkeys(w if w in SAFE_WARNINGS else
        "لم يكتمل التحقق من بعض جوانب الإجابة؛ راجع النتائج قبل الاعتماد عليها."
        for w in data.get("warnings", [])))

def admin(user):
    return user.role == UserRole.SUPER_ADMIN

def pick(data, fields):
    return {key: data[key] for key in fields if key in data}

def session(data, user):
    if admin(user):
        return {**data, "simulation_suggested": data.get("execution", {}).get("suggest_simulation") is True}
    result = pick(data, SESSION_FIELDS)
    result["final_synthesis"] = FAILURE if data.get("status") == "failed" else data.get("final_synthesis", "")
    result["simulation_suggested"] = data.get("execution", {}).get("suggest_simulation") is True
    result["warnings"] = warnings(data)
    return result

def message(data):
    result = pick(data, MESSAGE_FIELDS)
    if data.get("role") == "assistant" and data.get("status") == "failed":
        result["content"] = FAILURE
    if data.get("reference"):
        result["reference"] = pick(data["reference"], ("message_id", "text"))
    result["simulation_suggested"] = data.get("execution", {}).get("suggest_simulation") is True
    result["warnings"] = warnings(data)
    return result

def conversation(data, user):
    if admin(user):
        return {**data, "messages": [{**m, "simulation_suggested": m.get("execution", {}).get("suggest_simulation") is True} for m in data.get("messages", [])]}
    result = pick(data, CONVERSATION_FIELDS)
    result["messages"] = [message(m) for m in data.get("messages", [])]
    result["branches"] = [pick(b, ("id", "label", "parent_id", "message_count")) for b in data.get("branches", [])]
    return result
