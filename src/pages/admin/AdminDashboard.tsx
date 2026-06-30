import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { endpoints } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card';
import { Activity, Users, Zap, CheckCircle2 } from 'lucide-react';

export function AdminDashboard() {
  const { data: users } = useQuery({
    queryKey: ['admin_users'],
    queryFn: async () => {
      const res = await apiClient.get(endpoints.admin.users);
      return res.data;
    }
  });

  const { data: sessions } = useQuery({
    queryKey: ['admin_sessions'],
    queryFn: async () => {
      const res = await apiClient.get(endpoints.history.list);
      return res.data;
    }
  });

  const today = new Date().toISOString().split('T')[0];
  const todaySessions = Array.isArray(sessions) ? sessions.filter((s: any) => s.created_at?.startsWith(today)) : [];
  const avgConfidence = Array.isArray(sessions) && sessions.length > 0 
    ? sessions.reduce((acc: number, s: any) => acc + (s.confidence_final || 0), 0) / sessions.length 
    : 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold mb-6">نظرة عامة</h1>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-6">
            <div className="flex justify-between items-start">
              <div>
                <p className="text-sm text-[#888888] font-medium mb-1">إجمالي المستخدمين</p>
                <h3 className="text-3xl font-bold">{Array.isArray(users) ? users.length : 0}</h3>
              </div>
              <div className="p-2 bg-amber-500/10 rounded-lg">
                <Users className="w-5 h-5 text-[#F5A623]" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex justify-between items-start">
              <div>
                <p className="text-sm text-[#888888] font-medium mb-1">التحليلات اليوم</p>
                <h3 className="text-3xl font-bold">{todaySessions.length}</h3>
              </div>
              <div className="p-2 bg-blue-500/10 rounded-lg">
                <Activity className="w-5 h-5 text-blue-500" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex justify-between items-start">
              <div>
                <p className="text-sm text-[#888888] font-medium mb-1">حالة النظام</p>
                <h3 className="text-xl font-bold text-green-500 mt-2">متصل ومستقر</h3>
              </div>
              <div className="p-2 bg-green-500/10 rounded-lg">
                <CheckCircle2 className="w-5 h-5 text-green-500" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-6">
            <div className="flex justify-between items-start">
              <div>
                <p className="text-sm text-[#888888] font-medium mb-1">متوسط مستوى الثقة</p>
                <h3 className="text-3xl font-bold">{Math.round((avgConfidence || 0) * 100)}%</h3>
              </div>
              <div className="p-2 bg-purple-500/10 rounded-lg">
                <Zap className="w-5 h-5 text-purple-500" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="mt-8">
        <Card>
          <CardHeader>
            <CardTitle>أحدث النشاطات</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-center py-8 text-[#888888]">
              جاري العمل على هذا القسم...
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
