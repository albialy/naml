import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { Button } from "./ui/Button";
import { apiError } from "../types/project";

interface Policy {
  router_role: string; single_role: string; research_role: string; critic_role: string; fallback_role: string;
  max_model_calls: number; time_budget_seconds: number; provider_concurrency: number; parallel_workers: number; router_max_tokens: number;
}
interface Model {provider: string; model: string}
const roleLabels: Record<string, string> = {director: "المدير", fast: "السريع", deep_analytical: "التحليل", creative: "الإبداع", critic: "المراجع"};

export function ExecutionSettings({settings}: {settings: {execution: Policy; director: Model; workers: Record<string, Model>; source_status?: Record<string, boolean>}}) {
  const [value, setValue] = useState(settings.execution);
  useEffect(() => setValue(settings.execution), [settings.execution]);
  const cache = useQueryClient();
  const save = useMutation({
    mutationFn: () => apiClient.put("/settings/execution", value),
    onSuccess: () => cache.invalidateQueries({queryKey: ["settings"]}),
  });
  const roles = {director: settings.director, ...settings.workers};
  const fields: [keyof Policy, string][] = [
    ["router_role", "التوجيه والإجابة السريعة"], ["single_role", "المهام بنموذج واحد"],
    ["research_role", "البحث بالمصادر"], ["critic_role", "مراجعة النتائج"], ["fallback_role", "البديل عند عطل مؤقت"],
  ];
  const limits: [keyof Policy, string, number, number][] = [
    ["max_model_calls", "سقف الاستدعاءات لكل طلب", 4, 40],
    ["time_budget_seconds", "مهلة بدء الاستدعاءات (ثانية)", 15, 600],
    ["parallel_workers", "وكلاء يعملون بالتوازي", 1, 6],
    ["provider_concurrency", "استدعاءات متزامنة لكل مصدر", 1, 8],
    ["router_max_tokens", "حد إخراج التوجيه السريع (توكن)", 256, 2048],
  ];
  return <form className="glass rounded-3xl p-5 md:p-7 space-y-5" onSubmit={e => {e.preventDefault(); save.mutate();}}>
    <div><h2 className="text-xl font-bold mb-2">الاستجابة وتوزيع العمل</h2>
      <p className="text-sm muted leading-7">السؤال البسيط يأخذ إجابة مباشرة. تُستخدم بقية الأدوار عندما يحتاج الطلب إليها. يمكنك تغيير مصدر كل دور من إعدادات النماذج أدناه.</p>
    </div>
    <div className="flex gap-3 flex-wrap text-sm">
      {Object.entries(settings.source_status || {}).map(([provider, configured]) => <span key={provider} className="rounded-xl bg-white/80 px-3 py-2">{provider}: {configured ? "المفتاح مُعدّ" : "يحتاج مفتاحًا على الخادم"}</span>)}
    </div>
    <div className="grid md:grid-cols-2 gap-4">
      {fields.map(([key, label]) => <label key={key} className="text-sm space-y-2"><span>{label}</span>
        <select aria-label={label} className="glass-input" value={value[key]} onChange={e => setValue({...value, [key]: e.target.value})}>
          {key === "fallback_role" && <option value="">بدون تحويل تلقائي</option>}
          {Object.entries(roles).map(([name, model]) => <option key={name} value={name}>{roleLabels[name] || name} · {model.provider} / {model.model}</option>)}
        </select>
      </label>)}
    </div>
    <p className="text-xs muted leading-6">البديل المفعّل قد يستهلك رصيدًا لدى مصدر آخر. يُستخدم مرة واحدة عند عطل مؤقت أو بلوغ حد الاستخدام، ضمن ميزانية المهمة. حدود المصدر مشتركة بين مفاتيحه؛ إضافة مفتاح لا تضاعف الحصة.</p>
    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {limits.map(([key, label, min, max]) => <label key={key} className="text-sm space-y-2"><span>{label}</span>
        <input aria-label={label} className="glass-input" required type="number" min={min} max={max} value={value[key]} onChange={e => setValue({...value, [key]: Number(e.target.value)})} />
      </label>)}
    </div>
    <Button type="submit" isLoading={save.isPending}>حفظ طريقة التنفيذ</Button>
    {save.isSuccess && <p role="status" className="text-sm text-emerald-700">تم حفظ طريقة التنفيذ.</p>}
    {save.error && <p role="alert" className="text-sm text-red-700">{apiError(save.error)}</p>}
  </form>;
}
