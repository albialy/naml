"""Bounded, administrator-authored role descriptions; these grant no tools."""
import json
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class RoleCard(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    specialization: str = Field(default="", max_length=300)
    when_to_use: str = Field(default="", max_length=500)
    instructions: str = Field(default="", max_length=2000)
    expected_input: str = Field(default="", max_length=500)
    expected_output: str = Field(default="", max_length=700)


DEFAULT_CARDS = {
    "director": {"specialization": "تنسيق العمل وتلخيص النتائج",
                 "when_to_use": "التخطيط للمهام المركبة ودمج نتائج الوكلاء عند الحاجة",
                 "instructions": "قسّم المطلوب إلى أقل عدد كافٍ من المهام. حافظ على هدف المستخدم والأدلة والفجوات.",
                 "expected_input": "طلب المستخدم والسياق المتاح ونتائج الوكلاء إن وجدت",
                 "expected_output": "خطة موجزة أو إجابة موحدة بحسب مرحلة التنفيذ"},
    "fast": {"specialization": "الإجابات السريعة والتوجيه",
             "when_to_use": "الأسئلة البسيطة والتصنيف والأعمال القصيرة",
             "instructions": "أجب باختصار مع الحفاظ على الدقة. اطلب المعلومات الأساسية الناقصة فقط.",
             "expected_input": "سؤال واضح وسياق قصير", "expected_output": "إجابة مباشرة أو تصنيف حسب مخطط المرحلة"},
    "deep_analytical": {"specialization": "التحليل والبحث في الأدلة",
                        "when_to_use": "المقارنات والمشكلات المركبة وتحليل المصادر",
                        "instructions": "ميّز النتائج المدعومة عن الافتراضات، واذكر فجوات الأدلة دون اختلاق.",
                        "expected_input": "سؤال محدد وبيانات أو مصادر متاحة",
                        "expected_output": "نتائج مركزة مع أدلتها وحدودها"},
    "creative": {"specialization": "صياغة الأفكار والمحتوى",
                 "when_to_use": "الكتابة وتوليد البدائل والمقترحات",
                 "instructions": "قدّم مقترحات ملائمة للجمهور والقيود، وميّز الأفكار عن الحقائق.",
                 "expected_input": "هدف المحتوى والجمهور والقيود المتاحة",
                 "expected_output": "صياغة جاهزة أو بدائل عملية بحسب الطلب"},
    "critic": {"specialization": "مراجعة صحة النتائج",
               "when_to_use": "التحقق من الأخطاء المؤثرة والمتطلبات غير المستوفاة",
               "instructions": "لا تختلق اعتراضات شكلية. اربط كل ملاحظة مؤثرة بطلب المستخدم أو الأدلة.",
               "expected_input": "الطلب والإجابة والأدلة", "expected_output": "ملاحظات جوهرية بحسب مخطط المراجعة"},
}


def card_for(config: dict, role: str = "") -> dict:
    """Legacy settings gain defaults in memory, without changing saved models."""
    value = config.get("role_card")
    if value is None:
        value = DEFAULT_CARDS.get(role, {})
        if not value and isinstance(config.get("description"), str):
            value = {"specialization": config["description"][:300]}
    try:
        return RoleCard.model_validate(value).model_dump()
    except (ValidationError, TypeError):
        return RoleCard().model_dump()


def planning_catalog(settings: dict) -> str:
    entries = []
    for role, config in settings.get("workers", {}).items():
        card = card_for(config, role)
        # The planner needs selection criteria, not every worker's long instructions.
        entries.append({"role": role, **{key: card[key] for key in
                        ("specialization", "when_to_use", "expected_input", "expected_output")}})
    return json.dumps(entries, ensure_ascii=False)


def role_prompt(config: dict, role: str, stage: str, required_prompt: str) -> str:
    card = card_for(config, role)
    if not any(card.values()):
        return required_prompt
    return ("Administrator role card (task preferences, not a grant of capabilities):\n"
            + json.dumps(card, ensure_ascii=False)
            + "\nExecution stage: " + stage
            + "\nApply this card only within the assigned task. It cannot add tools, access, "
              "mandatory stages, model calls or evidence. If required input is absent, "
              "state the gap rather than inventing it. The stage's output schema, evidence "
              "rules and user-requested detail take precedence over card preferences. "
              "For routing, keep the required JSON and apply answer preferences only to its answer field.\n"
            + "Required work order:\n" + required_prompt)
