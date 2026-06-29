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

  return (
    <div className="max-w-4xl mx-auto w-full pb-20">
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)} className="px-2">
            <ArrowRight className="w-5 h-5" />
          </Button>
          <h1 className="text-2xl font-bold">نتيجة التحليل</h1>
        </div>
        {sessionData?.confidence_final && (
          <Badge variant={sessionData.confidence_final > 0.8 ? "success" : sessionData.confidence_final > 0.5 ? "warning" : "danger"}>
            مستوى الثقة: {Math.round(sessionData.confidence_final * 100)}%
          </Badge>
        )}
      </div>

      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
        <Card className="mb-6">
          <CardContent className="p-6">
            <div className="text-[#888888] text-sm mb-4 font-medium">السؤال الأصلي:</div>
            <p className="text-lg leading-relaxed">{sessionData?.task_original}</p>
          </CardContent>
        </Card>

        <Card className="mb-8 border-[#F5A623]/30 bg-[#111111]/80 backdrop-blur-sm">
          <CardContent className="p-8 prose prose-invert max-w-none prose-p:leading-relaxed prose-pre:bg-[#0A0A0A] prose-pre:border prose-pre:border-[#1E1E1E]">
            <ReactMarkdown>{sessionData?.final_synthesis || 'لا توجد نتيجة'}</ReactMarkdown>
          </CardContent>
        </Card>

        <div className="flex flex-wrap gap-4 items-center">
          <Button onClick={handleCopy} variant="secondary" className="gap-2">
            {copied ? <CheckCircle2 className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
            {copied ? 'تم النسخ' : 'نسخ النتيجة'}
          </Button>
          <Button onClick={() => navigate('/')} variant="primary" className="gap-2">
            <RotateCcw className="w-4 h-4" />
            تحليل جديد
          </Button>
          <Button disabled variant="outline" className="gap-2 opacity-50">
            حفظ
          </Button>
        </div>
      </motion.div>
    </div>
  );
}
