import { useTaskStore } from '../store/taskStore';

export function useTask() {
  const { currentTask, isProcessing, setTask, clearTask, setProcessing } = useTaskStore();

  return {
    currentTask,
    isProcessing,
    setTask,
    clearTask,
    setProcessing
  };
}
