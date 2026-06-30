from typing import List
from agent_system.core.worker import Worker
from agent_system.core.memory import SharedMemory

class Orchestrator:
    def __init__(self):
        from agent_system.core.settings_manager import settings_manager
        self.settings_manager = settings_manager

    def run_pipeline(self, workers: List[Worker], memory: SharedMemory):
        """Execute workers sequentially. Each worker sees all previous findings."""
        for worker in workers:
            try:
                worker.execute()
            except Exception as e:
                memory.add_finding(worker.name, worker.sub_question, f"Pipeline execution error / خطأ في تنفيذ التسلسل: {e}", 0.0)

    def run_parallel(self, workers: List[Worker], memory: SharedMemory):
        """Execute all workers without them seeing each other's work initially."""
        # For a true parallel, we would use threading or asyncio. 
        # But per requirements, they just don't see each other's work.
        for worker in workers:
            try:
                worker.execute()
            except Exception as e:
                memory.add_finding(worker.name, worker.sub_question, f"Parallel execution error / خطأ في التنفيذ الموازي: {e}", 0.0)

    def run_debate(self, worker_a: Worker, worker_b: Worker, memory: SharedMemory, rounds: int = 2):
        """Debate between two workers."""
        settings = self.settings_manager.get_settings()
        max_rounds = settings.get("system", {}).get("max_debate_rounds", 3)
        actual_rounds = min(rounds, max_rounds)
        
        for i in range(actual_rounds):
            worker_a.execute()
            worker_b.execute()
            # Identify contradictions based on their findings
            memory.add_contradiction(
                worker_a.name, worker_b.name,
                f"Debate round {i+1} completed. See findings for details. / اكتملت جولة النقاش {i+1}."
            )

    def run_hybrid(self, plan: dict, workers: List[Worker], memory: SharedMemory):
        """Execute according to the parsed flow description from director plan."""
        flow = plan.get("flow", "").lower()
        if "parallel" in flow and "pipeline" in flow:
            # Simple fallback for hybrid
            half = len(workers) // 2
            self.run_parallel(workers[:half], memory)
            self.run_pipeline(workers[half:], memory)
        else:
            self.run_pipeline(workers, memory)
