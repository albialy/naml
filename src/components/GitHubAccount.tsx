import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { githubAuthMessage } from "../lib/githubAuth";
import { Button } from "./ui/Button";

interface Account {enabled: boolean; linked: boolean; login: string | null; password_login: boolean}

export function GitHubAccount() {
  const user = useAuthStore(s => s.user);
  const cache = useQueryClient();
  const [params] = useSearchParams();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const query = useQuery({queryKey: ["github-account", user?.id], queryFn: async () => (await apiClient.get<Account>("/auth/github/account")).data});
  const account = query.data;
  async function submit(e: React.FormEvent) {
    e.preventDefault();setBusy(true);setError("");setMessage("");
    try {
      if (account?.linked) {
        await apiClient.delete("/auth/github/link", {data: {password}});
        setPassword("");setMessage("تم فك ربط GitHub. يمكنك متابعة الدخول بكلمة مرور نمل.");
        await cache.invalidateQueries({queryKey: ["github-account"]});
      } else {
        const {data} = await apiClient.post("/auth/github/link", {password});
        setPassword("");window.location.assign(data.authorization_url);
      }
    } catch (e: any) {setError(githubAuthMessage(e.response?.data?.detail?.code));}
    finally {setBusy(false);}
  }
  return <section className="glass rounded-3xl p-6 mt-8 space-y-4" aria-label="ربط حساب GitHub">
    <h2 className="text-lg font-bold">حساب GitHub</h2>
    <p className="text-sm muted leading-7">اربط GitHub بحسابك الحالي لتدخل إلى المشروعات والمحادثات والصلاحيات نفسها.</p>
    {query.isLoading ? <p role="status">جارٍ التحقق من الربط…</p> : query.isError ? <p role="alert">تعذر تحميل حالة الربط.</p> : account && <>
      {account.linked ? <p className="text-sm">مرتبط بالحساب <a className="text-sky-800 underline" target="_blank" rel="noreferrer" href={"https://github.com/" + encodeURIComponent(account.login || "")}>{account.login}</a></p>
        : <p className="text-sm">لم يُربط حساب GitHub بعد.</p>}
      {!account.enabled && <p className="text-sm muted">بدء الربط يحتاج إعداد GitHub OAuth على الخادم.</p>}
      {account.password_login && (account.enabled || account.linked) ? <form className="space-y-3" onSubmit={submit}>
        <label className="block space-y-2 text-sm"><span>كلمة مرور نمل لتأكيد {account.linked ? "فك الربط" : "الربط"}</span>
          <input aria-label="كلمة مرور نمل لتأكيد الإجراء" className="glass-input w-full" type="password" autoComplete="current-password" required maxLength={1000} value={password} onChange={e => setPassword(e.target.value)}/>
        </label>
        <Button type="submit" isLoading={busy} disabled={!password}>{account.linked ? "فك ربط GitHub" : "ربط حساب GitHub"}</Button>
      </form> : account.linked && <p className="text-sm muted">هذا الحساب يعتمد على GitHub للدخول. لا يمكن فك وسيلة الدخول الوحيدة من هنا.</p>}
    </>}
    {params.get("github") === "linked" && account?.linked && <p role="status" className="text-emerald-800">تم الربط. يمكنك استخدام زر GitHub في تسجيل الدخول القادم.</p>}
    {params.get("github_error") && <p role="alert" className="text-red-700">{githubAuthMessage(params.get("github_error"))}</p>}
    {message && <p role="status" className="text-emerald-800">{message}</p>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
  </section>;
}
