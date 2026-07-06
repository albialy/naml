import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../../api/client';
import { endpoints } from '../../api/endpoints';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Badge } from '../../components/ui/Badge';
import { Activity, Plus, Trash2, Save, CheckCircle2, XCircle } from 'lucide-react';

export function AdminModels() {
  const queryClient = useQueryClient();
  const [testResults, setTestResults] = useState<Record<string, { connected: boolean; latency: number }>>({});
  const [testingProvider, setTestingProvider] = useState<string | null>(null);

  const [editingWorker, setEditingWorker] = useState<string | null>(null);
  const [workerForm, setWorkerForm] = useState({ provider: '', model: '', temperature: 0.5, max_tokens: 2048 });

  const [addingWorker, setAddingWorker] = useState(false);
  const [newWorkerForm, setNewWorkerForm] = useState({ name: '', provider: '', model: '', temperature: 0.5, max_tokens: 2048 });

  const [editingDirector, setEditingDirector] = useState(false);
  const [directorForm, setDirectorForm] = useState({ provider: 'groq', model: '', temperature: 0.3, max_tokens: 4096 });

  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: async () => {
      const res = await apiClient.get(endpoints.admin.settings);
      return res.data;
    }
  });

  const { data: availableModels } = useQuery({
    queryKey: ['available_models'],
    queryFn: async () => {
      const res = await apiClient.get(endpoints.admin.availableModels);
      return res.data;
    }
  });

  const testConnection = async (provider: string) => {
    setTestingProvider(provider);
    try {
      const res = await apiClient.get(endpoints.admin.testConnection(provider));
      setTestResults(prev => ({ ...prev, [provider]: { connected: res.data.connected, latency: res.data.latency_ms } }));
    } catch (e) {
      setTestResults(prev => ({ ...prev, [provider]: { connected: false, latency: 0 } }));
    } finally {
      setTestingProvider(null);
    }
  };

  const updateWorker = useMutation({
    mutationFn: async ({ type, data }: { type: string, data: any }) => {
      await apiClient.put(endpoints.admin.settingsWorker(type), data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setEditingWorker(null);
    }
  });

  const addWorker = useMutation({
    mutationFn: async (data: any) => {
      await apiClient.post(endpoints.admin.settingsWorkers, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setAddingWorker(false);
      setNewWorkerForm({ name: '', provider: '', model: '', temperature: 0.5, max_tokens: 2048 });
    }
  });

  const deleteWorker = useMutation({
    mutationFn: async (type: string) => {
      await apiClient.delete(endpoints.admin.settingsWorker(type));
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    }
  });

  const updateDirector = useMutation({
    mutationFn: async (data: any) => {
      await apiClient.put(endpoints.admin.settingsDirector, data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setEditingDirector(false);
    }
  });

  if (!settings) return <div className="py-20 text-center">جاري التحميل...</div>;

  return (
    <div className="space-y-8 pb-20">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold mb-2">النماذج والإعدادات</h1>
          <p className="text-[#888888] text-sm">إدارة نماذج الذكاء الاصطناعي وإعدادات النظام بدون الحاجة لتعديل الكود.</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="w-5 h-5 text-[#F5A623]" />
            حالة الاتصال بمزودي الخدمة
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid md:grid-cols-2 gap-4">
            {['groq', 'openrouter'].map(provider => (
              <div key={provider} className="flex items-center justify-between p-4 bg-[#1A1A1A] rounded-lg border border-[#1E1E1E]">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 bg-[#111111] rounded flex items-center justify-center font-bold capitalize">
                    {provider[0]}
                  </div>
                  <div>
                    <div className="font-medium capitalize">{provider}</div>
                    {testResults[provider] ? (
                      <div className={`text-xs flex items-center gap-1 mt-1 ${testResults[provider].connected ? 'text-green-500' : 'text-red-500'}`}>
                        {testResults[provider].connected ? <CheckCircle2 className="w-3 h-3" /> : <XCircle className="w-3 h-3" />}
                        {testResults[provider].connected ? `متصل (${testResults[provider].latency}ms)` : 'خطأ في الاتصال'}
                      </div>
                    ) : (
                      <div className="text-xs text-[#888888] mt-1">لم يتم الاختبار</div>
                    )}
                  </div>
                </div>
                <Button 
                  variant="outline" 
                  size="sm" 
                  isLoading={testingProvider === provider}
                  onClick={() => testConnection(provider)}
                >
                  اختبار
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>النموذج الموجه (Director)</CardTitle>
          {!editingDirector && (
            <Button variant="outline" size="sm" onClick={() => {
              setEditingDirector(true);
              setDirectorForm({
                provider: settings.director?.provider || 'groq',
                model: settings.director?.model || '',
                temperature: settings.director?.temperature ?? 0.3,
                max_tokens: settings.director?.max_tokens ?? 4096
              });
            }}>
              تعديل
            </Button>
          )}
        </CardHeader>
        <CardContent>
          <div className="text-[#888888] mb-4">هذا النموذج مسؤول عن تخطيط المهام وتلخيص النتائج. التغيير يسري فوراً على التحليلات الجديدة.</div>
          {editingDirector ? (
            <div className="bg-[#1A1A1A] p-4 rounded-lg border border-[#F5A623] space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <select
                  className="flex h-10 w-full rounded-md border border-[#1E1E1E] bg-[#111111] px-3 py-2 text-sm text-white"
                  value={directorForm.provider}
                  onChange={e => setDirectorForm({...directorForm, provider: e.target.value, model: ''})}
                >
                  <option value="groq">Groq</option>
                  <option value="openrouter">OpenRouter</option>
                </select>
                <select
                  className="flex h-10 w-full rounded-md border border-[#1E1E1E] bg-[#111111] px-3 py-2 text-sm text-white"
                  value={directorForm.model}
                  onChange={e => setDirectorForm({...directorForm, model: e.target.value})}
                >
                  <option value="">اختر النموذج</option>
                  {directorForm.provider && availableModels?.[directorForm.provider]?.map((m: string) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
                <Input
                  type="number" step="0.1" max="1" min="0" placeholder="Temperature"
                  value={directorForm.temperature}
                  onChange={e => setDirectorForm({...directorForm, temperature: parseFloat(e.target.value)})}
                />
                <Input
                  type="number" placeholder="Max Tokens"
                  value={directorForm.max_tokens}
                  onChange={e => setDirectorForm({...directorForm, max_tokens: parseInt(e.target.value)})}
                />
              </div>
              <div className="flex gap-2 justify-end">
                <Button variant="ghost" size="sm" onClick={() => setEditingDirector(false)}>إلغاء</Button>
                <Button size="sm" onClick={() => updateDirector.mutate(directorForm)} isLoading={updateDirector.isPending} disabled={!directorForm.model} className="gap-2">
                  <Save className="w-4 h-4" />
                  حفظ
                </Button>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 mb-4">
              <div className="bg-[#1A1A1A] p-4 rounded-lg border border-[#1E1E1E]">
                <div className="text-xs text-[#888888] mb-1">المزود</div>
                <div className="font-medium capitalize">{settings.director?.provider}</div>
              </div>
              <div className="bg-[#1A1A1A] p-4 rounded-lg border border-[#1E1E1E]">
                <div className="text-xs text-[#888888] mb-1">النموذج</div>
                <div className="font-medium">{settings.director?.model}</div>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
      
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>النماذج العاملة (Workers)</CardTitle>
          <Button size="sm" onClick={() => setAddingWorker(true)} className="gap-2" disabled={addingWorker}>
            <Plus className="w-4 h-4" />
            إضافة نموذج
          </Button>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4">
            {addingWorker && (
              <div className="bg-[#1A1A1A] p-4 rounded-lg border border-[#F5A623] space-y-4">
                <h4 className="font-bold text-sm">إضافة نموذج جديد</h4>
                <div className="grid grid-cols-2 gap-4">
                  <Input 
                    placeholder="اسم النموذج (مثال: creative)" 
                    value={newWorkerForm.name} 
                    onChange={e => setNewWorkerForm({...newWorkerForm, name: e.target.value})} 
                  />
                  <select 
                    className="flex h-10 w-full rounded-md border border-[#1E1E1E] bg-[#111111] px-3 py-2 text-sm text-white"
                    value={newWorkerForm.provider}
                    onChange={e => setNewWorkerForm({...newWorkerForm, provider: e.target.value, model: ''})}
                  >
                    <option value="">اختر المزود</option>
                    <option value="groq">Groq</option>
                    <option value="openrouter">OpenRouter</option>
                  </select>
                  <select 
                    className="flex h-10 w-full rounded-md border border-[#1E1E1E] bg-[#111111] px-3 py-2 text-sm text-white"
                    value={newWorkerForm.model}
                    onChange={e => setNewWorkerForm({...newWorkerForm, model: e.target.value})}
                  >
                    <option value="">اختر النموذج</option>
                    {newWorkerForm.provider && availableModels?.[newWorkerForm.provider]?.map((m: string) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <Input 
                    type="number" step="0.1" max="1" min="0" placeholder="درجة الإبداع (Temperature)"
                    value={newWorkerForm.temperature}
                    onChange={e => setNewWorkerForm({...newWorkerForm, temperature: parseFloat(e.target.value)})}
                  />
                </div>
                <div className="flex gap-2 justify-end">
                  <Button variant="ghost" size="sm" onClick={() => setAddingWorker(false)}>إلغاء</Button>
                  <Button size="sm" onClick={() => addWorker.mutate(newWorkerForm)} isLoading={addWorker.isPending}>حفظ الإضافة</Button>
                </div>
              </div>
            )}

            {Object.entries(settings.workers || {}).map(([key, worker]: [string, any]) => (
              editingWorker === key ? (
                <div key={key} className="bg-[#1A1A1A] p-4 rounded-lg border border-[#F5A623] space-y-4">
                  <h4 className="font-bold text-sm capitalize">تعديل {key}</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <select 
                      className="flex h-10 w-full rounded-md border border-[#1E1E1E] bg-[#111111] px-3 py-2 text-sm text-white"
                      value={workerForm.provider}
                      onChange={e => setWorkerForm({...workerForm, provider: e.target.value, model: ''})}
                    >
                      <option value="groq">Groq</option>
                      <option value="openrouter">OpenRouter</option>
                    </select>
                    <select 
                      className="flex h-10 w-full rounded-md border border-[#1E1E1E] bg-[#111111] px-3 py-2 text-sm text-white"
                      value={workerForm.model}
                      onChange={e => setWorkerForm({...workerForm, model: e.target.value})}
                    >
                      <option value="">اختر النموذج</option>
                      {workerForm.provider && availableModels?.[workerForm.provider]?.map((m: string) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                    <Input 
                      type="number" step="0.1" max="1" min="0" placeholder="Temperature"
                      value={workerForm.temperature}
                      onChange={e => setWorkerForm({...workerForm, temperature: parseFloat(e.target.value)})}
                    />
                    <Input 
                      type="number" placeholder="Max Tokens"
                      value={workerForm.max_tokens}
                      onChange={e => setWorkerForm({...workerForm, max_tokens: parseInt(e.target.value)})}
                    />
                  </div>
                  <div className="flex gap-2 justify-end">
                    <Button variant="ghost" size="sm" onClick={() => setEditingWorker(null)}>إلغاء</Button>
                    <Button size="sm" onClick={() => updateWorker.mutate({ type: key, data: workerForm })} isLoading={updateWorker.isPending}>حفظ والتحديث</Button>
                  </div>
                </div>
              ) : (
                <div key={key} className="flex justify-between items-center bg-[#1A1A1A] p-4 rounded-lg border border-[#1E1E1E]">
                  <div>
                    <div className="font-medium capitalize flex items-center gap-2">
                      {key}
                      <Badge variant="outline">{worker.provider}</Badge>
                    </div>
                    <div className="text-sm text-[#888888] mt-1">{worker.model} <span className="mx-2">•</span> الحرارة: {worker.temperature}</div>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => {
                      setEditingWorker(key);
                      setWorkerForm({ provider: worker.provider, model: worker.model, temperature: worker.temperature, max_tokens: worker.max_tokens });
                    }}>
                      تعديل
                    </Button>
                    <Button variant="danger" size="sm" onClick={() => deleteWorker.mutate(key)} isLoading={deleteWorker.isPending && deleteWorker.variables === key}>
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              )
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
