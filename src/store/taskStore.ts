import { create } from 'zustand';
import { TaskResult, SessionSummary } from '../types';

interface TaskState {
  currentTaskId: string | null;
  status: 'idle' | 'running' | 'complete' | 'error';
  result: TaskResult | null;
  history: SessionSummary[];
  setTaskId: (id: string | null) => void;
  setStatus: (status: 'idle' | 'running' | 'complete' | 'error') => void;
  setResult: (result: TaskResult | null) => void;
  setHistory: (history: SessionSummary[]) => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  currentTaskId: null,
  status: 'idle',
  result: null,
  history: [],
  setTaskId: (id) => set({ currentTaskId: id }),
  setStatus: (status) => set({ status }),
  setResult: (result) => set({ result }),
  setHistory: (history) => set({ history }),
}));
