import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, Plus, ArrowUpLeft } from "lucide-react";
import { apiClient } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { Project, projectLabels, apiError } from "../types/project";
import { Button } from "../components/ui/Button";
export function ProjectsPage() {
  const user = useAuthStore((s) => s.user);
  const cache = useQueryClient();
  const navigate = useNavigate();
  const [create, setCreate] = useState(false);
  const [name, setName] = useState("");
  const [goal, setGoal] = useState("");
  const {
    data: projects = [],
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["projects", user?.id],
    queryFn: async () => (await apiClient.get("/projects")).data as Project[],
  });
  const save = useMutation({
    mutationFn: async () =>
      (await apiClient.post("/projects", { name, goal })).data,
    onSuccess: (p) => {
      cache.invalidateQueries({ queryKey: ["projects"] });
      navigate("/projects/" + p.id);
    },
  });
  return (
    <div className="max-w-5xl mx-auto">
      <div className="flex justify-between gap-4 items-start mb-8">
        <div>
          <p className="muted text-sm mb-3">مساحة العمل</p>
          <h1 className="text-3xl font-bold">مشاريعك</h1>
          <p className="muted mt-3 leading-7">
            اجمع المحادثات والقرارات والخطوات التالية في مكان واحد.
          </p>
        </div>
        <Button onClick={() => setCreate(!create)}>
          <Plus size={18} />
          مشروع جديد
        </Button>
      </div>
      {create && (
        <form
          className="glass rounded-3xl p-6 space-y-4 mb-8"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <label className="block space-y-2">
            <span>اسم المشروع</span>
            <input
              autoFocus
              required
              maxLength={100}
              className="glass-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="block space-y-2">
            <span>ما الهدف من المشروع؟</span>
            <textarea
              className="glass-input min-h-24"
              maxLength={3000}
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
            />
          </label>
          <div className="flex gap-3">
            <Button
              type="submit"
              isLoading={save.isPending}
              disabled={!name.trim()}
            >
              إنشاء المشروع
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setCreate(false)}
            >
              إلغاء
            </Button>
          </div>
          {save.error && (
            <p role="alert" className="text-red-700">
              {apiError(save.error)}
            </p>
          )}
        </form>
      )}
      {isLoading && <p className="muted">جارٍ تحميل المشاريع…</p>}
      {isError && (
        <p role="alert" className="text-red-700">
          تعذر تحميل المشاريع.
        </p>
      )}
      <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-5">
        {projects.map((p) => (
          <Link
            key={p.id}
            to={"/projects/" + p.id}
            className="glass rounded-3xl p-6 hover:bg-white transition-colors"
          >
            <div className="flex justify-between mb-7">
              <div className="bg-sky-100 p-3 rounded-2xl text-sky-700">
                <FolderOpen size={24} />
              </div>
              <ArrowUpLeft size={18} />
            </div>
            <p className="text-xs text-sky-700 mb-2">
              {projectLabels[p.project_type]}
            </p>
            <h2 className="font-bold text-xl truncate">{p.name}</h2>
            <p className="muted line-clamp-2 mt-3 text-sm leading-7">
              {p.goal || "أضف هدفك من إعدادات المشروع."}
            </p>
            <p className="muted text-xs border-t border-sky-100 pt-4 mt-5">
              آخر تحديث {new Date(p.updated_at).toLocaleDateString("ar-SA")}
            </p>
          </Link>
        ))}
      </div>
      {!projects.length && !isLoading && !isError && !create && (
        <div className="text-center py-16 glass rounded-3xl">
          <FolderOpen size={42} className="mx-auto text-sky-600 mb-5" />
          <h2 className="text-xl font-bold mb-3">
            مساحة لكل فكرة تستحق المتابعة
          </h2>
          <p className="muted mb-6">
            أنشئ مشروعًا، وابدأ الحوار. ستظهر التفاصيل المتخصصة مع تقدم العمل.
          </p>
          <Button onClick={() => setCreate(true)}>إنشاء أول مشروع</Button>
        </div>
      )}
    </div>
  );
}
