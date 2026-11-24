import { useMemo, useState } from 'react';
import { Monitor, Smartphone, Download, Camera } from 'lucide-react';
import { ConversationMessage } from '../types';
import { apiClient } from '../api/client';

export interface HtmlVersion { id: string; messageId: string; html: string; label: string }
export function htmlVersions(messages: ConversationMessage[]): HtmlVersion[] {
  const versions: HtmlVersion[] = [];
  for (const message of messages) {
    if (message.role !== 'assistant' || message.status !== 'complete') continue;
    for (const match of message.content.matchAll(/```html\s*\n([\s\S]*?)```/gi)) {
      if (match[1].length <= 200000 && /<(?:html|body|div|section|main|!doctype)\b/i.test(match[1])) {
        versions.push({ id: message.id + ':' + match.index, messageId: message.id, html: match[1], label: 'نسخة ' + (versions.length + 1) });
      }
    }
  }
  return versions;
}

export function ConversationPreview({ messages, onQuote }: {
  messages: ConversationMessage[];
  onQuote: (messageId: string, text: string) => void;
}) {
  const versions = useMemo(() => htmlVersions(messages), [messages]);
  const [selected, setSelected] = useState('');
  const [mobile, setMobile] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [shot, setShot] = useState<{id: string; png: string} | null>(null);
  const active = versions.find(v => v.id === selected) || versions[versions.length - 1];
  if (!active) return <aside className="glass rounded-2xl p-6 text-sm leading-7">
    <h2 className="font-bold text-lg mb-2">معاينة العمل</h2>
    <p>عندما يرسل نمل تصميمًا في كتلة HTML، ستظهر معاينته ونسخه هنا. يمكنك تحديد نص داخل المعاينة ومناقشته.</p>
    <p className="muted mt-3">المعاينة تدعم HTML وCSS. التصفح الحي للمواقع وتشغيل تطبيقات JavaScript ليسا متاحين في هذه اللوحة بعد.</p>
  </aside>;
  // Parsed in an inert document. Remove active/external navigation before srcDoc.
  const template = document.createElement('template');
  template.innerHTML = active.html;
  const parsed = template.content;
  parsed.querySelectorAll('script, iframe, frame, object, embed, base, meta[http-equiv]').forEach(n => n.remove());
  parsed.querySelectorAll('*').forEach(node => {
    for (const attr of [...node.attributes]) {
      if (attr.name.toLowerCase().startsWith('on') || ['href', 'action', 'formaction', 'srcdoc'].includes(attr.name.toLowerCase())) node.removeAttribute(attr.name);
    }
  });
  const policy = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; font-src data:; form-action 'none'; base-uri 'none'";
  const documentHtml = '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="' + policy + '"></head><body>' + template.innerHTML + '</body></html>';
  async function capture() {
    setBusy(true); setError(''); setShot(null);
    const versionId = active.id;
    try {
      const result = await apiClient.post('/browser/capture', { html: active.html, mobile }, { timeout: 125000 });
      if (!result.data.screenshot) throw new Error('no screenshot');
      setShot({ id: versionId, png: result.data.screenshot });
    } catch (e: any) {
      setError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'تعذر التصوير. تحقق من إعداد خدمة المتصفح.');
    } finally { setBusy(false); }
  }
  function download() {
    const url = URL.createObjectURL(new Blob([active.html], { type: 'text/html;charset=utf-8' }));
    const a = document.createElement('a'); a.href = url; a.download = 'naml-preview.html'; a.click(); URL.revokeObjectURL(url);
  }
  return <aside className="glass rounded-2xl overflow-hidden">
    <div className="p-4 space-y-3 border-b border-sky-100">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-bold">معاينة العمل</h2>
        <select aria-label="نسخة المعاينة" className="bg-white border rounded-lg p-1 max-w-full" value={active.id} onChange={e => {setSelected(e.target.value);setShot(null);setError('');}}>
          {versions.map(v => <option key={v.id} value={v.id}>{v.label}{v.id === versions.at(-1)?.id ? ' · الأحدث' : ''}</option>)}
        </select>
      </div>
      <div className="flex items-center gap-3 flex-wrap text-sm">
        <button type="button" className="flex gap-1 items-center" onClick={() => {setMobile(!mobile);setShot(null);}}>{mobile ? <Monitor size={16}/> : <Smartphone size={16}/>} {mobile ? 'كمبيوتر' : 'هاتف'}</button>
        <button type="button" className="flex gap-1 items-center" onClick={download}><Download size={16}/>تنزيل HTML</button>
        <button type="button" className="flex gap-1 items-center disabled:opacity-50" disabled={busy} onClick={capture}><Camera size={16}/>{busy ? 'جارٍ التصوير…' : 'تصوير بـ Chromium'}</button>
      </div>
      <p className="text-xs muted">حدّد نصًا داخل المعاينة لإرفاقه برسالتك. اختيار نسخة قديمة يعرضها فقط؛ اطلب من نمل اعتمادها أو تعديلها في رسالة جديدة.</p>
    </div>
    <div className="bg-slate-100 p-2 overflow-auto">
      <iframe key={active.id} title="معاينة HTML" sandbox="allow-same-origin" referrerPolicy="no-referrer"
        srcDoc={documentHtml} className="bg-white border-0 mx-auto h-[500px] max-w-full" style={{width: mobile ? 390 : '100%'}}
        onLoad={e => {
          const doc = e.currentTarget.contentDocument;
          doc?.addEventListener('mouseup', () => {
            const selection = doc.getSelection()?.toString().trim();
            if (selection && active.html.includes(selection)) onQuote(active.messageId, selection.slice(0, 6000));
          });
        }}/>
    </div>
    {error && <p role="alert" className="p-3 text-red-700 text-sm">{error}</p>}
    {shot?.id === active.id && <a className="block p-3 text-sky-700 underline" download="naml-preview.png" href={'data:image/png;base64,' + shot.png}>تنزيل لقطة Chromium</a>}
    <p className="p-3 text-xs muted">HTML وCSS فقط؛ السكربتات والموارد الخارجية معطلة في المعاينة.</p>
  </aside>;
}
