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
