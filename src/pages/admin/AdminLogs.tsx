import { Card, CardContent } from "../../components/ui/Card";

export function AdminLogs() {
  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold mb-2">سجل النشاط</h1>
          <p className="text-[#617991] text-sm">
            مراقبة جميع التغييرات التي تمت على النظام.
          </p>
        </div>
      </div>

      <Card>
        <CardContent className="p-12 text-center text-[#617991]">
          جاري العمل على هذا القسم... (قريباً)
        </CardContent>
      </Card>
    </div>
  );
}
