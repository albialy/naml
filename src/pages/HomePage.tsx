import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpLeft,
  MessageSquare,
  Sparkles,
  Compass,
  Code2,
  BookOpen,
} from "lucide-react";
import { apiClient } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { ConversationSummary } from "../types";
import { Composer, ChatRequest } from "../components/Composer";
import { Project } from "../types/project";
export function HomePage() {
  const user = useAuthStore((s) => s.user);
  const navigate = useNavigate();
  const cache = useQueryClient();
  const [hint, setHint] = useState("اكتب سؤالك أو أخبر نمل بما تعمل عليه...");
  const projects = useQuery({
    queryKey: ["projects", user?.id],
    queryFn: async () => (await apiClient.get("/projects")).data as Project[],
  });
  const { data: chats = [], isError } = useQuery({
    queryKey: ["conversations", user?.id],
    queryFn: async () =>
      (await apiClient.get("/conversations")).data as ConversationSummary[],
  });
  const send = useMutation({
    mutationFn: async (request: ChatRequest) =>
      (await apiClient.post("/task", request)).data,
    onSuccess: (data) => {
      cache.invalidateQueries({ queryKey: ["conversations"] });
      navigate("/conversation/" + data.conversation_id);
    },
  });
  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex justify-between items-center mb-12">
        <span className="text-sm muted">مساحة التفكير والعمل</span>
        <Link to="/settings" className="text-sm text-sky-700">
          إعدادات التشغيل
        </Link>
      </div>
      <div className="mb-8">
        <div className="inline-flex gap-2 items-center text-sky-700 text-sm mb-4">
          <Sparkles size={17} />
          مرحبًا {user?.username}
        </div>
        <h1 className="text-3xl md:text-4xl font-bold leading-relaxed mb-3">
          من فكرة أولى، إلى خطوة واضحة.
        </h1>
        <p className="muted leading-7">
          ناقش أفكارك مع نمل، واستكمل محادثاتك، واجمع عملك داخل مشاريعك.
        </p>
      </div>
      <Composer
        prefill={hint.startsWith("اكتب") ? undefined : hint}
        onSend={(task, response_detail) => send.mutate({task, response_detail})}
        busy={send.isPending}
        placeholder={hint}
        error={
          send.isError
            ? "تعذر بدء المحادثة. تحقق من الاتصال وحد الاستخدام."
            : undefined
        }
      />
      <div className="grid sm:grid-cols-3 gap-3 mt-5">
        {[
          {
            icon: Compass,
            title: "استكشف فكرة",
            text: "ساعدني في اختبار فكرة مشروع جديد",
          },
          {
            icon: Code2,
            title: "خطط لتطبيق",
            text: "ساعدني في تحديد متطلبات تطبيق",
          },
          {
            icon: BookOpen,
            title: "ابدأ بحثًا",
            text: "ساعدني في وضع خطة بحث",
          },
        ].map((item) => (
          <button
            key={item.title}
            onClick={() => setHint(item.text + "…")}
            className="text-right glass rounded-2xl p-4 flex gap-3 items-center hover:bg-white"
          >
            <item.icon size={20} className="text-sky-600" />
            <div>
              <p className="font-bold text-sm">{item.title}</p>
              <p className="text-xs muted mt-1">{item.text}</p>
            </div>
          </button>
        ))}
      </div>
      <section className="mt-10">
        <div className="flex justify-between items-center mb-4">
          <h2 className="font-bold text-lg">مشاريعك الأخيرة</h2>
          <Link to="/projects" className="text-sm text-sky-700">
            كل المشاريع
          </Link>
        </div>
        <div className="grid md:grid-cols-3 gap-3">
          {projects.data?.slice(0, 3).map((project) => (
            <Link
              key={project.id}
              to={"/projects/" + project.id}
              className="glass rounded-2xl p-5 hover:bg-white"
            >
              <h3 className="font-bold truncate">{project.name}</h3>
              <p className="text-sm muted mt-2 line-clamp-2">
                {project.goal || "استكمل العمل على مشروعك"}
              </p>
            </Link>
          ))}
        </div>
        {projects.isError && (
          <p role="alert" className="text-red-700 text-sm">
            تعذر تحميل المشاريع.
          </p>
        )}
        {projects.data?.length === 0 && (
          <Link
            to="/projects"
            className="block rounded-2xl border border-dashed border-sky-200 p-5 text-sm muted"
          >
            أنشئ مشروعًا لتجميع المحادثات وتنظيم خطوات العمل ←
          </Link>
        )}
      </section>
      <div className="flex justify-between items-center mt-10 mb-5">
        <h2 className="font-bold text-lg">محادثاتك الأخيرة</h2>
        <Link to="/history" className="text-sm text-sky-700">
          عرض الكل
        </Link>
      </div>
      {isError && (
        <p role="alert" className="text-red-700">
          تعذر تحميل المحادثات.
        </p>
      )}
      <div className="grid md:grid-cols-2 gap-4">
        {chats.slice(0, 4).map((c) => (
          <Link
            to={"/conversation/" + c.conversation_id}
            key={c.conversation_id}
            className="glass rounded-2xl p-5 hover:bg-white"
          >
            <div className="flex justify-between mb-4">
              <MessageSquare size={20} className="text-sky-600" />
              <ArrowUpLeft size={18} className="muted" />
            </div>
            <h3 className="font-bold truncate">{c.title}</h3>
            <p className="text-xs muted mt-2">
              {new Date(c.updated_at).toLocaleDateString("ar-SA")} ·{" "}
              {c.message_count} رسالة
            </p>
          </Link>
        ))}
      </div>
      {!chats.length && !isError && (
        <div className="border border-dashed border-sky-200 rounded-2xl p-7 text-center muted">
          محادثتك الأولى تبدأ من هنا. اكتب رسالتك بالأعلى.
        </div>
      )}
    </div>
  );
}
