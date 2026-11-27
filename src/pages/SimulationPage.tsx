import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { Button } from "../components/ui/Button";
import { apiError } from "../types/project";

type Stage = { id: string; name: string; capacity: number; duration: "constant" | "triangular"; minutes: number; minimum: number | null; maximum: number | null };
type Spec = { schema_version: 1; name: string; domain: "production" | "workflow"; unit: "minute"; entity_label: string; horizon_minutes: number; arrival_interval_minutes: number; max_entities: number; stages: Stage[]; assumptions: string; data_source: string };
type Scenario = { id: string; project_id: string | null; parent_id: string | null; input_hash: string; spec: Spec };
type Range = { mean: number; min: number; max: number };
type Summary = { completed: Range; arrived: Range; work_in_progress: Range; throughput_per_hour: Range; mean_flow_minutes: Range | null; trials_with_completions: number };
type Run = { id: string; scenario_id: string; project_id: string | null; status: string; created_at: string; seed: number; repetitions: number; name: string; summary: Summary | null };
type Result = { summary: Summary; stations: { id: string; name: string; utilization: Range; mean_wait_minutes: Range | null; queued_at_end: Range }[]; limitations: string[] };
type RunDetail = Run & { spec: Spec; message: string; result: Result | null; input_hash: string };
const active = ["queued", "running"];
const labels: Record<string, string> = { queued: "بانتظار البدء", running: "جارٍ الحساب", complete: "مكتملة", failed: "تعذر إكمالها", cancelled: "متوقفة" };
const num = (n: number | null | undefined) => n == null ? "—" : n.toLocaleString("ar", { maximumFractionDigits: 2 });
const range = (r: Range | null | undefined) => r ? num(r.mean) + " (" + num(r.min) + " – " + num(r.max) + ")" : "لا توجد وحدات مكتملة";
const uid = () => crypto.randomUUID();
function Numeric({ label, value, set, min = 1, max = 100000, step = "any" }: { label: string; value: number; set: (n: number) => void; min?: number; max?: number; step?: string }) {
  return <label className="block text-sm space-y-2"><span>{label}</span><input required className="glass-input w-full" type="number" min={min} max={max} step={step} value={Number.isFinite(value) ? value : ""} onChange={e => set(e.target.valueAsNumber)} /></label>;
}
export function SimulationPage() {
  const [params] = useSearchParams();
  const projectId = params.get("project_id");
  return <Workspace key={projectId || "personal"} projectId={projectId} />;
}
function Workspace({ projectId }: { projectId: string | null }) {
  const user = useAuthStore(s => s.user);
  const cache = useQueryClient();
  const scope = ["simulation", user?.id];
  const [domain, setDomain] = useState<"production" | "workflow">("production");
  const [spec, setSpec] = useState<Spec | null>(null);
  const [saved, setSaved] = useState<Scenario | null>(null);
  const [parentId, setParentId] = useState<string | null>(null);
  const [reviewed, setReviewed] = useState(false);
  const [repetitions, setRepetitions] = useState(5);
  const [seed, setSeed] = useState(42);
  const [requestKey, setRequestKey] = useState(uid);
  const [selectedRun, setSelectedRun] = useState("");
  const [baseline, setBaseline] = useState("");
  const [candidate, setCandidate] = useState("");
  const templates = useQuery({ queryKey: [...scope, "template", domain], queryFn: async () => (await apiClient.get("/simulation/templates/" + domain)).data as Spec });
  useEffect(() => { if (!spec && templates.data) setSpec(structuredClone(templates.data)); }, [templates.data, spec]);
  const availability = useQuery({ queryKey: [...scope, "status"], queryFn: async () => (await apiClient.get("/simulation/status")).data as { enabled: boolean; available: boolean }, refetchInterval: 10000 });
  const scenarios = useQuery({ queryKey: [...scope, "scenarios"], queryFn: async () => (await apiClient.get("/simulation/scenarios")).data as Scenario[] });
  const runs = useQuery({ queryKey: [...scope, "runs"], queryFn: async () => (await apiClient.get("/simulation/runs")).data as Run[], refetchInterval: 5000 });
  const detail = useQuery({ queryKey: [...scope, "run", selectedRun], queryFn: async () => (await apiClient.get("/simulation/runs/" + selectedRun)).data as RunDetail, enabled: !!selectedRun, refetchInterval: q => active.includes(q.state.data?.status || "") ? 1000 : false });
  const refresh = () => { void cache.invalidateQueries({ queryKey: scope }); };
  const save = useMutation({
    mutationFn: async () => (await apiClient.post("/simulation/scenarios", { spec, project_id: projectId, parent_id: parentId })).data as Scenario,
    onSuccess: data => { setSaved(data); setParentId(data.id); setReviewed(false); refresh(); },
  });
  const start = useMutation({
    mutationFn: async () => (await apiClient.post("/simulation/runs", { scenario_id: saved?.id, repetitions, seed, request_key: requestKey, reviewed })).data as RunDetail,
    onSuccess: data => { setSelectedRun(data.id); setRequestKey(uid()); setReviewed(false); refresh(); },
  });
  const cancel = useMutation({ mutationFn: async (id: string) => apiClient.post("/simulation/runs/" + id + "/cancel"), onSuccess: refresh });
  const update = (next: Spec) => { setSpec(next); setSaved(null); setReviewed(false); setRequestKey(uid()); save.reset(); start.reset(); };
  const stageChange = (i: number, patch: Partial<Stage>) => { if (spec) update({ ...spec, stages: spec.stages.map((s, j) => j === i ? { ...s, ...patch } : s) }); };
  const visibleScenarios = (scenarios.data || []).filter(s => s.project_id === projectId);
  const visibleRuns = (runs.data || []).filter(r => r.project_id === projectId);
  const finished = visibleRuns.filter(r => r.status === "complete" && r.summary);
  const left = finished.find(r => r.id === baseline), right = finished.find(r => r.id === candidate);
  const error = save.error || start.error || cancel.error;
  const busy = save.isPending || start.isPending;
  function openScenario(s: Scenario) {
    setSpec(structuredClone(s.spec)); setSaved(s); setParentId(s.id); setReviewed(false); setRequestKey(uid()); save.reset(); start.reset();
  }
  return <div className="max-w-6xl mx-auto space-y-6">
    {projectId && <Link to={"/projects/" + projectId} className="text-sky-700 text-sm">← العودة للمشروع</Link>}
    <header><p className="text-sm text-sky-700 mb-2">مساحة التجارب</p><h1 className="text-2xl font-bold">ماذا لو غيّرنا طريقة العمل؟</h1><p className="muted mt-3 leading-7">صِف مراحل العملية، راجع افتراضاتك، ثم قارن سيناريوهاتك. لن تبدأ أي تجربة قبل أن تطلب تشغيلها.</p></header>
    <div className="rounded-2xl bg-sky-50 border border-sky-100 p-4 text-sm leading-7">هذه النسخة تحاكي مسارًا متتابعًا، مثل خط إنتاج أو معاملات تمر بعدة أقسام. الأرقام الافتراضية أمثلة وليست توقعات عن مشروعك. كل الأزمنة بالدقائق.</div>
    {!availability.data?.available && <p role="status" className="rounded-xl bg-amber-50 p-4 text-amber-900 text-sm">{availability.isError ? "تعذر معرفة حالة التشغيل." : "تشغيل التجارب غير متاح حاليًا. يمكنك إعداد السيناريو وحفظه."}</p>}
    {(templates.isError || scenarios.isError || runs.isError) && <p role="alert" className="text-red-700">تعذر تحميل بعض البيانات. <button onClick={refresh} className="underline">إعادة المحاولة</button></p>}
    <div className="grid lg:grid-cols-[minmax(0,1fr)_260px] gap-6 items-start">
      <section className="glass rounded-3xl p-4 md:p-6 min-w-0">
        <div className="flex gap-3 flex-wrap mb-5"><h2 className="font-bold text-lg flex-1">إعداد السيناريو</h2>
          <button disabled={busy} className="text-sky-700 text-sm" onClick={() => { setDomain("production"); setSpec(null); setParentId(null); setSaved(null); setReviewed(false); }}>مثال خط إنتاج</button>
          <button disabled={busy} className="text-sky-700 text-sm" onClick={() => { setDomain("workflow"); setSpec(null); setParentId(null); setSaved(null); setReviewed(false); }}>مثال معاملات</button>
        </div>
        {!spec ? <p>جارٍ تجهيز المثال…</p> : <form className="space-y-5" onSubmit={e => { e.preventDefault(); save.mutate(); }}>
          <fieldset disabled={busy} className="space-y-5">
            <label className="block text-sm space-y-2"><span>اسم السيناريو</span><input required maxLength={100} className="glass-input w-full" value={spec.name} onChange={e => update({ ...spec, name: e.target.value })} /></label>
            <div className="grid sm:grid-cols-3 gap-4">
              <Numeric label="مدة التجربة (دقيقة)" value={spec.horizon_minutes} set={n => update({ ...spec, horizon_minutes: n })} />
              <Numeric label="وصول وحدة كل (دقيقة)" min={0.001} value={spec.arrival_interval_minutes} set={n => update({ ...spec, arrival_interval_minutes: n })} />
              <Numeric label="أقصى عدد للوحدات" max={5000} step="1" value={spec.max_entities} set={n => update({ ...spec, max_entities: n })} />
            </div>
            <p className="text-xs muted">الوحدات تصل بانتظام بدءًا من الدقيقة صفر. يتوقف الحساب عند نهاية المدة، ويظهر العمل المتبقي في النتائج.</p>
            <div className="space-y-4">{spec.stages.map((s, i) => <section key={s.id} className="rounded-2xl border border-sky-100 bg-white/70 p-4 space-y-3">
              <div className="flex items-center gap-3"><span className="rounded-full bg-sky-100 px-3 py-1">{i + 1}</span><input aria-label={"اسم المرحلة " + (i + 1)} required maxLength={100} className="glass-input min-w-0 flex-1" value={s.name} onChange={e => stageChange(i, { name: e.target.value })} /><button type="button" aria-label={"حذف " + s.name} disabled={spec.stages.length === 1} className="text-red-700 text-sm disabled:opacity-30" onClick={() => update({ ...spec, stages: spec.stages.filter((_, j) => j !== i) })}>حذف</button></div>
              <div className="grid sm:grid-cols-3 gap-3">
                <Numeric label="عدد الموارد المتوازية" max={100} step="1" value={s.capacity} set={n => stageChange(i, { capacity: n })} />
                <Numeric label={s.duration === "constant" ? "زمن الخدمة (دقيقة)" : "الزمن الأرجح (دقيقة)"} min={0.001} value={s.minutes} set={n => stageChange(i, { minutes: n })} />
                <label className="block text-sm space-y-2"><span>طبيعة الزمن</span><select className="glass-input w-full" value={s.duration} onChange={e => stageChange(i, { duration: e.target.value as Stage["duration"], minimum: s.minimum ?? s.minutes * 0.5, maximum: s.maximum ?? s.minutes * 1.5 })}><option value="constant">ثابت</option><option value="triangular">متغير: حدان وزمن أرجح</option></select></label>
              </div>
              {s.duration === "triangular" && <div className="grid sm:grid-cols-2 gap-3"><Numeric label="أقل زمن (دقيقة)" min={0.001} value={s.minimum ?? s.minutes} set={n => stageChange(i, { minimum: n })} /><Numeric label="أكبر زمن (دقيقة)" min={0.001} value={s.maximum ?? s.minutes} set={n => stageChange(i, { maximum: n })} /></div>}
            </section>)}</div>
            <Button type="button" variant="secondary" disabled={spec.stages.length >= 12} onClick={() => update({ ...spec, stages: [...spec.stages, { id: "s" + uid().replaceAll("-", ""), name: "مرحلة جديدة", capacity: 1, duration: "constant", minutes: 5, minimum: null, maximum: null }] })}>إضافة مرحلة</Button>
            <label className="block text-sm space-y-2"><span>الافتراضات وحدود التجربة</span><textarea required maxLength={4000} rows={3} className="glass-input w-full" value={spec.assumptions} onChange={e => update({ ...spec, assumptions: e.target.value })} /></label>
            <label className="block text-sm space-y-2"><span>مصدر الأرقام</span><textarea maxLength={2000} rows={2} className="glass-input w-full" value={spec.data_source} onChange={e => update({ ...spec, data_source: e.target.value })} /></label>
            <Button type="submit" disabled={!!saved} isLoading={save.isPending}>{saved ? "النسخة محفوظة" : parentId ? "حفظ نسخة معدلة" : "حفظ السيناريو"}</Button>
          </fieldset>
        </form>}
        {saved && <section className="mt-6 pt-6 border-t border-sky-100 space-y-4">
          <h3 className="font-bold">تشغيل النسخة المحفوظة</h3>
          <div className="grid sm:grid-cols-2 gap-4">
            <Numeric label="عدد التكرارات" max={20} step="1" value={repetitions} set={n => { setRepetitions(n); setRequestKey(uid()); setReviewed(false); }} />
            <Numeric label="رقم إعادة التجربة بنفس العشوائية" min={0} max={2147483600} step="1" value={seed} set={n => { setSeed(n); setRequestKey(uid()); setReviewed(false); }} />
          </div>
          <p className="text-xs muted">زيادة التكرارات تساعد على رؤية التفاوت إذا كانت أزمنة الخدمة متغيرة. الزمن الثابت يعطي النتيجة نفسها عند تكراره.</p>
          <label className="flex items-start gap-2 text-sm leading-6"><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} className="mt-1" />راجعت المراحل والأرقام والافتراضات، وأريد تشغيل هذه النسخة.</label>
          <Button disabled={!reviewed || !availability.data?.available || busy || !Number.isInteger(repetitions) || repetitions < 1 || repetitions > 20 || !Number.isInteger(seed) || seed < 0 || seed > 2147483600} isLoading={start.isPending} onClick={() => start.mutate()}>تشغيل التجربة</Button>
        </section>}
        {error && <p role="alert" className="mt-4 text-red-700">{apiError(error)}</p>}
      </section>
      <aside className="glass rounded-3xl p-5 space-y-3"><h2 className="font-bold">السيناريوهات المحفوظة</h2><p className="text-xs muted leading-6">تعديل سيناريو ينشئ نسخة جديدة ويحافظ على مدخلات التجارب السابقة.</p>{!visibleScenarios.length && <p className="text-sm muted">لم تحفظ سيناريو بعد.</p>}<div className="space-y-2 max-h-[520px] overflow-auto">{visibleScenarios.map(s => <button disabled={busy} key={s.id} className={"w-full text-right p-3 rounded-xl text-sm " + (saved?.id === s.id ? "bg-sky-100" : "bg-white/70")} onClick={() => openScenario(s)}>{s.spec.name}<span className="block text-xs muted mt-1">{s.spec.stages.length} مراحل · {s.parent_id ? "نسخة معدلة" : "نسخة أصلية"}</span></button>)}</div></aside>
    </div>
    <section className="glass rounded-3xl p-5 space-y-4"><h2 className="font-bold text-lg">التجارب والنتائج</h2>{!visibleRuns.length && <p className="muted text-sm">ستظهر التجارب هنا بعد طلب تشغيلها.</p>}
      <div className="grid md:grid-cols-2 gap-3">{visibleRuns.map(r => <div key={r.id} className="rounded-2xl border border-sky-100 p-4 bg-white/60 flex gap-3 justify-between items-center"><button className="text-right min-w-0" onClick={() => setSelectedRun(r.id)}><strong className="block truncate">{r.name}</strong><span className="text-xs muted">{labels[r.status]} · {new Date(r.created_at).toLocaleString("ar-SA")}</span></button>{active.includes(r.status) && <button disabled={cancel.isPending} className="text-red-700 text-sm" onClick={() => cancel.mutate(r.id)}>إيقاف</button>}</div>)}</div>
      {detail.isError && <p role="alert" className="text-red-700">تعذر تحميل تفاصيل التجربة.</p>}
      {detail.data && <section className="rounded-2xl bg-white/80 p-4 space-y-4"><h3 className="font-bold">{detail.data.spec.name} · {labels[detail.data.status]}</h3><p role="status" className="text-sm">{detail.data.message}</p>
        {detail.data.result && <><div className="grid sm:grid-cols-3 gap-3">{[
          ["الوحدات المكتملة", range(detail.data.result.summary.completed)],
          ["العمل المتبقي", range(detail.data.result.summary.work_in_progress)],
          ["متوسط زمن الإنجاز بالدقائق", range(detail.data.result.summary.mean_flow_minutes)],
        ].map(([label, value]) => <div key={label} className="rounded-xl bg-sky-50 p-4"><p className="text-xs muted">{label}</p><p className="font-bold mt-2">{value}</p></div>)}</div>
          <p className="text-xs muted">القيمة متوسط التكرارات، وبين القوسين أدناها وأعلاها. زمن الإنجاز يخص المكتمل فقط.</p>
          <div className="overflow-x-auto"><table className="w-full text-sm text-right"><thead><tr>{["المرحلة", "انشغال الموارد", "انتظار من بدأ الخدمة (دقيقة)", "الطابور عند النهاية"].map(h => <th key={h} className="p-3">{h}</th>)}</tr></thead><tbody>{detail.data.result.stations.map(s => <tr key={s.id} className="border-t border-sky-100"><td className="p-3">{s.name}</td><td className="p-3">{num(s.utilization.mean * 100)}٪</td><td className="p-3">{s.mean_wait_minutes ? range(s.mean_wait_minutes) : "لم تبدأ خدمة"}</td><td className="p-3">{range(s.queued_at_end)}</td></tr>)}</tbody></table></div>
          <ul className="list-disc pr-5 text-xs muted leading-7">{detail.data.result.limitations.map(t => <li key={t}>{t}</li>)}</ul>
        </>}
        <details><summary className="cursor-pointer text-sm text-sky-700">المدخلات المحفوظة لهذه التجربة</summary><div className="text-sm space-y-2 mt-3"><p>المدة: {num(detail.data.spec.horizon_minutes)} دقيقة · وصول كل {num(detail.data.spec.arrival_interval_minutes)} دقيقة · حد الوحدات: {num(detail.data.spec.max_entities)}</p><p>التكرارات: {detail.data.repetitions} · رقم إعادة التجربة: {detail.data.seed}</p><p className="whitespace-pre-wrap">الافتراضات: {detail.data.spec.assumptions}</p><p className="whitespace-pre-wrap">مصدر البيانات: {detail.data.spec.data_source}</p>{detail.data.spec.stages.map((s, i) => <p key={s.id}>{i + 1}. {s.name} — {s.capacity} موارد، {s.duration === "constant" ? "زمن ثابت" : "زمن متغير"}: {s.duration === "constant" ? num(s.minutes) : num(s.minimum) + " / " + num(s.minutes) + " / " + num(s.maximum)} دقيقة</p>)}</div></details>
      </section>}
    </section>
    {finished.length >= 2 && <section className="glass rounded-3xl p-5 space-y-4"><h2 className="font-bold text-lg">مقارنة تجربتين</h2><p className="muted text-sm">اختر تجربتين بمدة ووحدات وافتراضات قابلة للمقارنة. الفروق الحسابية لا تثبت السببية في الواقع.</p><div className="grid sm:grid-cols-2 gap-4">{[[baseline, setBaseline, "التجربة الأساسية"], [candidate, setCandidate, "التجربة البديلة"]].map(([value, setter, label], i) => <label key={i} className="text-sm space-y-2"><span>{label as string}</span><select className="glass-input w-full" value={value as string} onChange={e => (setter as (s: string) => void)(e.target.value)}><option value="">اختر تجربة</option>{finished.map(r => <option key={r.id} value={r.id}>{r.name} · {new Date(r.created_at).toLocaleTimeString("ar-SA")}</option>)}</select></label>)}</div>{left?.summary && right?.summary && left.id !== right.id && <div className="overflow-auto"><table className="w-full text-right text-sm"><thead><tr><th className="p-3">المؤشر</th><th className="p-3">الأساسية</th><th className="p-3">البديلة</th><th className="p-3">الفرق في المتوسط</th></tr></thead><tbody>{(["completed", "work_in_progress", "throughput_per_hour"] as const).map(k => <tr key={k} className="border-t border-sky-100"><td className="p-3">{{ completed: "الوحدات المكتملة", work_in_progress: "العمل المتبقي", throughput_per_hour: "وحدات مكتملة / ساعة" }[k]}</td><td className="p-3">{range(left.summary![k])}</td><td className="p-3">{range(right.summary![k])}</td><td className="p-3">{num(right.summary![k].mean - left.summary![k].mean)}</td></tr>)}</tbody></table></div>}</section>}
  </div>;
}
