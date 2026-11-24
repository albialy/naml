import { useEffect, useRef, useState } from 'react';
import { Link, useParams, useLocation } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
import { Copy, Plus, Pencil, RotateCcw, Square, Quote, X, PanelLeft } from 'lucide-react';
import { apiClient } from '../api/client';
import { Button } from '../components/ui/Button';
import { useAuthStore } from '../store/authStore';
import { Composer, ResponseDetail } from '../components/Composer';
import { ExecutionDetails } from '../components/ExecutionDetails';
import { ConversationPreview } from '../components/ConversationPreview';
import { Conversation } from '../types';

function errorMessage(error: any) {
  const detail = error?.response?.data?.detail;
  return typeof detail === 'string' ? detail : detail?.error || 'تعذر تنفيذ الطلب. حاول مرة أخرى.';
}
const activeStates = ['pending', 'running', 'synthesizing'];
type Turn = { task: string; response_detail: ResponseDetail; action?: 'send' | 'edit' | 'retry'; message_id?: string; interrupt_session_id?: string; reference?: {message_id: string; text: string} };

export function ConversationPage() {
  const { id } = useParams<{ id: string }>();
  // Remount local drafts/selection on navigation between conversations, never on polling.
  return <ConversationWorkspace key={id} id={id!} />;
}
function ConversationWorkspace({ id }: { id: string }) {
  const location = useLocation();
  const user = useAuthStore(s => s.user);
  const cache = useQueryClient();
  const key = ['conversation', user?.id, id];
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);
  const [reference, setReference] = useState<{ message_id: string; text: string } | null>(null);
  const [resetKey, setResetKey] = useState(0);
  const [preview, setPreview] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);
  const { data: conversation, isLoading, error } = useQuery({
    queryKey: key,
    queryFn: async () => (await apiClient.get('/conversations/' + id)).data as Conversation,
    refetchInterval: query => activeStates.includes(query.state.data?.status || '') ? 1000 : false,
  });
  const refresh = async () => {
    await cache.invalidateQueries({ queryKey: key });
    await cache.invalidateQueries({ queryKey: ['conversations', user?.id] });
  };
  const send = useMutation({
    mutationFn: async (request: Turn) => apiClient.post('/task', {
      ...request, conversation_id: id, branch_id: conversation?.branch_id,
      expected_revision: conversation?.revision,
    }),
    onSuccess: async () => {setEditing(null);setReference(null);setResetKey(n => n + 1);await refresh();},
    onError: () => {void refresh();},
  });
  const stop = useMutation({
    mutationFn: async () => apiClient.post('/conversations/' + id + '/stop', {
      session_id: conversation?.active_session_id, revision: conversation?.revision, branch_id: conversation?.branch_id,
    }),
    onSuccess: refresh,
    onError: () => {void refresh();},
  });
  const changeBranch = useMutation({
    mutationFn: async (branch_id: string) => apiClient.post('/conversations/' + id + '/branch', {branch_id, revision: conversation?.revision}),
    onSuccess: async () => {setEditing(null);setReference(null);send.reset();stop.reset();await refresh();},
    onError: () => {void refresh();},
  });
  const running = activeStates.includes(conversation?.status || '');
  const pending = send.isPending || stop.isPending || changeBranch.isPending;
  const owner = conversation?.user_id === user?.id;
  useEffect(() => {
    if (location.hash) document.getElementById(decodeURIComponent(location.hash.slice(1)))?.scrollIntoView({block: 'center'});
    else bottom.current?.scrollIntoView({behavior: 'smooth', block: 'end'});
  }, [conversation?.messages.length, conversation?.branch_id, location.hash]);
  // Another tab may change the active branch. Never carry a quote/edit across it.
  const lastBranch = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (lastBranch.current && lastBranch.current !== conversation?.branch_id) {setEditing(null);setReference(null);}
    lastBranch.current = conversation?.branch_id;
  }, [conversation?.branch_id]);

  if (isLoading) return <p className="text-center py-20 muted">جارٍ تحميل المحادثة…</p>;
  if (error || !conversation) return <div className="text-center py-20"><p className="mb-6">تعذر فتح المحادثة. تأكد من صلاحية الوصول.</p><Link to="/history" className="text-sky-700">العودة إلى المحادثات</Link></div>;
  const quote = (message_id: string, text: string) => {setReference({message_id, text: text.slice(0, 6000)});};
  const copy = async (messageId: string, content: string) => {
    try {await navigator.clipboard.writeText(content);setCopiedId(messageId);} catch {setCopiedId(null);}
  };
  const actionError = send.error || stop.error || changeBranch.error;
  return <div className={`mx-auto w-full pb-4 ${preview ? 'max-w-[1500px]' : 'max-w-4xl'}`}>
    {conversation.project_id && <Link to={'/projects/' + conversation.project_id} className="block mb-4 text-sm text-sky-700">← العودة إلى مساحة المشروع ولوحته</Link>}
    <header className="flex items-start justify-between gap-3 mb-5 flex-wrap">
      <div className="min-w-0"><h1 className="text-xl font-bold break-words">{conversation.title}</h1><p className="text-xs muted mt-2">ناقش، عدّل، وواصل من حيث وصلت.</p></div>
      <div className="flex gap-3 flex-wrap items-center text-sm text-sky-700">
        <button type="button" aria-pressed={preview} className="flex gap-1 items-center" onClick={() => setPreview(!preview)}><PanelLeft size={17}/>{preview ? 'إخفاء المعاينة' : 'معاينة العمل'}</button>
        <Link to="/" className="flex gap-1 items-center"><Plus size={17}/>محادثة جديدة</Link>
      </div>
    </header>
    <div className="flex items-center justify-between gap-3 flex-wrap mb-5 rounded-xl bg-white/60 px-3 py-2 text-sm">
      <label className="flex items-center gap-2">مسار المحادثة
        <select aria-label="مسار المحادثة" className="rounded-lg border border-sky-100 bg-white p-1 max-w-48" value={conversation.branch_id || 'main'} disabled={!owner || running || pending} onChange={e => changeBranch.mutate(e.target.value)}>
          {(conversation.branches || [{id: 'main', label: 'المسار الأصلي'}]).map(b => <option key={b.id} value={b.id}>{b.label}</option>)}
        </select>
      </label>
      <span className="text-xs muted">تعديل رسالة أو إعادة رد يحفظ المسار السابق.</span>
    </div>
    <div className={preview ? 'grid xl:grid-cols-2 gap-5 items-start' : ''}>
      <main className="min-w-0">
        <div className="space-y-4">
          {conversation.messages.map(message => <article id={message.id} key={message.id} className={`rounded-2xl p-4 md:p-5 border min-w-0 ${message.role === 'user' ? 'ml-4 md:ml-10 bg-white/60 border-sky-100' : 'bg-[#f7fbfe] border-sky-200/60'}`}>
            <div className="flex items-center justify-between gap-3 mb-3 text-sm"><span className="font-bold text-sky-700">{message.role === 'user' ? 'أنت' : '🐜 نمل'}</span><time className="text-[11px] muted">{new Date(message.created_at).toLocaleTimeString('ar-SA', {hour:'2-digit',minute:'2-digit'})}</time></div>
            {message.reference && <blockquote className="text-xs border-r-2 border-sky-400 pr-3 mb-3 text-slate-600 whitespace-pre-wrap max-h-28 overflow-auto">{message.reference.text}</blockquote>}
            {message.status === 'failed' && <p className="text-red-700 mb-3 text-sm">تعذر إكمال هذا الرد. يمكنك إعادة المحاولة.</p>}
            {editing?.id === message.id ? <form onSubmit={e => {e.preventDefault();if (editing.text.trim()) send.mutate({task: editing.text, response_detail:'auto', action:'edit', message_id:message.id});}} className="space-y-3">
              <textarea aria-label="تعديل الرسالة" autoFocus rows={5} maxLength={20000} className="w-full rounded-xl border p-3 bg-white" value={editing.text} onChange={e => setEditing({...editing, text:e.target.value})}/>
              <p className="text-xs muted">سيُنشأ مسار جديد من هذه الرسالة. المحادثة السابقة محفوظة؛ الإجراءات الخارجية لا تُلغى.</p>
              <div className="flex gap-2"><Button type="submit" size="sm" disabled={pending || !editing.text.trim()}>حفظ وإرسال</Button><Button type="button" size="sm" variant="ghost" disabled={pending} onClick={() => setEditing(null)}>إلغاء</Button></div>
            </form> : <div onMouseUp={() => {
              const selection = window.getSelection();
              const text = selection?.toString().trim();
              const article = document.getElementById(message.id);
              if (owner && text && article?.contains(selection?.anchorNode || null) && article.contains(selection?.focusNode || null) && message.content.includes(text)) quote(message.id, text);
            }} className="leading-8 break-words [&_p]:mb-3 [&_h1]:text-2xl [&_h2]:text-xl [&_h3]:font-bold [&_pre]:overflow-auto [&_pre]:bg-slate-100 [&_pre]:p-4 [&_pre]:rounded-xl [&_a]:text-sky-700 [&_ul]:list-disc [&_ul]:pr-5">
              {message.role === 'user' ? <p className="whitespace-pre-wrap">{message.content}</p> : <ReactMarkdown components={{pre: ({children}) => <details className="my-3"><summary className="cursor-pointer text-sm text-sky-700">عرض الكود</summary><pre dir="ltr" className="text-left text-sm">{children}</pre></details>}}>{message.content}</ReactMarkdown>}
            </div>}
            {!editing && <div className="flex items-center flex-wrap gap-3 mt-3 text-xs text-sky-700">
              <button type="button" className="inline-flex items-center gap-1" onClick={() => copy(message.id, message.content)}><Copy size={14}/>{copiedId === message.id ? 'تم النسخ' : 'نسخ'}</button>
              {owner && message.status !== 'cancelled' && <button type="button" className="inline-flex items-center gap-1" onClick={() => quote(message.id, message.content)}><Quote size={14}/>مناقشة هذا</button>}
              {owner && <button type="button" disabled={running || pending} className="inline-flex items-center gap-1 disabled:opacity-40" onClick={() => {
                send.reset();
                if (message.role === 'user') setEditing({id:message.id,text:message.content});
                else send.mutate({task:'إعادة الرد', response_detail:'auto', action:'retry', message_id:message.id});
              }}>{message.role === 'user' ? <Pencil size={14}/> : <RotateCcw size={14}/>} {message.role === 'user' ? 'تعديل' : 'إعادة الرد'}</button>}
              {message.role === 'assistant' && <ExecutionDetails execution={message.execution}/>}
            </div>}
            {message.warnings?.map((warning, i) => <p key={i} className="text-sm text-amber-800 mt-3">{warning}</p>)}
          </article>)}
        </div>
        {running && <div className="py-5 flex items-center justify-between gap-3"><p role="status" className="text-sky-700 animate-pulse text-sm">نمل يُعدّ الرد…</p>{owner && <button type="button" disabled={pending} className="flex gap-2 items-center rounded-lg border bg-white px-3 py-2 text-sm" onClick={() => stop.mutate()}><Square size={14}/>{stop.isPending ? 'جارٍ الإيقاف…' : 'إيقاف الرد'}</button>}</div>}
        <div ref={bottom}/>
        {owner && <div className="sticky bottom-0 pt-4 pb-2 bg-[#eff7fc]/95 mt-4 rounded-t-2xl">
          {reference && <div className="p-3 mb-2 bg-sky-50 border border-sky-100 rounded-xl text-sm"><div className="flex justify-between gap-3"><span className="font-bold">النص المقصود</span><button type="button" aria-label="إزالة النص المحدد" onClick={() => setReference(null)}><X size={16}/></button></div><p className="text-xs whitespace-pre-wrap max-h-24 overflow-auto mt-2">{reference.text}</p></div>}
          <Composer key={id + ':' + conversation.branch_id} draftKey={'naml-draft:' + user?.id + ':' + id + ':' + conversation.branch_id} resetKey={resetKey}
            busy={pending || !!editing} running={running}
            onSend={(task,response_detail) => send.mutate({task,response_detail,...(reference ? {reference} : {})})}
            onInterrupt={(task,response_detail) => send.mutate({task,response_detail,interrupt_session_id:conversation.active_session_id,...(reference ? {reference} : {})})}
            error={actionError ? errorMessage(actionError) : undefined}/>
          {running && <p className="text-xs muted mt-2 px-2">الإيقاف يمنع متابعة الخطوات وحفظ الرد المتأخر؛ قد يكتمل طلب أُرسل بالفعل إلى مزود النموذج.</p>}
        </div>}
      </main>
      {preview && <div className="min-w-0 xl:sticky xl:top-4"><ConversationPreview key={conversation.branch_id} messages={conversation.messages} onQuote={(mid,text) => {if(owner) quote(mid,text);}}/></div>}
    </div>
  </div>;
}
