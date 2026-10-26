export type UserRole = "super_admin" | "operator" | "user";

export interface User {
  id: string;
  username: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  last_login: string;
  session_limit: number;
}

export interface AuthResponse {
  token: string;
  role: UserRole;
  username: string;
}

export interface TaskStatus {
  session_id: string;
  status: "pending" | "running" | "synthesizing" | "complete" | "failed";
  user_id: string;
  task_original: string;
}

export interface TaskResult {
  final_synthesis: string;
  confidence_final: number;
  stress_test_results: string;
  status: string;
}

export interface SessionSummary {
  session_id: string;
  task_original: string;
  status: string;
  created_at: string;
  confidence_final: number;
}

export interface ConversationSummary {
  project_id?: string;
  conversation_id: string;
  user_id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at: string;
  active_session_id: string;
  message_count: number;
}

export interface ConversationMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  session_id: string;
  created_at: string;
  status?: string;
  confidence?: number;
  execution?: ExecutionInfo;
  warnings?:string[];
}

export interface ExecutionInfo {
  route?: string;
  reason?: string;
  revision_applied?: boolean;
  model_calls?: number;
  duration_ms?: number;
  reported_tokens?: number;
  usage_complete?: boolean;
  calls?: {stage: string; provider: string; model: string; status: string; duration_ms?: number; total_tokens: number | null; fallback?: boolean}[];
}

export interface Conversation extends ConversationSummary {
  messages: ConversationMessage[];
}
