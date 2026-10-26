import { ConversationSummary } from "./index";
export type ModelChoice = {
  provider: "groq" | "openrouter";
  model: string;
  temperature: number;
  max_tokens: number;
};
export const moduleLabels: Record<string, string> = {
  facts:"الحقائق", assumptions:"الافتراضات", questions:"الأسئلة المفتوحة", results:"النتائج والقياس",
  tasks: "المهام",
  notes: "الملاحظات",
  decisions: "القرارات",
  requirements: "المتطلبات",
  bugs: "الأخطاء",
  milestones: "مراحل التنفيذ",
  products: "المنتجات",
  content: "خطة المحتوى",
  sources: "المصادر",
  chapters: "خطة الفصول",
  lessons: "الدروس",
  assessments: "الاختبارات",
};
export const projectLabels: Record<string, string> = {
  general: "مشروع عام",
  software: "تطوير برمجي",
  commerce: "تجارة",
  research: "بحث",
  teaching: "تعليم",
};
export type BoardItem = {
  id: string;
  title: string;
  content: string;
  status: "todo" | "doing" | "done";
  due_date: string;
  url: string;
  owner?:string;
  expected_outcome?:string;
  linked_decision_id?:string;
  linked_task_id?:string;
  blocked_by?:string[];
  knowledge_status?:'unverified'|'confirmed'|'disputed';
  decision_state?:'proposed'|'approved'|'rejected';
  target?:number|null;
  actual?:number|null;
  unit?:string;
  direction?:'increase'|'decrease';
  origin?: string;
  message_id?: string;
  evidence?: string;
  conversation_id?: string;
};
export type BoardModule = {
  id: string;
  kind: string;
  title: string;
  hidden: boolean;
  items: BoardItem[];
};
export type Proposal = {
  id: string;
  project_type: string;
  reason: string;
  modules: string[];
  items: (BoardItem & { kind: string })[];
};
export type Project = {
  id: string;
  name: string;
  goal: string;
  project_type: string;
  revision: number;
  updated_at: string;
  director: ModelChoice | null;
  locked: boolean;
  auto_suggest: boolean;
  modules: BoardModule[];
  proposal: Proposal | null;
  suggestion_status: string;
  suggestion_error: string;
  can_undo: boolean;
  brief?:{success_criteria:string;constraints:string;stage:string};
  overview?:{next_step:string;tasks_total:number;tasks_done:number;blocked:BoardItem[];pending_decisions:BoardItem[];open_questions:BoardItem[];unverified_facts:BoardItem[];measurements:Measurement[];missing_results:BoardItem[];events:{id:string;at:string;action:string;title:string}[]};
  reviews?:{at:string;goal:string;success_criteria:string;measurements:Measurement[];next_step:string;missing_results:number}[];
  conversations?: ConversationSummary[];
};
export function apiError(error: any) {
  const d = error?.response?.data?.detail;
  return typeof d === "string"
    ? d
    : d?.error || "تعذر حفظ التغيير. تحقق من الاتصال وأعد المحاولة.";
}

export type Measurement={id:string;title:string;actual:number|null;target:number|null;unit:string;verdict:string;linked_task_id:string};
