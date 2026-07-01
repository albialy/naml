import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'motion/react';
import { apiClient } from '../api/client';
import { endpoints } from '../api/endpoints';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import { SessionSummary } from '../types';
import { Clock, Paperclip, X } from 'lucide-react';

const PLACEHOLDERS = [
  "حلل أسباب فشل المشاريع الناشئة...",
  "ما أفضل استراتيجية لدخول سوق جديد؟",
  "كيف أبني فريق عمل متماسك؟",
  "قيّم هذه الفكرة التجارية..."
];

export function HomePage() {
  const [task, setTask] = useState('');
  const [placeholderIndex, setPlaceholderIndex] = useState(0);
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const interval = setInterval(() => {
      setPlaceholderIndex((prev) => (prev + 1) % PLACEHOLDERS.length);
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  const { data: history } = useQuery({
    queryKey: ['history'],
    queryFn: async () => {
      const res = await apiClient.get(endpoints.history.list);
      return res.data as SessionSummary[];
    }
  });

  const createTask = useMutation({
    mutationFn: async (taskText: string) => {
      const res = await apiClient.post(endpoints.task.create, { task: taskText });
      return res.data;
    },
    onSuccess: (data) => {
      navigate(`/result/${data.session_id}`);
    }
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (task.trim()) {
      createTask.mutate(task);
    }
  };

  const handleFilePick = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const isRunning = createTask.isPending;

  return (
    <div className="flex flex-col items-center justify-center flex-1 max-w-3xl mx-auto w-full pb-20 pt-10">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full text-center mb-8"
      >
        <h1 className="text-4xl md:text-5xl font-bold mb-4">ماذا تريد أن تفهم اليوم؟</h1>
        <p className="text-xl text-[#888888]">اكتب سؤالك أو مهمتك بأي لغة وسيقوم نمل بالتفكير وتحليل الإجابة.</p>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 0.1 }}
        className="w-full relative"
      >
        {/* File chips */}
        {files.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {files.map((file, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.05] backdrop-blur-xl px-3 py-1.5 text-xs text-white"
              >
                <Paperclip className="w-3 h-3 text-[#F5A623]" />
                <span className="max-w-[150px] truncate">{file.name}</span>
                <button
                  type="button"
                  onClick={() => removeFile(index)}
                  className="text-white/50 hover:text-white transition-colors"
                >
                  <X className="w-3 h-3" />
                </button>
              </motion.div>
            ))}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="relative rounded-3xl border border-white/10 bg-white/[0.03] backdrop-blur-2xl shadow-[0_8px_40px_rgba(0,0,0,0.4)] overflow-hidden focus-within:ring-2 focus-within:ring-[#F5A623]/50 focus-within:border-[#F5A623]/40 transition-all">
            {/* Specular highlight */}
            <span className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent" />

            <textarea
              className="w-full h-40 bg-transparent text-white p-6 resize-none focus:outline-none text-lg leading-relaxed placeholder:text-transparent"
              value={task}
              onChange={(e) => setTask(e.target.value)}
              maxLength={2000}
              disabled={isRunning}
            />
            {!task && !isRunning && (
              <div className="absolute top-6 right-6 pointer-events-none text-[#888888] text-lg">
                <AnimatePresence mode="wait">
                  <motion.span
                    key={placeholderIndex}
                    initial={{ opacity: 0, y: 5 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -5 }}
                    transition={{ duration: 0.3 }}
                    className="block"
                  >
                    {PLACEHOLDERS[placeholderIndex]}
                  </motion.span>
                </AnimatePresence>
              </div>
            )}

            <div className="absolute bottom-4 left-4 right-4 flex justify-between items-center">
              <div className="flex items-center gap-3">
                <span className="text-xs text-[#888888]">{task.length}/2000</span>
                {/* File attach button */}
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  accept=".pdf,.docx,.xlsx,.txt,.csv,image/*"
                  className="hidden"
                  onChange={handleFilePick}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="flex items-center justify-center h-9 w-9 rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl text-white/60 hover:text-[#F5A623] hover:border-[#F5A623]/40 transition-all"
                  title="إرفاق ملفات"
                >
                  <Paperclip className="w-4 h-4" />
                </button>
              </div>
              <Button
                type="submit"
                size="lg"
                disabled={!task.trim() || isRunning}
                className="px-8 font-bold text-base"
              >
                {isRunning ? (
                  <span className="flex items-center gap-2">
                    <span className="animate-bounce">🐜</span> نمل يفكر...
                  </span>
                ) : (
                  <span>ابدأ التفكير 🐜</span>
                )}
              </Button>
            </div>
          </div>
        </form>
      </motion.div>

      {Array.isArray(history) && history.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="w-full mt-16"
        >
          <div className="flex items-center gap-2 mb-4 text-[#888888]">
            <Clock className="w-4 h-4" />
            <h2 className="text-sm font-medium">آخر تحليلاتك</h2>
          </div>
          <div className="grid gap-3">
            {history.slice(0, 3).map((session) => (
              <Card
                key={session.session_id}
                className="cursor-pointer hover:border-[#F5A623]/50 transition-colors"
                onClick={() => navigate(`/result/${session.session_id}`)}
              >
                <CardContent className="p-4 flex items-center justify-between">
                  <p className="text-sm line-clamp-1 flex-1 ml-4">{session.task_original}</p>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className="text-xs text-[#888888]">
                      {new Date(session.created_at).toLocaleDateString('ar-SA')}
                    </span>
                    <span className={`w-2 h-2 rounded-full ${session.status === 'complete' ? 'bg-green-500' : 'bg-amber-500'}`} />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
