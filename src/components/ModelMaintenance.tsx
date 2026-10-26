import {useId,useState} from 'react';
import {useQuery} from '@tanstack/react-query';
import {apiClient} from '../api/client';
import {apiError} from '../types/project';
import {Button} from './ui/Button';

export function ModelPicker({provider,value,onChange,suggestions}:{provider:string;value:string;onChange:(v:string)=>void;suggestions:string[]}) {
 const id=useId();const [models,setModels]=useState<string[]>([]);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 async function load(){setBusy(true);setError('');try {setModels((await apiClient.get('/settings/catalog/'+provider)).data.models);}catch(e){setError(apiError(e));}finally{setBusy(false);}}
 return <div className="space-y-2"><input aria-label="معرف النموذج" className="glass-input" dir="ltr" list={id} value={value} onChange={e=>onChange(e.target.value)} placeholder="معرف النموذج لدى المزود"/><datalist id={id}>{[...new Set([...models,...suggestions])].map(m=><option key={m} value={m}/>)}</datalist><Button type="button" size="sm" variant="outline" disabled={!provider} isLoading={busy} onClick={load}>جلب قائمة {provider}</Button>{error&&<p role="alert" className="text-xs text-red-700">{error}</p>}</div>;
}

export function ModelMaintenance({settings,refresh}:{settings:any;refresh:()=>void}) {
 const changes=useQuery({queryKey:['retired-models',settings],queryFn:async()=>(await apiClient.get('/settings/retired-models')).data as {role:string;old:string;new:string}[]});
 const [busy,setBusy]=useState('');const [message,setMessage]=useState('');const [error,setError]=useState('');
 async function run(role:string,config?:any){setBusy(role);setMessage('');setError('');try{if(config){await apiClient.post('/settings/test-model',config);setMessage('نجح اختبار '+role+' بالنموذج '+config.model);}else{await apiClient.post('/settings/repair-models');setMessage('تم تحديث النماذج المعروضة وحفظ الإعدادات.');refresh();await changes.refetch();}}catch(e){setError(apiError(e));}finally{setBusy('');}}
 return <section className="glass rounded-2xl p-6 space-y-4"><h2 className="font-bold text-lg">صلاحية النماذج المختارة</h2><p className="text-sm muted">اختبار النموذج يرسل طلبًا قصيرًا فعليًا وقد تُحتسب تكلفته. نجاح اتصال المزود وحده لا يضمن صلاحية كل نموذج.</p><div className="flex flex-wrap gap-2">{Object.entries({director:settings.director,...settings.workers}).map(([role,config]:[string,any])=><Button key={role} size="sm" variant="outline" disabled={!!busy} isLoading={busy===role} onClick={()=>run(role,config)}>اختبار {role}</Button>)}</div>
 {!!changes.data?.length&&<div className="rounded-xl bg-amber-50 p-4 space-y-3"><p className="font-bold text-sm">بدائل مقترحة لإعدادات Groq القديمة</p><p className="text-xs">قد يختلف التوفر حسب حسابك. راجع البدائل ثم طبّقها إذا أردت؛ لا يحدث تغيير تلقائي.</p>{changes.data.map(c=><p key={c.role} className="text-sm break-all" dir="ltr">{c.role}: {c.old} → {c.new}</p>)}<Button size="sm" disabled={!!busy} onClick={()=>run('repair')}>تطبيق البدائل المعروضة</Button><p className="text-xs muted">يشمل إعدادات النظام فقط. الاختيارات الشخصية واختيارات مدير المشروع تُعدّل من إعداداتها.</p></div>}
 {changes.error&&<p role="alert" className="text-red-700 text-sm">{apiError(changes.error)}</p>}{message&&<p role="status" className="text-emerald-700 text-sm">{message}</p>}{error&&<p role="alert" className="text-red-700 text-sm">{error}</p>}
 </section>;
}
