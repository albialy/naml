export interface RoleCard {
  specialization: string;
  when_to_use: string;
  instructions: string;
  expected_input: string;
  expected_output: string;
}

export const emptyRoleCard = (): RoleCard => ({
  specialization: "", when_to_use: "", instructions: "", expected_input: "", expected_output: "",
});

const fields: {key: keyof RoleCard; label: string; limit: number; hint: string}[] = [
  {key: "specialization", label: "التخصص", limit: 300, hint: "ما العمل الذي يجيده هذا الدور؟"},
  {key: "when_to_use", label: "متى يُستخدم؟", limit: 500, hint: "متى يختاره المدير؟ ومتى لا يحتاج إليه؟"},
  {key: "expected_input", label: "المدخلات المطلوبة", limit: 500, hint: "المعلومات أو نتائج الأدوار الأخرى التي يحتاجها"},
  {key: "expected_output", label: "النتيجة المطلوبة", limit: 700, hint: "شكل التسليم ومعايير اكتماله"},
  {key: "instructions", label: "تعليمات التنفيذ", limit: 2000, hint: "تعليمات محددة يطبقها الوكيل عند إسناد العمل إليه"},
];

const templates: Record<string, RoleCard> = {
  "مطور برمجيات": {
    specialization: "كتابة الشيفرة وتحليل المشكلات البرمجية",
    when_to_use: "عندما يتطلب الطلب كتابة شيفرة أو إصلاح خطأ. لا يُستخدم لمجرد سؤال معلوماتي بسيط.",
    expected_input: "المتطلبات والشيفرة المتاحة ورسالة الخطأ والقيود التقنية إن وجدت",
    expected_output: "شيفرة أو تعديل مقترح واضح، وشرح مختصر وطريقة للتحقق، مع تمييز ما لم يُختبر",
    instructions: "استخدم الملفات والمعلومات المتاحة فقط. اذكر النواقص المؤثرة. اقترح أقل تعديل يحقق المطلوب، ولا تدّع تشغيل الشيفرة أو تعديل ملفات فعلية دون أداة ونتيجة تؤكد ذلك.",
  },
  "مراجع": {
    specialization: "مراجعة صحة الإجابات والشيفرة والمتطلبات",
    when_to_use: "عند الحاجة إلى التحقق من نتيجة دور آخر أو اكتشاف أخطاء مؤثرة",
    expected_input: "طلب المستخدم والنتيجة المطلوب مراجعتها وأدلتها أو الشيفرة المتاحة",
    expected_output: "أخطاء مؤثرة مرتبة حسب الأهمية مع تصحيح مقترح، أو توضيح عدم وجود خطأ جوهري",
    instructions: "راجع النتيجة مقابل المتطلبات والأدلة. لا تصنع اعتراضات شكلية، ولا تدّع إجراء اختبارات لم تُنفذ. التزم بمخطط المراجعة إن طلبته مرحلة التنفيذ.",
  },
  "باحث": {
    specialization: "بحث المصادر وتحليل الأدلة",
    when_to_use: "للأسئلة التي تتطلب معلومات حديثة أو مصادر، عندما يتيح مسار المهمة البحث",
    expected_input: "سؤال بحث محدد والسياق والمصادر التي يوفرها النظام",
    expected_output: "نتائج موجزة مع روابط المصادر وحدود الأدلة والفجوات",
    instructions: "استند إلى الأدلة المتاحة فقط. اربط الادعاءات بمصادرها. لا تختلق مصادر أو تدّع قراءة صفحات كاملة عند توفر مقتطفات فقط.",
  },
};

export function RoleCardEditor({value, onChange}: {value: RoleCard; onChange: (v: RoleCard) => void}) {
  const card = {...emptyRoleCard(), ...value};
  return <details open className="rounded-xl border border-[#cbddea] bg-white/70 p-4">
    <summary className="cursor-pointer font-bold text-sm">بطاقة الدور</summary>
    <p className="text-xs muted leading-6 mt-3">الوصف يساعد المدير على اختيار الدور. التعليمات تُرسل إليه عند التنفيذ. إضافة دور لا تجعله مرحلة إلزامية، ولا تمنحه أدوات أو قدرات جديدة.</p>
    <div className="flex flex-wrap gap-2 my-3" aria-label="قوالب بطاقة الدور">
      {Object.entries(templates).map(([label, template]) => <button key={label} type="button" className="rounded-lg border border-[#cbddea] px-3 py-2 text-xs hover:bg-sky-50" onClick={() => onChange({...template})}>قالب {label}</button>)}
    </div>
    <div className="grid gap-4 md:grid-cols-2">
      {fields.map(({key, label, limit, hint}) => <label key={key} className={"block text-sm space-y-2 min-w-0 " + (key === "instructions" ? "md:col-span-2" : "")}>
        <span>{label}</span>
        <textarea aria-label={label} className="glass-input w-full !h-auto min-h-24 resize-y" rows={key === "instructions" ? 4 : 3} maxLength={limit} value={card[key]} placeholder={hint} onChange={e => onChange({...card, [key]: e.target.value})}/>
        <span className="block text-xs muted" dir="ltr">{card[key].length} / {limit}</span>
      </label>)}
    </div>
    <p className="text-xs muted mt-3">تُحفظ البطاقة مع زر حفظ إعدادات هذا الدور. الاسم الواضح والوصف يساعدان التوجيه؛ الاختيار الفعلي للنموذج قد يخطئ.</p>
  </details>;
}

export function RoleCardSummary({value}: {value?: RoleCard}) {
  if (!value || !Object.values(value).some(Boolean)) return <p className="text-xs muted mt-2">لم تُحدد بطاقة لهذا الدور. أضف تخصصه من «تعديل».</p>;
  return <details className="mt-3 text-sm max-w-3xl">
    <summary className="cursor-pointer text-sky-800 break-words">{value.specialization || "عرض بطاقة الدور"}</summary>
    <dl className="mt-3 space-y-3 text-xs leading-6">
      {fields.map(({key, label}) => value[key] && <div key={key}><dt className="font-bold">{label}</dt><dd className="muted whitespace-pre-wrap break-words">{value[key]}</dd></div>)}
    </dl>
  </details>;
}
