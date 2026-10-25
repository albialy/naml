import uuid
import threading
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from agent_system.core.storage import get_storage

class SharedMemory:
    def __init__(self, task_original: str, user_id: str = "", conversation_id: str = "", chat_history=None):
        self._lock = threading.RLock()
        self.session_id: str = str(uuid.uuid4())
        self.user_id: str = user_id
        self.conversation_id = conversation_id
        self.chat_history = chat_history or []
        self.project_id = None
        self.project_context = ""
        self.run_settings = None
        self.execution = {}
        self.response_detail = "auto"
        self.warnings = []
        self.task_original: str = task_original
        self.task_real: str = ""
        self.problem_level: int = 0
        self.agents_plan: List[Dict[str, Any]] = []
        self.conversation_pattern: str = ""
        self.findings: List[Dict[str, Any]] = []
        self.contradictions: List[Dict[str, Any]] = []
        self.final_synthesis: str = ""
        self.confidence_final: float = 0.0
        self.stress_test_results: str = ""
        self.status: str = "pending"  # pending/running/synthesizing/complete/failed
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self.completed_at: Optional[str] = None

    def add_finding(self, agent_name: str, sub_question: str, response: str, confidence: float, pheromone: str = "", status: str = "complete", model: str = ""):
        with self._lock:
            self.findings.append({
                "agent_name": agent_name,
                "status": status,
                "model": model,
                "sub_question": sub_question,
                "response": response,
                "confidence": confidence,
                "pheromone": pheromone,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            self.save_to_file()

    def add_contradiction(self, agent_1: str, agent_2: str, description: str):
        self.contradictions.append({
            "agent_1": agent_1,
            "agent_2": agent_2,
            "description": description,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self.save_to_file()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "chat_history": self.chat_history,
            "project_id": self.project_id,
            "project_context": self.project_context,
            "run_settings": self.run_settings,
            "execution": self.execution,
            "response_detail": self.response_detail,
            "warnings": self.warnings,
            "task_original": self.task_original,
            "task_real": self.task_real,
            "problem_level": self.problem_level,
            "agents_plan": self.agents_plan,
            "conversation_pattern": self.conversation_pattern,
            "findings": self.findings,
            "contradictions": self.contradictions,
            "final_synthesis": self.final_synthesis,
            "confidence_final": self.confidence_final,
            "stress_test_results": self.stress_test_results,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at
        }

    def save_to_file(self):
        """Persist via the storage layer (backend-agnostic).
        Method name kept for backward compatibility with all callers."""
        with self._lock:
            get_storage().save_session(self.to_dict())

    def conversation_context(self, compact=False):
        """Limit model context while preserving the complete saved history."""
        messages = []
        remaining = 5000 if compact else 24000
        truncated = False
        for message in reversed(self.chat_history):
            # start_turn includes the current user message; it is supplied separately.
            if message.get("session_id") == self.session_id and message.get("role") == "user":
                continue
            raw = message.get("content", "")
            text = raw[:1500 if compact else 6000]
            truncated = truncated or len(text) < len(raw)
            if len(text) > remaining:
                truncated = True
                break
            messages.append(f"{message['role']}: {text}")
            remaining -= len(text)
        project = self.project_context[:2000] if compact else self.project_context
        truncated = truncated or len(project) < len(self.project_context)
        note = "[Context excerpts are incomplete. Use single route if earlier details are needed.]" if compact and truncated else ""
        return "\n\n".join([project, note] + list(reversed(messages))).strip()
