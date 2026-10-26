import { useEffect, useRef, useState } from "react";
import { Link, useParams, useLocation } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import ReactMarkdown from "react-markdown";
import { Copy, Send, Plus } from "lucide-react";
import { apiClient } from "../api/client";
import { endpoints } from "../api/endpoints";
import { Button } from "../components/ui/Button";
import { useAuthStore } from "../store/authStore";
import { Composer, ChatRequest } from "../components/Composer";
import { ExecutionDetails } from "../components/ExecutionDetails";
import { Conversation } from "../types";

function errorMessage(error: any) {
  const detail = error?.response?.data?.detail;
  return typeof detail === "string"
    ? detail
    : detail?.error || "تعذر إرسال الرسالة. حاول مرة أخرى.";
}

export function ConversationPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const queryClient = useQueryClient();
  const [text, setText] = useState("");
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  const {
    data: conversation,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["conversation", user?.id, id],
    queryFn: async () =>
      (await apiClient.get(endpoints.conversations.get(id!)))
        .data as Conversation,
    refetchInterval: (query) =>
      ["pending", "running", "synthesizing"].includes(
        query.state.data?.status || "",
      )
        ? 1000
        : false,
  });
  const send = useMutation({
    mutationFn: async (request: ChatRequest) =>
      apiClient.post(endpoints.task.create, { ...request, conversation_id: id }),
    onSuccess: async () => {
      setText("");
      await queryClient.invalidateQueries({
        queryKey: ["conversation", user?.id, id],
      });
      queryClient.invalidateQueries({ queryKey: ["conversations", user?.id] });
    },
  });
  const busy =
    send.isPending ||
    ["pending", "running", "synthesizing"].includes(conversation?.status || "");
  useEffect(() => {
    if (location.hash)
      document
        .getElementById(decodeURIComponent(location.hash.slice(1)))
        ?.scrollIntoView({ block: "center" });
    else bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [conversation?.messages.length, busy, location.hash]);

  if (isLoading)
    return (
      <p className="text-center py-20 text-[#617991]">جاري تحميل المحادثة...</p>
    );
  if (error || !conversation)
    return (
      <div className="text-center py-20">
        <p className="mb-6">تعذر فتح المحادثة. تأكد من صلاحية الوصول.</p>
        <Link to="/history" className="text-[#168bd2]">
          العودة إلى المحادثات
        </Link>
      </div>
    );

  const copy = async (messageId: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedId(messageId);
    } catch {
      setCopiedId(null);
    }
  };

  return (
    <div className="max-w-4xl mx-auto w-full pb-12">
      {conversation.project_id && (
        <Link
          to={"/projects/" + conversation.project_id}
          className="block mb-5 text-sm text-sky-700"
        >
          ← العودة إلى مساحة المشروع ولوحته
        </Link>
      )}
      <div className="flex items-center justify-between gap-4 mb-8">
        <h1 className="text-xl font-bold truncate">{conversation.title}</h1>
        <Link
          to="/"
          className="text-[#168bd2] text-sm flex gap-2 items-center shrink-0"
        >
          <Plus className="w-4 h-4" />
          محادثة جديدة
        </Link>
      </div>
      <div className="space-y-6">
        {conversation.messages.map((message) => (
          <article
            id={message.id}
            key={message.id}
            className={`rounded-2xl p-5 md:p-7 border ${message.role === "user" ? "mr-0 ml-6 md:ml-16 bg-white/5 border-sky-200/60" : "bg-[#f7fbfe] border-[#168bd2]/20"}`}
          >
            <div className="flex items-center justify-between gap-3 mb-4 text-sm">
              <span className="font-bold text-[#168bd2]">
                {message.role === "user" ? "أنت" : "🐜 نمل"}
              </span>
              <time className="text-xs text-[#617991]">
                {new Date(message.created_at).toLocaleString("ar-SA")}
              </time>
            </div>
            {message.status === "failed" && (
              <p className="text-red-700 mb-3">تعذر إكمال هذا الرد</p>
            )}
            {message.role === "user" ? (
              <p className="whitespace-pre-wrap leading-8">{message.content}</p>
            ) : (
              <div className="leading-8 space-y-3 break-words [&_p]:mb-3 [&_h1]:text-2xl [&_h2]:text-xl [&_h3]:font-bold [&_pre]:overflow-auto [&_pre]:bg-slate-100 [&_pre]:p-4 [&_a]:text-sky-700 [&_ul]:list-disc [&_ul]:pr-5">
                <ReactMarkdown>{message.content}</ReactMarkdown>
              </div>
            )}
            {message.role === "assistant" && (
              <div className="flex justify-between items-center gap-4 mt-5">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => copy(message.id, message.content)}
                  className="gap-2"
                >
                  <Copy className="w-4 h-4" />
                  {copiedId === message.id ? "تم النسخ" : "نسخ"}
                </Button>
                <ExecutionDetails execution={message.execution} />
              </div>
            )}
            {message.warnings?.map((warning, index) => <p key={index} className="text-sm text-amber-800 mt-3">{warning}</p>)}
          </article>
        ))}
      </div>
      {busy && (
        <div role="status" className="py-8 text-[#168bd2] animate-pulse">
          🐜 نمل يُعدّ الرد...
        </div>
      )}
      <div ref={bottom} />
      {conversation.user_id === user?.id && (
        <div className="mt-8">
          <Composer
            key={conversation.active_session_id}
            onSend={(task, response_detail) => send.mutate({task, response_detail})}
            busy={busy}
            error={send.error ? errorMessage(send.error) : undefined}
          />
        </div>
      )}
    </div>
  );
}
