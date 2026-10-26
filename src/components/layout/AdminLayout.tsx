import { Outlet, Navigate, NavLink, Link } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { Sidebar } from "./Sidebar";

export function AdminLayout() {
  const { user, isAuthenticated } = useAuthStore();

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user?.role !== "super_admin") return <Navigate to="/" replace />;

  return (
    <div
      className="min-h-screen bg-[#eaf4fa] text-slate-800 lg:flex font-sans"
      dir="rtl"
    >
      <div className="hidden lg:block shrink-0"><Sidebar /></div>
      <div className="lg:hidden border-b border-sky-200 p-4 space-y-3">
        <div className="flex justify-between items-center"><strong>نمل | إدارة النظام</strong><Link to="/" className="text-sm text-sky-700">العودة للتطبيق</Link></div>
        <nav aria-label="إدارة النظام" className="flex flex-wrap gap-2">
          {[["/admin", "لوحة التحكم"], ["/admin/users", "المستخدمون"], ["/admin/models", "النماذج والإعدادات"], ["/admin/logs", "سجل النشاط"]].map(([to, label]) =>
            <NavLink key={to} to={to} end={to === "/admin"} className={({isActive}) => `rounded-xl px-3 py-2 text-sm ${isActive ? "bg-sky-100 text-sky-800 font-bold" : "bg-white/70 text-slate-600"}`}>{label}</NavLink>)}
        </nav>
      </div>
      <main className="flex-1 min-w-0">
        <div className="max-w-6xl mx-auto p-4 md:p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
