import uuid
from datetime import datetime
import json
import os
from typing import List, Dict, Any, Optional

class SharedMemory:
    def __init__(self, task_original: str, user_id: str = ""):
        self.session_id: str = str(uuid.uuid4())
        self.user_id: str = user_id
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
        self.created_at: str = datetime.now().isoformat()
        self.completed_at: Optional[str] = None

    def add_finding(self, agent_name: str, sub_question: str, response: str, confidence: float):
        self.findings.append({
            "agent_name": agent_name,
            "sub_question": sub_question,
            "response": response,
            "confidence": confidence,
            "timestamp": datetime.now().isoformat()
        })
        self.save_to_file()

    def add_contradiction(self, agent_1: str, agent_2: str, description: str):
        self.contradictions.append({
            "agent_1": agent_1,
            "agent_2": agent_2,
            "description": description,
            "timestamp": datetime.now().isoformat()
        })
        self.save_to_file()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
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
        storage_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'storage', 'sessions')
        os.makedirs(storage_dir, exist_ok=True)
        file_path = os.path.join(storage_dir, f"{self.session_id}.json")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving session / خطأ في حفظ الجلسة: {e}")
