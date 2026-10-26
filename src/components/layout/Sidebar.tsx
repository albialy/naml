import { NavLink, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  Cpu,
  Activity,
  ArrowRight,
} from "lucide-react";
import { cn } from "../../lib/utils";
import { Button } from "../ui/Button";

export function Sidebar() {
  const navigate = useNavigate();

  const navItems = [
    { to: "/admin", icon: LayoutDashboard, label: "لوحة التحكم" },
    { to: "/admin/users", icon: Users, label: "المستخدمون" },
    { to: "/admin/models", icon: Cpu, label: "النماذج والإعدادات" },
    { to: "/admin/logs", icon: Activity, label: "سجل النشاط" },
  ];

  return (
    <aside className="w-64 border-l border-[#cbddea] bg-[#f7fbfe] flex flex-col shrink-0 h-screen sticky top-0">
      <div className="h-16 flex items-center px-6 border-b border-[#cbddea]">
        <span className="text-[#168bd2] text-xl ml-2">🐜</span>
        <span className="font-bold text-lg">نمل | إدارة النظام</span>
      </div>
      <div className="p-4 flex-1 flex flex-col gap-2">
        <Button
          variant="outline"
          size="sm"
          className="mb-4 gap-2 justify-start"
          onClick={() => navigate("/")}
        >
          <ArrowRight className="w-4 h-4" />
          العودة للتطبيق
        </Button>
        <div className="text-xs font-bold text-[#617991] uppercase mb-2 px-2">
          القائمة الرئيسية
        </div>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/admin"}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                isActive
                  ? "bg-amber-500/10 text-[#168bd2] font-medium"
                  : "text-[#617991] hover:bg-[#cbddea] hover:text-slate-800",
              )
            }
          >
            <item.icon className="w-4 h-4" />
            {item.label}
          </NavLink>
        ))}
      </div>
    </aside>
  );
}
