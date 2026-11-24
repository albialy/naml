import { useRef, useState, useEffect } from "react";
import { Paperclip, Send } from "lucide-react";
import { Button } from "./ui/Button";
export type ResponseDetail = "auto" | "brief" | "detailed";
export interface ChatRequest { task: string; response_detail: ResponseDetail }
export function Composer({
  onSend,
  busy = false,
  placeholder = "اكتب رسالتك هنا...",
  error,
  prefill,
  resetKey,
  draftKey,
  running = false,
  onInterrupt,
}: {
  onSend: (text: string, detail: ResponseDetail) => void;
  busy?: boolean;
  placeholder?: string;
  error?: string;
  prefill?: string;
  resetKey?: number;
  draftKey?: string;
  running?: boolean;
  onInterrupt?: (text: string, detail: ResponseDetail) => void;
}) {
  const [text, setText] = useState(() => {
    try { return draftKey ? sessionStorage.getItem(draftKey) || "" : ""; } catch { return ""; }
  });
  const previousReset = useRef(resetKey);
  useEffect(() => {
    if (previousReset.current !== resetKey) { setText(""); setFileError(""); previousReset.current = resetKey; }
  }, [resetKey]);
  useEffect(() => {
    if (draftKey) { try { sessionStorage.setItem(draftKey, text); } catch { /* Draft storage may be disabled. */ } }
  }, [text, draftKey]);
  const [detail, setDetail] = useState<ResponseDetail>("auto");
  useEffect(() => {
    if (prefill) setText(prefill);
  }, [prefill]);
  const [fileError, setFileError] = useState("");
  const file = useRef<HTMLInputElement>(null);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (text.trim() && !busy) {
          if (running && onInterrupt) onInterrupt(text.trim(), detail);
          else if (!running) onSend(text.trim(), detail);
        }
      }}
      className="glass rounded-3xl p-4 md:p-5"
    >
      <textarea
        aria-label="رسالتك"
        className="w-full min-h-20 max-h-64 resize-y bg-transparent outline-none text-base leading-8"
        maxLength={20000}
        placeholder={placeholder}
        value={text}
        disabled={busy}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing && e.keyCode !== 229) {
            e.preventDefault();
            if (!e.repeat && text.trim() && !busy && !running) e.currentTarget.form?.requestSubmit();
          }
        }}
      />
      <div className="flex justify-between items-center gap-2 border-t border-sky-100 pt-3">
        <div className="flex items-center gap-2 flex-wrap">
          <input
            ref={file}
            type="file"
            accept=".txt,.md,.csv"
            className="hidden"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (!f) return;
              setFileError("");
              if (!/\.(txt|md|csv)$/i.test(f.name) || f.size > 60000) {
                setFileError(
                  "اختر ملف TXT أو MD أو CSV بحجم أقل من 60 كيلوبايت.",
                );
                return;
              }
              try {
                const content = await f.text();
                setText((previous) => {
                  const next =
                    previous + "\n\nمحتوى الملف " + f.name + ":\n" + content;
                  if (next.length > 20000) {
                    setFileError("محتوى الملف يتجاوز حد الرسالة: 20000 حرف.");
                    return previous;
                  }
                  return next;
                });
              } catch {
                setFileError("تعذرت قراءة الملف.");
              }
            }}
          />
          <Button
            type="button"
            variant="ghost"
            aria-label="إرفاق ملف نصي"
            disabled={busy}
            onClick={() => file.current?.click()}
          >
            <Paperclip size={18} />
          </Button>
          <span className="text-xs muted">
            {text.length.toLocaleString("ar")} / ٢٠٬٠٠٠
          </span>
          <select
            aria-label="تفصيل الإجابة"
            className="rounded-xl border border-sky-100 bg-white/80 px-2 py-1 text-sm"
            value={detail}
            disabled={busy}
            onChange={(e) => setDetail(e.target.value as ResponseDetail)}
          >
            <option value="auto">تفصيل مناسب للسؤال</option>
            <option value="brief">مختصر</option>
            <option value="detailed">تفصيلي</option>
          </select>
        </div>
        <Button type="submit" disabled={busy || !text.trim()} isLoading={busy}>
          <Send size={17} />
          {busy ? "جارٍ الإرسال" : running ? "إيقاف وإرسال التوجيه" : "إرسال"}
        </Button>
      </div>
      <p className="text-xs muted mt-3">
        {running ? "اكتب توجيهك، ثم اضغط إيقاف وإرسال التوجيه لاستكمال الحوار به." : "Enter للإرسال · Shift+Enter لسطر جديد · إرفاق TXT، MD، CSV"}
      </p>
      {(error || fileError) && (
        <p role="alert" className="text-red-700 text-sm mt-3">
          {error || fileError}
        </p>
      )}
    </form>
  );
}
