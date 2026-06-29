import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { endpoints } from '../../api/endpoints';
import { Card, CardContent } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { UserRole } from '../../types';

export function AdminUsers() {
  const { data: users, isLoading } = useQuery({
    queryKey: ['admin_users'],
    queryFn: async () => {
      const res = await apiClient.get(endpoints.admin.users);
      return res.data;
    }
  });

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold mb-2">المستخدمون</h1>
          <p className="text-[#888888] text-sm">إدارة مستخدمي النظام وصلاحياتهم.</p>
        </div>
        <Button>إضافة مستخدم</Button>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-right">
              <thead className="bg-[#1A1A1A] text-[#888888] uppercase border-b border-[#1E1E1E]">
                <tr>
                  <th className="px-6 py-4 font-medium">اسم المستخدم</th>
                  <th className="px-6 py-4 font-medium">الصلاحية</th>
                  <th className="px-6 py-4 font-medium">الحالة</th>
                  <th className="px-6 py-4 font-medium">الحد الأقصى للجلسات</th>
                  <th className="px-6 py-4 font-medium">إجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#1E1E1E]">
                {isLoading ? (
                  <tr><td colSpan={5} className="text-center py-8">جاري التحميل...</td></tr>
                ) : users?.map((user: any) => (
                  <tr key={user.id} className="hover:bg-[#1A1A1A]/50 transition-colors">
                    <td className="px-6 py-4 font-medium">{user.username}</td>
                    <td className="px-6 py-4">
                      <Badge variant={user.role === 'super_admin' ? 'warning' : 'default'}>
                        {user.role}
                      </Badge>
                    </td>
                    <td className="px-6 py-4">
                      <Badge variant={user.is_active ? 'success' : 'danger'}>
                        {user.is_active ? 'نشط' : 'موقوف'}
                      </Badge>
                    </td>
                    <td className="px-6 py-4">{user.session_limit === -1 ? 'غير محدود' : user.session_limit}</td>
                    <td className="px-6 py-4">
                      <div className="flex gap-2">
                        <Button variant="ghost" size="sm">تعديل</Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
