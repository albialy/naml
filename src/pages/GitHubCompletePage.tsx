import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiClient } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { githubAuthMessage } from "../lib/githubAuth";

export function GitHubCompletePage() {
  const started = useRef(false);
  const [error, setError] = useState("");
  const login = useAuthStore(s => s.login);
  const navigate = useNavigate();
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    apiClient.post("/auth/github/complete").then(({data}) => {
      login(data.access_token, data.user);
      navigate("/", {replace: true});
    }).catch(e => setError(githubAuthMessage(e.response?.data?.detail?.code)));
  }, [login, navigate]);
  return <main dir="rtl" className="min-h-screen bg-[#eaf4fa] flex items-center justify-center p-5">
    <div className="glass rounded-3xl p-8 max-w-md w-full text-center space-y-5">
      <h1 className="text-xl font-bold">تسجيل الدخول عبر GitHub</h1>
      {error ? <><p role="alert" className="text-red-700 leading-7">{error}</p><Link className="text-sky-800 underline" to="/login">العودة إلى تسجيل الدخول</Link></>
        : <p role="status">جارٍ إكمال تسجيل الدخول…</p>}
    </div>
  </main>;
}
