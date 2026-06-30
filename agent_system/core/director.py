import json
import re
from datetime import datetime
import yaml
import os
from agent_system.core.memory import SharedMemory
from agent_system.core.worker import Worker
from agent_system.core.orchestrator import Orchestrator
from agent_system.core.connectors.groq_connector import GroqConnector
from agent_system.core.connectors.openrouter_connector import OpenRouterConnector

DIRECTOR_SYSTEM_PROMPT = """You are not an assistant. You are a thinking system.
Your job is not to answer questions.
Your job is to find the right question first,
then orchestrate the right minds to answer it.

You have one absolute rule:
Never output a final answer before completing
all seven stages. No exceptions.

STAGE 0 - DECONSTRUCT THE REQUEST:
List every hidden assumption.
Challenge each assumption.
Find the REAL QUESTION behind the surface question.
Output format:
SURFACE_QUESTION: [what was asked]
ASSUMPTIONS: [numbered list]
REAL_QUESTION: [what is actually needed]

STAGE 1 - IDENTIFY PROBLEM LEVEL:
LEVEL 1: missing information -> find data
LEVEL 2: recurring pattern -> analyze
LEVEL 3: system design -> restructure  
LEVEL 4: false assumption -> first principles
Output format:
PROBLEM_LEVEL: [1/2/3/4]
REASON: [why]
APPROACH: [how to solve]

STAGE 2 - DECOMPOSE:
Break into 2-6 independent sub-questions.
No overlaps. No gaps.
Output format:
SUB_QUESTIONS:
1. [question] | NEEDS: [specialist type]
2. [question] | NEEDS: [specialist type]
...

STAGE 3 - ASSIGN AGENTS:
For each sub-question define:
AGENTS:
- NAME: [name]
  ROLE: [one sentence]
  SUB_QUESTION: [number]
  PERSPECTIVE: [unique angle]
  BIAS: [what they might miss]
  SPEED: [fast/deep]

STAGE 4 - CONVERSATION PATTERN:
A=pipeline, B=parallel, C=debate, D=hybrid
PATTERN: [letter]
REASON: [why]
FLOW: [describe the sequence]

STAGE 5 - FINISH LINE:
COMPLETION_CRITERIA: [what done looks like]
CONTRADICTION_PROTOCOL: [how to handle conflicts]

Respond only in valid JSON matching this structure:
{
  "surface_question": "",
  "assumptions": [],
  "real_question": "",
  "problem_level": 1,
  "approach": "",
  "sub_questions": [
    {"id": 1, "question": "", "specialist": ""}
  ],
  "agents": [
    {
      "name": "",
      "role": "",
      "sub_question_id": 1,
      "perspective": "",
      "bias": "",
      "speed": "fast|deep"
    }
  ],
  "pattern": "A|B|C|D",
  "pattern_reason": "",
  "flow": "",
  "completion_criteria": "",
  "contradiction_protocol": ""
}"""

class Director:
    def __init__(self):
        from agent_system.core.settings_manager import settings_manager
        self.settings_manager = settings_manager
        
        settings = self.settings_manager.get_settings()
        director_model = settings.get("director", {}).get("model", "llama-3.3-70b-versatile")
        
        self.groq_connector = GroqConnector(model_name=director_model)
        self.openrouter_connector = OpenRouterConnector()
        # Fallback to Groq if OpenRouter key is missing
        if not os.getenv("OPENROUTER_API_KEY"):
            self.openrouter_connector = self.groq_connector
            
        self.orchestrator = Orchestrator()

    def analyze_task(self, task: str) -> dict:
        try:
            settings = self.settings_manager.get_settings()
            temperature = settings.get("director", {}).get("temperature", 0.3)
            max_tokens = settings.get("director", {}).get("max_tokens", 4096)
            
            response = self.groq_connector.complete(
                system_prompt=DIRECTOR_SYSTEM_PROMPT,
                user_message=f"Analyze this task: {task}",
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Extract JSON from response
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
                
            return json.loads(json_str)
        except Exception as e:
            return {
                "error": str(e),
                "surface_question": task,
                "real_question": task,
                "problem_level": 1,
                "pattern": "A",
                "agents": [{"name": "DefaultWorker", "role": "Generalist", "sub_question_id": 1, "perspective": "General", "bias": "None", "speed": "fast"}],
                "sub_questions": [{"id": 1, "question": task, "specialist": "General"}]
            }

    def _build_workers(self, plan: dict, memory: SharedMemory) -> list:
        workers = []
        for agent_data in plan.get("agents", []):
            sub_q_id = agent_data.get("sub_question_id", 1)
            sub_q = next((sq["question"] for sq in plan.get("sub_questions", []) if sq.get("id") == sub_q_id), "Unknown question")
            
            # Determine connector based on speed
            speed = agent_data.get("speed", "fast")
            
            # Lookup worker config
            settings = self.settings_manager.get_settings()
            workers_config = settings.get("workers", {})
            worker_type = "fast" if speed == "fast" else "deep_analytical"
            
            provider = "groq"
            model_name = "llama-3.3-70b-versatile"
            
            if worker_type in workers_config:
                provider = workers_config[worker_type].get("provider", provider)
                model_name = workers_config[worker_type].get("model", model_name)
            else:
                if speed != "fast":
                    provider = "openrouter"
                    model_name = "qwen/qwen-72b-chat"
            
            if provider == "groq":
                connector = GroqConnector(model_name=model_name)
            else:
                connector = OpenRouterConnector(model_name=model_name)
                if not os.getenv("OPENROUTER_API_KEY"):
                    connector = self.groq_connector
            
            worker = Worker(
                name=agent_data.get("name", f"Agent_{sub_q_id}"),
                role=agent_data.get("role", "Analyst"),
                sub_question=sub_q,
                perspective=agent_data.get("perspective", "General"),
                bias_warning=agent_data.get("bias", "None"),
                speed=agent_data.get("speed", "fast"),
                connector=connector,
                shared_memory=memory
            )
            workers.append(worker)
        return workers

    def _execute_pattern(self, pattern: str, plan: dict, workers: list, memory: SharedMemory):
        pattern = str(pattern).upper().strip()
        if pattern == "A" or pattern == "PIPELINE":
            self.orchestrator.run_pipeline(workers, memory)
        elif pattern == "B" or pattern == "PARALLEL":
            self.orchestrator.run_parallel(workers, memory)
        elif pattern == "C" or pattern == "DEBATE":
            if len(workers) >= 2:
                self.orchestrator.run_debate(workers[0], workers[1], memory)
            else:
                self.orchestrator.run_pipeline(workers, memory)
        else: # D or Hybrid
            self.orchestrator.run_hybrid(plan, workers, memory)

    def _synthesize(self, memory: SharedMemory):
        memory.status = "synthesizing"
        memory.save_to_file()
        
        findings_text = "\n\n".join([f"{f['agent_name']}: {f['response']}" for f in memory.findings])
        
        prompt = f"""Synthesize the final answer based on the following findings.
Original Task: {memory.task_original}
Real Question: {memory.task_real}

Findings:
{findings_text}

Provide a comprehensive, unified final answer. Note any contradictions and how you resolved them. / قدم إجابة نهائية شاملة وموحدة. اذكر أي تناقضات وكيف قمت بحلها."""

        settings = self.settings_manager.get_settings()
        temperature = settings.get("director", {}).get("temperature", 0.3)
        max_tokens = settings.get("director", {}).get("max_tokens", 4096)

        response = self.groq_connector.complete(
            system_prompt="You are the lead synthesizer. Combine multiple perspectives into one coherent final answer.",
            user_message=prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )
        memory.final_synthesis = response
        
        # Calculate final confidence based on average of findings
        if memory.findings:
            memory.confidence_final = sum(f.get("confidence", 0) for f in memory.findings) / len(memory.findings)
        else:
            memory.confidence_final = 50.0

    def _stress_test(self, memory: SharedMemory):
        prompt = f"""Stress test this synthesized answer.
Task: {memory.task_real}
Answer: {memory.final_synthesis}

Find any logical flaws, missing elements, or weaknesses in this answer. / ابحث عن أي عيوب منطقية، عناصر مفقودة، أو نقاط ضعف في هذه الإجابة."""

        response = self.groq_connector.complete(
            system_prompt="You are a critical stress-tester.",
            user_message=prompt,
            temperature=0.2,
            max_tokens=2048
        )
        memory.stress_test_results = response

    def run(self, task: str, memory: SharedMemory):
        try:
            memory.status = "running"
            memory.save_to_file()
            
            # Stage 0-5
            plan = self.analyze_task(task)
            
            memory.task_real = plan.get("real_question", task)
            memory.problem_level = plan.get("problem_level", 1)
            memory.agents_plan = plan.get("agents", [])
            memory.conversation_pattern = plan.get("pattern", "A")
            memory.save_to_file()
            
            # Apply system constraints
            settings = self.settings_manager.get_settings()
            max_agents = settings.get("system", {}).get("max_agents_per_task", 6)
            
            # Stage 6: Build and Execute
            workers = self._build_workers(plan, memory)
            if len(workers) > max_agents:
                workers = workers[:max_agents]
                
            self._execute_pattern(plan.get("pattern", "A"), plan, workers, memory)
            
            # Stage 7: Synthesize and Stress Test
            self._synthesize(memory)
            self._stress_test(memory)
            
            memory.status = "complete"
            memory.completed_at = datetime.now().isoformat()
            memory.save_to_file()
            
        except Exception as e:
            memory.status = "failed"
            memory.final_synthesis = f"Error during execution / خطأ أثناء التنفيذ: {str(e)}"
            memory.save_to_file()
