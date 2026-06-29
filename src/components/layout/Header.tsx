import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { LogOut, Home, History, Settings } from 'lucide-react';
import { Button } from '../ui/Button';

export function Header() {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="h-16 border-b border-[#1E1E1E] bg-[#111111] flex items-center justify-between px-6 shrink-0 z-10 sticky top-0">
      <div className="flex items-center gap-6">
        <div className="flex items-center gap-2 cursor-pointer" onClick={() => navigate('/')}>
          <span className="text-[#F5A623] text-xl">🐜</span>
          <span className="font-bold text-xl tracking-tight">نمل <span className="text-[#888888] font-normal mx-2">|</span> NAML</span>
        </div>
        <nav className="hidden md:flex items-center gap-1 ml-4">
          <Button variant="ghost" size="sm" onClick={() => navigate('/')} className="gap-2">
            <Home className="w-4 h-4" />
            الرئيسية
          </Button>
          <Button variant="ghost" size="sm" onClick={() => navigate('/history')} className="gap-2">
            <History className="w-4 h-4" />
            السجل
          </Button>
          {user?.role === 'super_admin' && (
            <Button variant="ghost" size="sm" onClick={() => navigate('/admin')} className="gap-2 text-amber-400">
              <Settings className="w-4 h-4" />
              الإدارة
            </Button>
          )}
        </nav>
      </div>
      <div className="flex items-center gap-4">
        <div className="text-sm flex flex-col items-end hidden sm:flex">
          <span className="text-white font-medium">{user?.username}</span>
          <span className="text-[#888888] text-xs capitalize">{user?.role === 'super_admin' ? 'مدير النظام' : user?.role === 'operator' ? 'موظف' : 'مستخدم'}</span>
        </div>
        <Button variant="ghost" size="sm" onClick={handleLogout} className="text-[#888888] hover:text-red-400">
          <LogOut className="w-4 h-4" />
        </Button>
      </div>
    </header>
  );
}
