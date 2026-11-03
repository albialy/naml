import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';

type Capture = { title: string; url: string | null; text: string; screenshot: string | null; blocked_requests: number; truncated: boolean };
export function BrowserPage() {
  const [mode, setMode] = useState<'url' | 'html'>('url');
  const [url, setUrl] = useState('');
  const [html, setHtml] = useState('');
  const [mobile, setMobile] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [result, setResult] = useState<Capture | null>(null);
  const status = useQuery({ queryKey: ['browser-status'], queryFn: async () => (await apiClient.get('/browser/status')).data });
  async function run(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError(''); setResult(null);
    try { setResult((await apiClient.post('/browser/capture', { [mode]: mode === 'url' ? url : html, mobile }, { timeout: 45000 })).data); }
    catch (e: any) { setError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'تعذر عرض الصفحة. راجع الرابط واتصال خدمة المتصفح.'); }
    finally { setBusy(false); }
  }
  return <section className="max-w-5xl mx-auto space-y-6">
    <header><h1 className="text-2xl font-bold">متصفح نمل</h1><p className="muted mt-2">اقرأ صفحة ويب، التقط صورتها، أو عاين تصميم HTML.</p></header>
    {status.isError && <p role="alert">تعذر التحقق من حالة الخدمة. حدّث الصفحة.</p>}
    {status.data && !status.data.configured && <p className="bg-amber-50 p-4 rounded-xl">خدمة المتصفح لم تُفعّل بعد. يجب ربطها من إعدادات الخادم.</p>}
    <form onSubmit={run} className="bg-white/80 rounded-2xl p-5 space-y-4">
      <div className="flex flex-wrap gap-3"><button type="button" aria-pressed={mode === 'url'} onClick={() => {setMode('url');setResult(null);}} className={`rounded-xl px-4 py-2 ${mode === 'url' ? 'bg-sky-100' : ''}`}>رابط موقع</button><button type="button" aria-pressed={mode === 'html'} onClick={() => {setMode('html');setResult(null);}} className={`rounded-xl px-4 py-2 ${mode === 'html' ? 'bg-sky-100' : ''}`}>معاينة HTML</button></div>
      {mode === 'url' ? <label className="block">رابط الصفحة<input required type="url" maxLength={4096} dir="ltr" placeholder="https://example.com" value={url} onChange={e=>setUrl(e.target.value)} className="w-full border rounded-xl p-3 mt-2"/></label> : <label className="block">كود التصميم<textarea required maxLength={200000} dir="ltr" rows={9} value={html} onChange={e=>setHtml(e.target.value)} className="w-full border rounded-xl p-3 mt-2 font-mono text-sm"/><span className="text-xs muted">معاينة HTML وCSS فقط، دون تشغيل JavaScript أو تحميل موارد خارجية.</span></label>}
      <label className="flex items-center gap-2"><input type="checkbox" checked={mobile} onChange={e=>setMobile(e.target.checked)}/>عرض بحجم الهاتف</label>
      <button disabled={busy || !status.data?.configured} className="rounded-xl bg-sky-600 text-white px-6 py-3 disabled:opacity-50">{busy ? 'جارٍ فتح الصفحة…' : 'قراءة وتصوير'}</button>
      <p className="text-xs muted">اللقطة للجزء الظاهر من الصفحة. بعض المواقع قد تمنع التصفح الآلي أو تعرض محتوى ناقصًا.</p>
    </form>
    {error && <p role="alert" className="bg-red-50 p-4 rounded-xl">{error}</p>}
    {result && <article className="space-y-4 min-w-0"><h2 className="font-bold text-xl break-words">{result.title || 'معاينة الصفحة'}</h2>
      {result.url && <p dir="ltr" className="text-xs break-all muted">{result.url}</p>}
      {result.blocked_requests > 0 && <p className="text-sm muted">تعذر تحميل بعض موارد الصفحة؛ قد تكون المعاينة جزئية.</p>}
      {result.screenshot && <><img className="w-full rounded-xl border" src={`data:image/png;base64,${result.screenshot}`} alt="لقطة الصفحة"/><a download="naml-preview.png" href={`data:image/png;base64,${result.screenshot}`} className="inline-block text-sky-700 underline">تنزيل الصورة</a></>}
      <details className="bg-white/80 rounded-xl p-4"><summary>النص المستخرج{result.truncated ? ' (مختصر)' : ''}</summary><pre className="whitespace-pre-wrap break-words text-sm mt-4 font-sans">{result.text || 'لا يوجد نص قابل للاستخراج.'}</pre></details>
    </article>}
  </section>;
}
