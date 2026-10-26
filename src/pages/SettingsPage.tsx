import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { ModelSettings } from "../components/ModelSettings";
import { ModelChoice, apiError } from "../types/project";
import { GitHubAccount } from "../components/GitHubAccount";
export function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const cache = useQueryClient();
  const [saved, setSaved] = useState(false);
  const query = useQuery({
    queryKey: ["preferences", user?.id],
    queryFn: async () => (await apiClient.get("/preferences")).data,
  });
  const save = useMutation({
    mutationFn: async (director: ModelChoice | null) =>
      apiClient.put("/preferences", { director }),
    onSuccess: () => {
      cache.invalidateQueries({ queryKey: ["preferences"] });
      setSaved(true);
    },
  });
  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-3">إعدادات التشغيل</h1>
      <p className="muted mb-8 leading-7">
        اختياراتك محفوظة لحسابك، وتُستخدم في المحادثات الجديدة. يمكنك تخصيص
        نموذج مختلف لكل مشروع.
      </p>
      <div className="glass rounded-3xl p-6">
        {query.isLoading ? (
          <p>جارٍ تحميل الإعدادات…</p>
        ) : query.isError ? (
          <p role="alert">تعذر تحميل الإعدادات.</p>
        ) : (
          <ModelSettings
            key={JSON.stringify(query.data.effective_director)}
            initial={query.data.effective_director}
            models={query.data.available_models}
            busy={save.isPending}
            onSave={(v) => {
              setSaved(false);
              save.mutate(v);
            }}
            onReset={() => save.mutate(null)}
          />
        )}
      </div>
      {saved && !save.isPending && (
        <p role="status" className="text-emerald-700 mt-4">
          تم الحفظ. ستبقى الإعدادات بعد إغلاق الصفحة وإعادة التشغيل.
        </p>
      )}
      {save.error && (
        <p role="alert" className="text-red-700 mt-4">
          {apiError(save.error)}
        </p>
      )}
      {user?.role === "super_admin" && (
        <Link to="/admin/models" className="inline-block mt-8 text-sky-700">
          إعدادات النظام والوكلاء واختبار الاتصال ←
        </Link>
      )}
      <GitHubAccount />
    </div>
  );
}
