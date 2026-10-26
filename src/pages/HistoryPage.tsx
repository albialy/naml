import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import { endpoints } from "../api/endpoints";
import { ConversationSummary } from "../types";
import { Card, CardContent } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Input } from "../components/ui/Input";
import { Search, Clock, ChevronLeft } from "lucide-react";
import { motion } from "motion/react";
import { useAuthStore } from "../store/authStore";

export function HistoryPage() {
  const navigate = useNavigate();
  const user = useAuthStore((state) => state.user);
  const [searchTerm, setSearchTerm] = useState("");

  const {
    data: history,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["conversations", user?.id],
    queryFn: async () => {
      const res = await apiClient.get(endpoints.conversations.list);
      return res.data as ConversationSummary[];
    },
  });

  const filteredHistory = Array.isArray(history)
    ? history.filter((item) =>
        item.title.toLowerCase().includes(searchTerm.toLowerCase()),
      )
    : [];

  return (
    <div className="max-w-4xl mx-auto w-full pb-20">
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-6">المحادثات المحفوظة</h1>
        <div className="relative max-w-md">
          <Search className="absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-[#617991]" />
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
          <span className="w-8 h-8 rounded-full border-2 border-[#168bd2] border-t-transparent animate-spin" />
        </div>
      ) : isError ? (
        <p role="alert" className="text-red-700">
          تعذر تحميل المحادثات. تحقق من الاتصال ثم حدّث الصفحة.
        </p>
      ) : !filteredHistory?.length ? (
        <div className="text-center py-20 border border-dashed border-[#cbddea] rounded-xl bg-[#f7fbfe]/50">
          <Clock className="w-12 h-12 text-[#617991] mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-medium text-[#617991]">
            لا توجد محادثات محفوظة بعد
          </h3>
        </div>
      ) : (
        <div className="grid gap-4">
          {filteredHistory.map((session, index) => (
            <motion.div
              key={session.conversation_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.05 }}
            >
              <Card
                className="cursor-pointer hover:border-[#168bd2]/50 transition-all hover:bg-[#edf6fc] group"
                onClick={() =>
                  navigate(`/conversation/${session.conversation_id}`)
                }
              >
                <CardContent className="p-5 flex items-center justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <p className="text-base font-medium line-clamp-1 mb-2 group-hover:text-[#168bd2] transition-colors">
                      {session.title}
                    </p>
                    <div className="flex items-center gap-4 text-xs text-[#617991]">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" />
                        {new Date(session.updated_at).toLocaleString("ar-SA")}
                      </span>
                      <Badge
                        variant={
                          session.status === "complete"
                            ? "success"
                            : session.status === "failed"
                              ? "danger"
                              : "warning"
                        }
                      >
                        {session.message_count} رسالة
                      </Badge>
                    </div>
                  </div>
                  <ChevronLeft className="w-5 h-5 text-[#617991] group-hover:text-[#168bd2] transition-colors shrink-0" />
                </CardContent>
              </Card>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
