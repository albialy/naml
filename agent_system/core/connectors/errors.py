def failure(provider, model, status=None, code=""):
    if status in (401,403):
        reason="تعذر الوصول: راجع المفتاح وصلاحية النموذج لحسابك"
    elif status==429:
        reason="تجاوز حد الاستدعاءات أو الحصة المتاحة؛ أعد المحاولة لاحقًا"
    elif status==404 or code in ("model_not_found","model_decommissioned"):
        reason="النموذج غير متاح؛ حدّث اختياره من الإعدادات"
    elif status in (400,413,422):
        reason="رفض المزود الطلب؛ راجع دعم النموذج وحجم السياق وإعدادات الرد"
    else:
        reason="تعذر الاتصال بالمزود أو الحصول على رد صالح"
    return f"Error: {provider} / {model}: {reason} (HTTP {status or '-'}; {code[:80]})"


def error_code(body):
    if isinstance(body,dict):
        error=body.get("error",body)
        if isinstance(error,dict):return str(error.get("code", ""))
    return ""
