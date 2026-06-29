import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { endpoints } from '../api/endpoints';
import { SessionSummary } from '../types';
import { Card, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { Input } from '../components/ui/Input';
import { Search, Clock, ChevronLeft } from 'lucide-react';
import { motion } from 'motion/react';

export function HistoryPage() {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');

  const { data: history, isLoading } = useQuery({
    queryKey: ['history'],
    queryFn: async () => {
      const res = await apiClient.get(endpoints.history.list);
      return res.data as SessionSummary[];
    }
  });

  const filteredHistory = history?.filter(item => 
    item.task_original.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="max-w-4xl mx-auto w-full pb-20">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-6">سجل التحليلات</h1>
        <div className="relative max-w-md">
          <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[#888888]" />
          <Input 
            placeholder="البحث في السجل..." 
            className="pr-10"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20">
          <span className="w-8 h-8 rounded-full border-2 border-[#F5A623] border-t-transparent animate-spin" />
        </div>
      ) : !filteredHistory?.length ? (
        <div className="text-center py-20 border border-dashed border-[#1E1E1E] rounded-xl bg-[#111111]/50">
          <Clock className="w-12 h-12 text-[#888888] mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-medium text-[#888888]">لا توجد تحليلات سابقة بعد</h3>
        </div>
      ) : (
        <div className="grid gap-4">
          {filteredHistory.map((session, index) => (
            <motion.div
              key={session.session_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
            >
              <Card 
                className="cursor-pointer hover:border-[#F5A623]/50 transition-all hover:bg-[#1A1A1A] group"
                onClick={() => navigate(`/result/${session.session_id}`)}
              >
                <CardContent className="p-5 flex items-center justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-base font-medium line-clamp-1 mb-2 group-hover:text-[#F5A623] transition-colors">
                      {session.task_original}
                    </p>
                    <div className="flex items-center gap-4 text-xs text-[#888888]">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(session.created_at).toLocaleString('ar-SA')}
                      </span>
                      {session.confidence_final && (
                        <Badge variant={session.confidence_final > 0.8 ? "success" : session.confidence_final > 0.5 ? "warning" : "danger"} className="scale-90 origin-right">
                          ثقة {Math.round(session.confidence_final * 100)}%
                        </Badge>
                      )}
                    </div>
                  </div>
                  <ChevronLeft className="w-5 h-5 text-[#333333] group-hover:text-[#F5A623] transition-colors shrink-0" />
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
