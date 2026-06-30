import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '../api/client';
import { endpoints } from '../api/endpoints';
import { TaskResult, TaskStatus } from '../types';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { ArrowRight, Copy, CheckCircle2, RotateCcw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { motion } from 'motion/react';

const LOADING_MESSAGES = [
  "جاري التحليل...",
  "نمل يعمل...",
  "يتم جمع الأفكار...",
  "اقتربنا من النتيجة..."
];

export function ResultPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [loadingMsgIdx, setLoadingMsgIdx] = useState(0);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setLoadingMsgIdx((prev) => (prev + 1) % LOADING_MESSAGES.length);
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  const { data: sessionData, isLoading: isLoadingSession, error } = useQuery({
    queryKey: ['session', id],
    queryFn: async () => {
      const res = await apiClient.get(endpoints.task.result(id!));
      return res.data;
    },
    refetchInterval: (query) => {
      // If complete or failed, stop polling
      if (query.state.data && (query.state.data.status === 'complete' || query.state.data.status === 'failed')) {
        return false;
      }
      return 2000; // Poll every 2 seconds
    }
  });

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <div className="text-red-500 mb-4 text-4xl">⚠️</div>
        <h2 className="text-xl font-bold mb-2">تعذر العثور على التحليل</h2>
        <p className="text-[#888888] mb-6">قد يكون تم حذفه أو ليس لديك صلاحية الوصول إليه.</p>
        <Button onClick={() => navigate('/')}>العودة للرئيسية</Button>
      </div>
    );
  }

  const isComplete = sessionData?.status === 'complete';
  const isRunning = sessionData?.status && !['complete', 'failed'].includes(sessionData.status);

  if (isLoadingSession || isRunning) {
    return (
      <div className="flex flex-col items-center justify-center py-32 text-center">
        <motion.div 
          animate={{ y: [0, -10, 0] }} 
          transition={{ repeat: Infinity, duration: 1 }}
          className="text-6xl mb-8"
        >
          🐜
        </motion.div>
        <motion.h2 
          key={loadingMsgIdx}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className="text-2xl font-bold text-[#F5A623]"
        >
          {LOADING_MESSAGES[loadingMsgIdx]}
        </motion.h2>
        <div className="mt-8 flex gap-2">
          <span className="w-2 h-2 rounded-full bg-[#F5A623] animate-pulse" style={{ animationDelay: '0ms' }} />
          <span className="w-2 h-2 rounded-full bg-[#F5A623] animate-pulse" style={{ animationDelay: '150ms' }} />
          <span className="w-2 h-2 rounded-full bg-[#F5A623] animate-pulse" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    );
  }

  const handleCopy = () => {
    if (sessionData?.final_synthesis) {
      navigator.clipboard.writeText(sessionData.final_synthesis);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const rawConfidence = sessionData?.confidence_final || 0;
  const displayConfidence = Math.min(100, Math.round(
    rawConfidence > 1 ? rawConfidence : rawConfidence * 100
  ));

  return (
    <div className="max-w-4xl mx-auto w-full pb-20">
      <div className="flex items-center gap-4 mb-8">
        <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="px-2">
          <ArrowRight className="w-5 h-5" />
        </Button>
        <h1 className="text-3xl font-bold tracking-tight">نتيجة التحليل</h1>
      </div>

      <motion.div 
        initial={{ opacity: 0, y: 20 }} 
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
      >
        <Card className="mb-6 border-[#2A2A2A] bg-gradient-to-br from-[#1A1A1A] to-[#111111]">
          <CardContent className="p-6 md:p-8 flex flex-col md:flex-row gap-6 items-start md:items-center justify-between">
            <div className="flex-1">
              <div className="text-[#F5A623] text-sm font-semibold tracking-wider mb-3 uppercase">
                السؤال الأصلي
              </div>
              <p className="text-xl md:text-2xl font-medium leading-relaxed text-white border-r-4 border-[#F5A623] pr-4">
                "{sessionData?.task_original}"
              </p>
            </div>
            {sessionData?.confidence_final !== undefined && (
              <div className="flex flex-col items-center justify-center shrink-0 w-32 h-32 rounded-full border-4 border-[#333333] relative">
                <div 
                  className="absolute inset-0 rounded-full border-4 border-[#F5A623] rounded-full opacity-80"
                  style={{ clipPath: `polygon(0 0, 100% 0, 100% ${displayConfidence}%, 0 ${displayConfidence}%)` }}
                ></div>
                <span className="text-3xl font-bold text-[#F5A623] relative z-10">{displayConfidence}%</span>
                <span className="text-xs text-[#888888] font-medium relative z-10">مستوى الثقة</span>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="mb-8 border-[#F5A623]/20 bg-[#0F0F0F] shadow-2xl">
          <CardContent className="p-8 md:p-10">
            <div className="prose prose-invert max-w-none 
              prose-p:text-lg prose-p:leading-relaxed prose-p:text-gray-300
              prose-headings:text-[#F5A623] prose-headings:font-bold prose-headings:tracking-tight
              prose-h1:text-3xl prose-h2:text-2xl prose-h3:text-xl
              prose-ul:list-none prose-ul:pl-0 prose-ul:space-y-3
              prose-li:relative prose-li:pr-6 prose-li:text-gray-300
              before:prose-li:absolute before:prose-li:right-0 before:prose-li:top-3 before:prose-li:w-2 before:prose-li:h-2 before:prose-li:bg-[#F5A623] before:prose-li:rounded-full
              prose-strong:text-white prose-strong:font-semibold
              prose-pre:bg-[#1A1A1A] prose-pre:border prose-pre:border-[#2A2A2A] prose-pre:rounded-xl">
              <ReactMarkdown>{sessionData?.final_synthesis || 'لا توجد نتيجة'}</ReactMarkdown>
            </div>
          </CardContent>
        </Card>

        <div className="flex flex-wrap gap-4 items-center">
          <Button onClick={handleCopy} variant="secondary" className="gap-2 transition-all hover:scale-105">
            {copied ? <CheckCircle2 className="w-5 h-5 text-green-500" /> : <Copy className="w-5 h-5" />}
            {copied ? 'تم النسخ' : 'نسخ النتيجة'}
          </Button>
          <Button onClick={() => navigate('/')} variant="primary" className="gap-2 transition-all hover:scale-105">
            <RotateCcw className="w-5 h-5" />
            تحليل جديد
          </Button>
          <Button disabled variant="outline" className="gap-2 opacity-50">
            حفظ (قريباً)
          </Button>
        </div>
      </motion.div>
    </div>
  );
}
