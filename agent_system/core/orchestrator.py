from typing import List
from concurrent.futures import ThreadPoolExecutor
import copy
from agent_system.core.worker import Worker
from agent_system.core.memory import SharedMemory
from agent_system.core.execution_policy import policy_for

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
                memory.add_finding(worker.name, worker.sub_question, "Error: تعذر تشغيل الوكيل", 0.0, status="failed")

    def run_parallel(self, workers: List[Worker], memory: SharedMemory):
        """Execute all workers without them seeing each other's work initially."""
        snapshot=copy.deepcopy(memory.findings)
        for worker in workers:worker.context_snapshot=snapshot
        settings = memory.run_settings or self.settings_manager.get_settings()
        with ThreadPoolExecutor(max_workers=min(policy_for(settings).parallel_workers,len(workers)) or 1) as pool:
            futures=[pool.submit(worker.execute) for worker in workers]
            for worker,future in zip(workers,futures):
                try:future.result()
                except Exception:
                    memory.add_finding(worker.name,worker.sub_question,"Error: تعذر تشغيل الوكيل",0,status="failed")
        for worker in workers:del worker.context_snapshot

    def run_dependencies(self, workers, memory):
        """Run independent waves; never execute dependents of failed workers."""
        by_id = {worker.task_id: worker for worker in workers}
        if len(by_id) != len(workers) or len({w.name for w in workers}) != len(workers):
            raise ValueError("الخطة تحتوي معرّفات أو أسماء وكلاء مكررة")
        for worker in workers:
            if not isinstance(worker.depends_on, list) or any(dep not in by_id or dep == worker.task_id for dep in worker.depends_on):
                raise ValueError("الخطة تحتوي اعتمادات غير صالحة")
        # Validate all dependencies before spending any worker calls.
        remaining = set(by_id)
        while remaining:
            wave = {key for key in remaining if not any(d in remaining for d in by_id[key].depends_on)}
            if not wave:
                raise ValueError("الخطة تحتوي اعتمادات دائرية")
            remaining -= wave
        pending = list(workers)
        done, failed = set(), set()
        while pending:
            wave = [w for w in pending if set(w.depends_on) <= done | failed]
            runnable = []
            for worker in wave:
                if set(worker.depends_on) & failed:
                    memory.add_finding(worker.name, worker.sub_question, "تعذر التنفيذ لفشل مهمة يعتمد عليها هذا الجزء", 0, status="failed")
                    failed.add(worker.task_id)
                else:
                    runnable.append(worker)
            self.run_parallel(runnable, memory)
            for worker in runnable:
                findings = [f for f in memory.findings if f["agent_name"] == worker.name]
                (done if findings and findings[-1].get("status", "complete") == "complete" else failed).add(worker.task_id)
            pending = [w for w in pending if w not in wave]

    def run_debate(self, worker_a: Worker, worker_b: Worker, memory: SharedMemory, rounds: int = 2):
        """Debate between two workers."""
        settings = memory.run_settings or self.settings_manager.get_settings()
        max_rounds = settings.get("system", {}).get("max_debate_rounds", 3)
        actual_rounds = min(rounds, max_rounds)
        
        for i in range(actual_rounds):
            worker_a.execute()
            worker_b.execute()
            # A completed exchange is not evidence of a contradiction.

    def run_hybrid(self, plan: dict, workers: List[Worker], memory: SharedMemory):
        """Explicit dependencies determine order, never keywords in a prose plan."""
        if any(getattr(worker, "depends_on", []) for worker in workers):
            self.run_dependencies(workers, memory)
        else:
            self.run_parallel(workers, memory)
