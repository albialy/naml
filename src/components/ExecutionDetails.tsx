import { ExecutionInfo } from "../types";

const routes: Record<string, string> = {direct: "إجابة مباشرة", single: "نموذج واحد", clarify: "استيضاح", research: "بحث بالمصادر", team: "عمل جماعي"};
export function ExecutionDetails({execution: info}: {execution?: ExecutionInfo}) {
  if (!info?.route) return null;
  return <details className="text-xs text-slate-500 max-w-full">
    <summary className="cursor-pointer">{routes[info.route] || info.route} · تفاصيل التنفيذ</summary>
    <div className="mt-3 space-y-2 break-words">
      {info.reason && <p>{info.reason}</p>}
      {info.model_calls !== undefined && <p>{info.model_calls} استدعاء · {((info.duration_ms || 0) / 1000).toFixed(1)} ثانية</p>}
      {info.reported_tokens !== undefined && <p>التوكن المبلغ عنه: {info.reported_tokens.toLocaleString("ar")}{!info.usage_complete && " (بيانات بعض الاستدعاءات غير متاحة)"}</p>}
      {info.calls?.map((call, i) => <p key={i} dir="auto">{call.provider} / {call.model} · {call.status === "complete" ? "اكتمل" : "تعذر"}{call.fallback && " · مصدر بديل"}</p>)}
    </div>
  </details>;
}
