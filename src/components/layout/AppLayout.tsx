import { AntMark } from "../AntMark";
import { useState } from "react";
import {
  Outlet,
  Navigate,
  NavLink,
  Link,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  MessageSquare,
  FolderOpen,
  Settings,
  LogOut,
  Menu,
  X,
  Shield,
  Home,
} from "lucide-react";
import { useAuthStore } from "../../store/authStore";
import { apiClient } from "../../api/client";
import { ConversationSummary } from "../../types";
import { Button } from "../ui/Button";
export function AppLayout() {
  const { isAuthenticated, user, logout } = useAuthStore();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const cache = useQueryClient();
  const { data: chats = [] } = useQuery({
    queryKey: ["conversations", user?.id],
    queryFn: async () =>
      (await apiClient.get("/conversations")).data as ConversationSummary[],
    enabled: isAuthenticated,
  });
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  const nav = [
    { to: "/", label: "الرئيسية", icon: Home },
    { to: "/history", label: "المحادثات", icon: MessageSquare },
    { to: "/projects", label: "المشاريع", icon: FolderOpen },
    { to: "/settings", label: "الإعدادات", icon: Settings },
  ];
  return (
    <div dir="rtl" className="min-h-screen p-2 md:p-5 font-sans">
      <div className="lg:hidden flex justify-between items-center px-3 py-2">
        <Link to="/" className="text-xl font-bold flex items-center gap-2">
          <AntMark className="w-7 h-7" /> نمل
        </Link>
        <Button
          aria-label={open ? "إغلاق القائمة" : "فتح القائمة"}
          aria-expanded={open}
          variant="ghost"
          onClick={() => setOpen(!open)}
        >
          {open ? <X size={20} /> : <Menu size={20} />}
        </Button>
      </div>
      {open && (
        <button
          aria-label="إغلاق القائمة"
          onClick={() => setOpen(false)}
          className="fixed inset-0 bg-slate-900/20 z-30 lg:hidden"
        />
      )}
      <aside
        className={`glass rounded-[28px] w-64 flex flex-col fixed top-16 bottom-3 right-3 lg:top-5 lg:right-5 lg:bottom-5 z-40 p-5 ${open ? "flex" : "hidden lg:flex"}`}
      >
        <Link
          to="/"
          onClick={() => setOpen(false)}
          className="flex items-center gap-3 px-3 pt-3 pb-7"
        >
          <AntMark />
          <div>
            <strong className="text-3xl">نمل</strong>
            <p className="text-xs muted mt-1">أفكار أوضح، معًا</p>
          </div>
        </Link>
        <Link
          to="/"
          onClick={() => {
            setOpen(false);
            navigate("/");
          }}
          className="flex items-center justify-center gap-2 bg-sky-200/70 hover:bg-sky-200 rounded-2xl p-3 font-bold mb-5"
        >
          <Plus size={19} />
          محادثة جديدة
        </Link>
        <nav className="space-y-1">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              onClick={() => setOpen(false)}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-xl text-sm ${isActive ? "bg-white/85 text-sky-800 font-bold shadow-sm" : "muted hover:bg-white/60"}`
              }
            >
              <item.icon size={19} />
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-sky-200/60 mt-5 pt-4 flex-1 min-h-0 overflow-auto">
          <p className="muted text-xs mb-3 px-3">المحادثات الأخيرة</p>
          {chats.slice(0, 8).map((c) => (
            <Link
              onClick={() => setOpen(false)}
              key={c.conversation_id}
              to={`/conversation/${c.conversation_id}`}
              className={`block text-sm truncate rounded-xl px-3 py-3 mb-1 ${location.pathname.includes(c.conversation_id) ? "bg-sky-100" : "hover:bg-white/60"}`}
            >
              {c.title}
            </Link>
          ))}
          {!chats.length && (
            <p className="text-xs muted px-3 leading-6">
              ستجد محادثاتك هنا بعد البدء.
            </p>
          )}
        </div>
        {user?.role === "super_admin" && (
          <Link
            to="/admin"
            className="flex gap-2 items-center text-xs muted py-3"
          >
            <Shield size={15} />
            إدارة النظام
          </Link>
        )}
        <div className="border-t border-sky-200/60 pt-4 flex items-center justify-between">
          <div>
            <p className="font-bold text-sm">{user?.username}</p>
            <p className="text-xs muted">مساحتك الشخصية</p>
          </div>
          <Button
            aria-label="تسجيل الخروج"
            variant="ghost"
            onClick={async () => {
              try {
                await apiClient.post("/auth/logout");
              } finally {
                cache.clear();
                logout();
                navigate("/login");
              }
            }}
          >
            <LogOut size={17} />
          </Button>
        </div>
      </aside>
      <main className="lg:mr-[280px] min-w-0">
        <div className="glass rounded-[28px] min-h-[calc(100vh-40px)] p-5 md:p-8 xl:p-10">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
