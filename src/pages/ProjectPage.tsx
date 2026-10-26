import { useState } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  FolderOpen,
  MessageSquare,
  LayoutDashboard,
  Settings,
  ArrowRight,
  Plus,
} from "lucide-react";
import { apiClient } from "../api/client";
import {
  Project,
  apiError,
  ModelChoice,
  projectLabels,
} from "../types/project";
import { ConversationSummary } from "../types";
import { useAuthStore } from "../store/authStore";
import { Button } from "../components/ui/Button";
import { Composer, ChatRequest } from "../components/Composer";
import { ModelSettings } from "../components/ModelSettings";
import { WorkCenter } from "../components/WorkCenter";
import { ProjectBoard } from "../components/ProjectBoard";
export function ProjectPage() {
  const { id } = useParams();
  const user = useAuthStore((s) => s.user);
  const cache = useQueryClient();
  const navigate = useNavigate();
  const [tab, setTab] = useState("overview");
  const [attach, setAttach] = useState("");
  const q = useQuery({
    queryKey: ["project", user?.id, id],
    queryFn: async () =>
      (await apiClient.get("/projects/" + id)).data as Project,
    refetchInterval: 5000,
  });
  const chats = useQuery({
    queryKey: ["conversations", user?.id],
    queryFn: async () =>
      (await apiClient.get("/conversations")).data as ConversationSummary[],
  });
  const prefs = useQuery({
    queryKey: ["preferences", user?.id],
    queryFn: async () => (await apiClient.get("/preferences")).data,
    enabled: tab === "settings",
  });
  const refresh = () => {
    cache.invalidateQueries({ queryKey: ["project", user?.id, id] });
    cache.invalidateQueries({ queryKey: ["projects"] });
    cache.invalidateQueries({ queryKey: ["conversations"] });
  };
  const send = useMutation({
    mutationFn: async (request: ChatRequest) =>
      (await apiClient.post("/task", { ...request, project_id: id })).data,
    onSuccess: (d) => {
      refresh();
      navigate("/conversation/" + d.conversation_id);
    },
  });
  const link = useMutation({
    mutationFn: () =>
      apiClient.post(`/projects/${id}/conversations`, {
        conversation_id: attach,
      }),
    onSuccess: () => {
      setAttach("");
      refresh();
    },
  });
  const update = useMutation({
    mutationFn: (data: object) =>
      apiClient.patch("/projects/" + id, {
        revision: q.data?.revision,
        ...data,
      }),
    onSuccess: refresh,
  });
  if (q.isLoading) return <p>جارٍ تحميل المشروع…</p>;
  if (!q.data || q.isError)
    return (
      <p role="alert">
        تعذر فتح المشروع. <Link to="/projects">العودة إلى المشاريع</Link>
      </p>
    );
  const p = q.data;
  const unlinked = (chats.data || []).filter(
    (c) =>
      !c.project_id &&
      !["pending", "running", "synthesizing"].includes(c.status),
  );
  return (
    <div className="max-w-6xl mx-auto">
      <Link
        to="/projects"
        className="inline-flex gap-2 items-center text-sm muted mb-6"
      >
        <ArrowRight size={16} />
        كل المشاريع
      </Link>
      <div className="flex gap-4 items-center mb-5">
        <div className="rounded-2xl p-4 bg-sky-100 text-sky-700">
          <FolderOpen size={28} />
        </div>
        <div className="min-w-0">
          <p className="text-xs text-sky-700 mb-1">
            {projectLabels[p.project_type]}
          </p>
          <h1 className="text-2xl md:text-3xl font-bold break-words">
            {p.name}
          </h1>
        </div>
      </div>
      <p className="muted leading-7 mb-6 whitespace-pre-wrap">
        {p.goal || "أضف هدف المشروع من الإعدادات، أو ابدأ بتوضيحه في الحوار."}
      </p>
      <nav
        aria-label="أقسام المشروع"
        className="flex gap-2 border-b border-sky-200/60 pb-4 mb-7 flex-wrap"
      >
        {[
          { id:"overview",title:"متابعة المشروع",icon:LayoutDashboard },
          { id: "chat", title: "المحادثات", icon: MessageSquare },
          { id: "board", title: "لوحة المشروع", icon: LayoutDashboard },
          { id: "settings", title: "إعدادات المشروع", icon: Settings },
        ].map((t) => (
          <Button
            key={t.id}
            variant={tab === t.id ? "secondary" : "ghost"}
            onClick={() => setTab(t.id)}
          >
            <t.icon size={17} />
            {t.title}
            {t.id === "board" && p.proposal && (
              <span className="w-2 h-2 rounded-full bg-sky-600" />
            )}
          </Button>
        ))}
      </nav>
      {tab === "overview" && <WorkCenter project={p} onRefresh={refresh} openBoard={()=>setTab("board")} />}
      {tab === "chat" && (
        <div className="space-y-7">
          <Composer
            onSend={(task, response_detail) => send.mutate({task, response_detail})}
            busy={send.isPending}
            placeholder="ابدأ محادثة جديدة داخل هذا المشروع…"
            error={send.error ? apiError(send.error) : undefined}
          />
          {p.proposal && (
            <button
              onClick={() => setTab("board")}
              className="w-full text-right bg-sky-100 border border-sky-200 rounded-2xl p-4 text-sky-900"
            >
              جهّز نمل اقتراحًا لتطوير لوحة المشروع. راجعه قبل الإضافة ←
            </button>
          )}
          <div className="flex justify-between items-center">
            <h2 className="font-bold text-lg">محادثات المشروع</h2>
            <span className="text-sm muted">
              {p.conversations?.length || 0} محادثة
            </span>
          </div>
          <div className="grid md:grid-cols-2 gap-3">
            {p.conversations?.map((c) => (
              <Link
                key={c.conversation_id}
                to={"/conversation/" + c.conversation_id}
                className="glass rounded-2xl p-5 hover:bg-white"
              >
                <MessageSquare size={18} className="text-sky-700 mb-3" />
                <h3 className="font-bold truncate">{c.title}</h3>
                <p className="text-xs muted mt-2">
                  {c.message_count} رسالة ·{" "}
                  {new Date(c.updated_at).toLocaleDateString("ar-SA")}
                </p>
              </Link>
            ))}
          </div>
          {!p.conversations?.length && (
            <p className="muted text-sm">
              ابدأ الحوار بالأعلى، وستُحفظ هذه المحادثة داخل المشروع.
            </p>
          )}
          {unlinked.length > 0 && (
            <div className="glass rounded-2xl p-5">
              <label className="block font-bold mb-3" htmlFor="link-chat">
                إضافة محادثة سابقة
              </label>
              <div className="flex gap-3 flex-wrap">
                <select
                  id="link-chat"
                  className="glass-input flex-1 min-w-0"
                  value={attach}
                  onChange={(e) => setAttach(e.target.value)}
                >
                  <option value="">اختر محادثة غير مرتبطة بمشروع</option>
                  {unlinked.map((c) => (
                    <option key={c.conversation_id} value={c.conversation_id}>
                      {c.title}
                    </option>
                  ))}
                </select>
                <Button
                  disabled={!attach}
                  isLoading={link.isPending}
                  onClick={() => link.mutate()}
                >
                  <Plus size={16} />
                  إضافة
                </Button>
              </div>
              {link.error && (
                <p role="alert" className="text-red-700 mt-3">
                  {apiError(link.error)}
                </p>
              )}
            </div>
          )}
        </div>
      )}
      {tab === "board" && <ProjectBoard project={p} onRefresh={refresh} />}
      {tab === "settings" && (
        <div className="space-y-7">
          <ProjectDetails
            key={p.id + ":" + p.name + ":" + p.goal}
            project={p}
            busy={update.isPending}
            onSave={(v) => update.mutate(v)}
          />
          <div className="glass p-6 rounded-3xl">
            <h2 className="font-bold text-lg mb-4">
              النموذج المدير لهذا المشروع
            </h2>
            <p className="muted text-sm mb-5">
              {p.director
                ? "يستخدم المشروع اختيارًا خاصًا."
                : "يتبع المشروع إعدادات حسابك."}
            </p>
            {prefs.data && (
              <ModelSettings
                key={JSON.stringify(
                  p.director || prefs.data.effective_director,
                )}
                initial={p.director || prefs.data.effective_director}
                models={prefs.data.available_models}
                busy={update.isPending}
                onSave={(director: ModelChoice) => update.mutate({ director })}
                onReset={() => update.mutate({ director: null })}
              />
            )}
          </div>
          {update.isSuccess && (
            <p role="status" className="text-emerald-700">
              تم حفظ إعدادات المشروع.
            </p>
          )}
          {update.error && (
            <p role="alert" className="text-red-700">
              {apiError(update.error)}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
function ProjectDetails({
  project,
  busy,
  onSave,
}: {
  project: Project;
  busy: boolean;
  onSave: (v: object) => void;
}) {
  const [revision] = useState(project.revision);
  const [name, setName] = useState(project.name);
  const [goal, setGoal] = useState(project.goal);
  return (
    <form
      className="glass rounded-3xl p-6 space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        onSave({ name, goal, revision });
      }}
    >
      <label className="block space-y-2">
        <span>اسم المشروع</span>
        <input
          className="glass-input"
          required
          maxLength={100}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
      </label>
      <label className="block space-y-2">
        <span>الهدف</span>
        <textarea
          className="glass-input min-h-24"
          maxLength={3000}
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
        />
      </label>
      <Button type="submit" isLoading={busy}>
        حفظ معلومات المشروع
      </Button>
    </form>
  );
}
