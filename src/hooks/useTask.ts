import { useTaskStore } from '../store/taskStore';

export function useTask() {
  return useTaskStore();
}
