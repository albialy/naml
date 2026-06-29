import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../store/authStore';
import { apiClient } from '../api/client';
import { endpoints } from '../api/endpoints';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Card, CardContent } from '../components/ui/Card';
import { motion } from 'motion/react';

export function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { login } = useAuthStore();
  const navigate = useNavigate();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      const response = await apiClient.post(endpoints.auth.login, { username, password });
      
      const token = response.data.access_token || response.data.token;
      const user = response.data.user || {
        id: response.data.id || 'unknown-id',
        username: response.data.username,
        role: response.data.role
      };

      if (!token || !user.username) {
        throw new Error('استجابة غير صالحة من الخادم');
      }
      
      login(token, user);
      
      if (user.role === 'super_admin') {
        navigate('/admin');
      } else {
        navigate('/');
      }
    } catch (err: any) {
      console.error("Login error:", err);
      let errMsg = 'فشل تسجيل الدخول. تأكد من صحة البيانات.';
      if (err.response?.data?.detail?.error) {
        errMsg = err.response.data.detail.error;
      } else if (err.response?.data?.detail && typeof err.response.data.detail === 'string') {
        errMsg = err.response.data.detail;
      } else if (err.message && err.message !== 'Request failed with status code 401') {
        errMsg = err.message;
      }
      setError(errMsg);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0A0A0A] flex items-center justify-center p-4" dir="rtl">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md"
      >
        <div className="text-center mb-8">
          <div className="text-6xl mb-4 text-[#F5A623]">🐜</div>
          <h1 className="text-4xl font-bold text-white mb-2 tracking-tight">نمل <span className="text-[#888888] font-normal mx-2">|</span> NAML</h1>
          <p className="text-[#888888] text-lg font-medium">قوة التفكير الجماعي</p>
        </div>

        <motion.div animate={error ? { x: [-10, 10, -10, 10, 0] } : {}} transition={{ duration: 0.4 }}>
          <Card className="border-[#1E1E1E]">
            <CardContent className="pt-6">
              <form onSubmit={handleLogin} className="space-y-4">
                <div className="space-y-2">
                  <Input 
                    type="text" 
                    placeholder="اسم المستخدم" 
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Input 
                    type="password" 
                    placeholder="كلمة المرور" 
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
                
                {error && (
                  <div className="text-red-500 text-sm text-center bg-red-500/10 p-2 rounded">
                    {error}
                  </div>
                )}

                <Button type="submit" className="w-full" size="lg" isLoading={isLoading}>
                  تسجيل الدخول
                </Button>

                <div className="relative py-4 flex items-center justify-center">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-[#1E1E1E]"></div>
                  </div>
                  <div className="relative bg-[#111111] px-4 text-sm text-[#888888]">
                    أو
                  </div>
                </div>

                <div className="space-y-2">
                  <Button type="button" variant="outline" className="w-full relative opacity-50 cursor-not-allowed">
                    تسجيل الدخول عبر Google
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 bg-[#1E1E1E] text-xs px-2 py-0.5 rounded">قريباً</span>
                  </Button>
                  <Button type="button" variant="outline" className="w-full relative opacity-50 cursor-not-allowed">
                    تسجيل الدخول عبر GitHub
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 bg-[#1E1E1E] text-xs px-2 py-0.5 rounded">قريباً</span>
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>
        </motion.div>
      </motion.div>
    </div>
  );
}
