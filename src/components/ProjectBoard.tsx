import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import {
  Sparkles,
  LockKeyhole,
  LockKeyholeOpen,
  Undo2,
  ArrowUp,
  ArrowDown,
  Eye,
  EyeOff,
  Plus,
  ExternalLink,
  Pencil,
  Trash2,
  SlidersHorizontal,
} from "lucide-react";
import { apiClient } from "../api/client";
import {
  Project,
  BoardItem,
  BoardModule,
  moduleLabels,
  apiError,
} from "../types/project";
import { Button } from "./ui/Button";
type Command = {
  method: "post" | "patch" | "put" | "delete";
  path: string;
  data?: object;
};
const statusLabels = { todo: "لم تبدأ", doing: "قيد التنفيذ", done: "مكتملة" };
export function ProjectBoard({
  project: p,
  onRefresh,
}: {
  project: Project;
  onRefresh: () => void;
}) {
  const [customize, setCustomize] = useState(false);
  const [kind, setKind] = useState("");
  const [edit, setEdit] = useState<{
    module: BoardModule;
    item?: BoardItem;
    revision: number;
  } | null>(null);
  const change = useMutation({
    mutationFn: async (c: Command) =>
      apiClient.request({
        method: c.method,
        url: "/projects/" + p.id + c.path,
        data: { revision: p.revision, ...c.data },
      }),
    onSuccess: () => {
      onRefresh();
      setEdit(null);
    },
    onError: () => onRefresh(),
  });
  const suggest = useMutation({
    mutationFn: () => apiClient.post("/projects/" + p.id + "/suggest"),
    onSuccess: onRefresh,
    onError: onRefresh,
  });
  const busy = change.isPending;
  const generating = suggest.isPending || p.suggestion_status === "running";
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2 justify-between">
        <div>
          <h2 className="font-bold text-xl">لوحة المشروع</h2>
          <p className="muted text-sm mt-2">
            تتوسع مع العمل، وتبقى قرارات التغيير بيدك.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={p.locked || generating}
            isLoading={generating}
            onClick={() => suggest.mutate()}
          >
            <Sparkles size={16} />
            اقتراح تطوير اللوحة
          </Button>
          <Button variant="ghost" onClick={() => setCustomize(!customize)}>
            <SlidersHorizontal size={17} />
            تخصيص
          </Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-xs muted">
        <Button
          variant="ghost"
          size="sm"
          disabled={busy}
          onClick={() =>
            change.mutate({
              method: "patch",
              path: "",
              data: { locked: !p.locked },
            })
          }
        >
          {p.locked ? <LockKeyhole size={15} /> : <LockKeyholeOpen size={15} />}{" "}
          {p.locked ? "اللوحة مثبتة" : "تثبيت اللوحة"}
        </Button>
        <label className="flex gap-2 items-center">
          <input
            type="checkbox"
            checked={p.auto_suggest}
            disabled={busy}
            onChange={(e) =>
              change.mutate({
                method: "patch",
                path: "",
                data: { auto_suggest: e.target.checked },
              })
            }
          />
          اقتراحات بعد المحادثات
        </label>
        <Button
          size="sm"
          variant="ghost"
          disabled={!p.can_undo || busy}
          onClick={() => change.mutate({ method: "post", path: "/undo" })}
        >
          <Undo2 size={15} />
          التراجع عن آخر تعديل
        </Button>
      </div>
      {p.locked && (
        <p className="bg-sky-50 rounded-xl p-3 text-sm muted">
          تم إيقاف اقتراحات نمل وتطبيقها. يمكنك تعديل اللوحة يدويًا.
        </p>
      )}
      {(change.error || suggest.error || p.suggestion_error) && (
        <p role="alert" className="text-red-700 text-sm">
          {change.error
            ? apiError(change.error)
            : suggest.error
              ? apiError(suggest.error)
              : p.suggestion_error}
        </p>
      )}
      {p.proposal && (
        <section className="rounded-3xl border border-sky-300 bg-sky-50/90 p-6">
          <div className="flex gap-2 items-center font-bold text-sky-800">
            <Sparkles size={20} />
            اقتراح نمل — ينتظر مراجعتك
          </div>
          <p className="my-3 leading-7 text-sm">{p.proposal.reason}</p>
          <p className="text-sm muted mb-4">
            الأقسام:{" "}
            {p.proposal.modules.map((k) => moduleLabels[k]).join("، ") ||
              "الأقسام الحالية"}
          </p>
          <div className="space-y-3 mb-5">
            {p.proposal.items.map((item, i) => (
              <div key={i} className="rounded-xl bg-white p-4 text-sm">
                <p className="font-bold">
                  {moduleLabels[item.kind]} · {item.title}
                </p>
                <p className="muted mt-2 whitespace-pre-wrap">{item.content}</p>
                <details className="mt-2">
                  <summary className="cursor-pointer text-sky-700">
                    الدليل من المحادثة
                  </summary>
                  <blockquote className="muted mt-2 border-r-2 border-sky-200 pr-3">
                    {item.evidence}
                  </blockquote>
                  <Link
                    to={
                      "/conversation/" +
                      item.conversation_id +
                      "#" +
                      item.message_id
                    }
                    className="text-sky-700"
                  >
                    فتح الرسالة
                  </Link>
                </details>
              </div>
            ))}
          </div>
          <div className="flex gap-3">
            <Button
              disabled={busy || p.locked}
              onClick={() =>
                change.mutate({
                  method: "post",
                  path: "/proposal/accept",
                  data: { proposal_id: p.proposal!.id },
                })
              }
            >
              اعتماد الإضافات
            </Button>
            <Button
              variant="outline"
              disabled={busy}
              onClick={() =>
                change.mutate({
                  method: "post",
                  path: "/proposal/dismiss",
                  data: { proposal_id: p.proposal!.id },
                })
              }
            >
              تجاهل
            </Button>
          </div>
          <p className="text-xs muted mt-3">
            تُضاف العناصر الجديدة دون استبدال بياناتك الحالية. يمكنك تعديلها أو
            التراجع بعد الاعتماد.
          </p>
        </section>
      )}
      {customize && (
        <section className="glass rounded-3xl p-5">
          <h3 className="font-bold mb-4">ترتيب الأقسام وإظهارها</h3>
          <div className="space-y-2">
            {p.modules.map((m, i) => (
              <div
                className="flex items-center justify-between gap-2"
                key={m.id}
              >
                <span className="text-sm">{m.title}</span>
                <div className="flex gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={"إظهار أو إخفاء " + m.title}
                    disabled={busy}
                    onClick={() =>
                      change.mutate({
                        method: "patch",
                        path: "/modules/" + m.id,
                        data: { hidden: !m.hidden },
                      })
                    }
                  >
                    {m.hidden ? <EyeOff size={16} /> : <Eye size={16} />}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={"رفع " + m.title}
                    disabled={busy || i === 0}
                    onClick={() =>
                      change.mutate({
                        method: "patch",
                        path: "/modules/" + m.id,
                        data: { direction: "up" },
                      })
                    }
                  >
                    <ArrowUp size={16} />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={"خفض " + m.title}
                    disabled={busy || i === p.modules.length - 1}
                    onClick={() =>
                      change.mutate({
                        method: "patch",
                        path: "/modules/" + m.id,
                        data: { direction: "down" },
                      })
                    }
                  >
                    <ArrowDown size={16} />
                  </Button>
                </div>
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-5">
            <select
              aria-label="نوع القسم الجديد"
              className="glass-input"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              <option value="">إضافة قسم</option>
              {Object.entries(moduleLabels)
                .filter(([k]) => !p.modules.some((m) => m.kind === k))
                .map(([k, label]) => (
                  <option key={k} value={k}>
                    {label}
                  </option>
                ))}
            </select>
            <Button
              disabled={!kind || busy}
              onClick={() => {
                change.mutate({
                  method: "post",
                  path: "/modules",
                  data: { kind },
                });
                setKind("");
              }}
            >
              إضافة
            </Button>
          </div>
        </section>
      )}
      {edit && (
        <ItemEditor
          key={edit.module.id + ":" + (edit.item?.id || "new")}
          project={p}
          kind={edit.module.kind}
          item={edit.item}
          busy={busy}
          title={edit.module.title}
          onCancel={() => setEdit(null)}
          onSave={(item) =>
            change.mutate({
              method: edit.item ? "put" : "post",
              path: `/modules/${edit.module.id}/items${edit.item ? "/" + edit.item.id : ""}`,
              data: { item, revision: edit.revision },
            })
          }
        />
      )}
      <div className="grid xl:grid-cols-2 gap-5 items-start">
        {p.modules
          .filter((m) => !m.hidden)
          .map((m) => (
            <section
              key={m.id}
              className={`glass rounded-3xl p-5 md:p-6 ${["requirements", "chapters", "sources"].includes(m.kind) ? "xl:col-span-2" : ""}`}
            >
              <div className="flex items-center justify-between gap-3 mb-5">
                <h3 className="font-bold text-lg">
                  {m.title}
                  <span className="text-xs muted mr-2">{m.items.length}</span>
                </h3>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={"إضافة عنصر إلى " + m.title}
                  onClick={() => setEdit({ module: m, revision: p.revision })}
                >
                  <Plus size={17} />
                  إضافة
                </Button>
              </div>
              {!m.items.length && (
                <p className="text-sm muted leading-7 border border-dashed border-sky-200 p-5 rounded-2xl">
                  لا توجد عناصر بعد. أضف عنصرًا أو ناقش مشروعك ليقترح نمل
                  تنظيمه.
                </p>
              )}
              <div className="space-y-3">
                {m.items.map((item) => (
                  <article
                    key={item.id}
                    className="bg-white/75 border border-sky-100 rounded-2xl p-4"
                  >
                    <div className="flex gap-2 justify-between">
                      <h4 className="font-bold text-sm break-words">
                        {item.title}
                      </h4>
                      <div className="flex shrink-0">
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={m.kind === "decisions" && item.decision_state === "approved"}
                          title={m.kind === "decisions" && item.decision_state === "approved" ? "القرار معتمد؛ أضف قرارًا جديدًا لتغييره" : undefined}
                          aria-label={"تعديل " + item.title}
                          onClick={() =>
                            setEdit({ module: m, item, revision: p.revision })
                          }
                        >
                          <Pencil size={14} />
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={"حذف " + item.title}
                          disabled={busy}
                          onClick={() =>
                            change.mutate({
                              method: "delete",
                              path: `/modules/${m.id}/items/${item.id}`,
                            })
                          }
                        >
                          <Trash2 size={14} />
                        </Button>
                      </div>
                    </div>
                    {m.kind==='decisions'&&<p className="text-xs text-sky-700 mt-2">{item.decision_state==='approved'?'قرار معتمد':item.decision_state==='rejected'?'قرار مرفوض':'مقترح ينتظر قرارك — اعتمده من متابعة المشروع'}</p>}
                    {m.kind==='facts'&&<p className="text-xs text-sky-700 mt-2">{item.knowledge_status==='confirmed'?'أكدها المستخدم':item.knowledge_status==='disputed'?'محل خلاف':'غير متحقق منها'}</p>}
                    {item.owner&&<p className="text-xs muted mt-2">المسؤول: {item.owner}</p>}
                    {item.expected_outcome&&<p className="text-xs muted mt-2">المخرج المتوقع: {item.expected_outcome}</p>}
                    {m.kind==='results'&&<p className="text-sm mt-2">المستهدف: {item.target??'غير محدد'} · الفعلي: {item.actual??'لم يسجل بعد'} {item.unit}</p>}
                    {item.content && (
                      <p className="text-sm muted whitespace-pre-wrap leading-7 mt-2">
                        {item.content}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-3 items-center mt-3">
                      <span
                        className={`text-xs rounded-lg px-2 py-1 ${item.status === "done" ? "text-emerald-800 bg-emerald-50" : "text-sky-800 bg-sky-50"}`}
                      >
                        {statusLabels[item.status]}
                      </span>
                      {item.due_date && (
                        <time className="text-xs muted">{item.due_date}</time>
                      )}
                      {item.url && (
                        <a
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-sky-700 flex gap-1"
                        >
                          <ExternalLink size={13} />
                          فتح المصدر
                        </a>
                      )}
                      {item.conversation_id && (
                        <Link
                          to={
                            "/conversation/" +
                            item.conversation_id +
                            "#" +
                            item.message_id
                          }
                          className="text-xs text-sky-700"
                        >
                          المحادثة الأصلية
                        </Link>
                      )}
                    </div>
                  </article>
                ))}
              </div>
            </section>
          ))}
      </div>
      {!p.modules.some((m) => !m.hidden) && (
        <p className="muted">كل الأقسام مخفية. استخدم «تخصيص» لإظهارها.</p>
      )}
    </div>
  );
}
function ItemEditor({
  project,kind,
  item,
  title,
  busy,
  onSave,
  onCancel,
}: {
  project:Project;kind:string;
  item?: BoardItem;
  title: string;
  busy: boolean;
  onSave: (v: object) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState({
    title: item?.title || "",
    content: item?.content || "",
    status: item?.status || "todo",
    due_date: item?.due_date || "",
    url: item?.url || "",
    owner:item?.owner||'', expected_outcome:item?.expected_outcome||'',
    linked_decision_id:item?.linked_decision_id||'',linked_task_id:item?.linked_task_id||'',blocked_by:item?.blocked_by||[],
    knowledge_status:item?.knowledge_status||'unverified',decision_state:item?.decision_state||'proposed',
    target:item?.target??null,actual:item?.actual??null,unit:item?.unit||'',direction:item?.direction||'increase',

  });
  return (
    <form
      className="glass border-sky-300! rounded-3xl p-6 space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(value);
      }}
    >
      <h3 className="font-bold">
        {item ? "تعديل عنصر" : "عنصر جديد"} · {title}
      </h3>
      <label className="block space-y-2">
        <span className="text-sm">العنوان</span>
        <input
          autoFocus
          className="glass-input"
          required
          maxLength={200}
          value={value.title}
          onChange={(e) => setValue({ ...value, title: e.target.value })}
        />
      </label>
      <label className="block space-y-2">
        <span className="text-sm">التفاصيل</span>
        <textarea
          className="glass-input"
          maxLength={5000}
          value={value.content}
          onChange={(e) => setValue({ ...value, content: e.target.value })}
        />
      </label>
      <div className="grid sm:grid-cols-2 gap-4">
        <label className="block space-y-2">
          <span className="text-sm">الحالة</span>
          <select
            aria-label="الحالة"
            className="glass-input"
            value={value.status}
            onChange={(e) =>
              setValue({
                ...value,
                status: e.target.value as BoardItem["status"],
              })
            }
          >
            {Object.entries(statusLabels).map(([k, v]) => (
              <option value={k} key={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-2">
          <span className="text-sm">الموعد (اختياري)</span>
          <input
            className="glass-input"
            type="date"
            value={value.due_date}
            onChange={(e) => setValue({ ...value, due_date: e.target.value })}
          />
        </label>
      </div>
      <label className="block space-y-2">
        <span className="text-sm">رابط المصدر (اختياري)</span>
        <input
          className="glass-input"
          type="url"
          dir="ltr"
          maxLength={2000}
          value={value.url}
          onChange={(e) => setValue({ ...value, url: e.target.value })}
        />
      </label>
      {kind==='facts'&&<label className="block space-y-2"><span>درجة التحقق</span><select aria-label="درجة التحقق" className="glass-input" value={value.knowledge_status} onChange={e=>setValue({...value,knowledge_status:e.target.value as any})}><option value="unverified">غير متحقق منها</option><option value="confirmed">أكدتها أنا</option><option value="disputed">محل خلاف</option></select><p className="text-xs muted">التأكيد هنا قرار منك، وليس تحققًا مستقلًا من نمل.</p></label>}
      {kind==='tasks'&&<div className="space-y-4"><label className="block space-y-2"><span>المسؤول</span><input className="glass-input" maxLength={150} value={value.owner} onChange={e=>setValue({...value,owner:e.target.value})}/></label><label className="block space-y-2"><span>المخرج المتوقع</span><textarea className="glass-input" maxLength={1000} value={value.expected_outcome} onChange={e=>setValue({...value,expected_outcome:e.target.value})}/></label><label className="block space-y-2"><span>القرار المرتبط</span><select aria-label="القرار المرتبط" className="glass-input" value={value.linked_decision_id} onChange={e=>setValue({...value,linked_decision_id:e.target.value})}><option value="">بدون قرار مرتبط</option>{project.modules.filter(m=>m.kind==='decisions').flatMap(m=>m.items).filter(i=>i.decision_state==='approved').map(i=><option key={i.id} value={i.id}>{i.title}</option>)}</select></label><fieldset className="space-y-2"><legend>تعتمد على اكتمال</legend>{project.modules.filter(m=>m.kind==='tasks').flatMap(m=>m.items).filter(i=>i.id!==item?.id).map(i=><label key={i.id} className="flex gap-2 items-center text-sm"><input type="checkbox" checked={value.blocked_by.includes(i.id)} onChange={e=>setValue({...value,blocked_by:e.target.checked?[...value.blocked_by,i.id]:value.blocked_by.filter(x=>x!==i.id)})}/>{i.title}</label>)}</fieldset></div>}
      {kind==='results'&&<div className="space-y-4"><label className="block space-y-2"><span>المهمة التي نقيسها</span><select aria-label="المهمة التي نقيسها" required className="glass-input" value={value.linked_task_id} onChange={e=>setValue({...value,linked_task_id:e.target.value})}><option value="">اختر مهمة</option>{project.modules.filter(m=>m.kind==='tasks').flatMap(m=>m.items).map(i=><option key={i.id} value={i.id}>{i.title}</option>)}</select></label><div className="grid sm:grid-cols-2 gap-4"><label><span>القيمة المستهدفة</span><input type="number" step="any" className="glass-input" value={value.target??''} onChange={e=>setValue({...value,target:e.target.value===''?null:Number(e.target.value)})}/></label><label><span>النتيجة الفعلية</span><input type="number" step="any" className="glass-input" value={value.actual??''} onChange={e=>setValue({...value,actual:e.target.value===''?null:Number(e.target.value)})}/></label></div><label className="block"><span>وحدة القياس</span><input className="glass-input" maxLength={80} value={value.unit} onChange={e=>setValue({...value,unit:e.target.value})} placeholder="مثل: تسجيل، ريال، يوم"/></label><label className="block"><span>اتجاه النجاح</span><select aria-label="اتجاه النجاح" className="glass-input" value={value.direction} onChange={e=>setValue({...value,direction:e.target.value as any})}><option value="increase">الوصول إلى الهدف أو تجاوزه</option><option value="decrease">البقاء عند الهدف أو أقل</option></select></label><p className="text-xs muted">اترك القيمة الفعلية فارغة حتى تتوفر بيانات؛ الصفر يُعد نتيجة فعلية.</p></div>}
      <div className="flex gap-3">
        <Button type="submit" isLoading={busy}>
          حفظ العنصر
        </Button>
        <Button
          type="button"
          variant="ghost"
          disabled={busy}
          onClick={onCancel}
        >
          إلغاء
        </Button>
      </div>
    </form>
  );
}
