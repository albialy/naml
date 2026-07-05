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

CRITICAL HONESTY RULE:
If the task refers to material that was not provided
(an attached file, a document, data, an image, a link),
do NOT plan agents to imagine its contents.
Set "missing_input" to true and describe what is missing
in "missing_description". Keep agents minimal (one agent
whose job is to state clearly what is needed).

STAGE 0 - DECONSTRUCT THE REQUEST:
List every hidden assumption.
Challenge each assumption.
Find the REAL QUESTION behind the surface question.

STAGE 1 - IDENTIFY PROBLEM LEVEL:
LEVEL 1: missing information -> find data
LEVEL 2: recurring pattern -> analyze
LEVEL 3: system design -> restructure
LEVEL 4: false assumption -> first principles

STAGE 2 - DECOMPOSE:
Break into 2-6 independent sub-questions.
No overlaps. No gaps.

STAGE 3 - ASSIGN AGENTS:
For each sub-question define name, role, perspective,
bias to watch for, and speed (fast/deep).

STAGE 4 - CONVERSATION PATTERN:
A=pipeline, B=parallel, C=debate, D=hybrid

STAGE 5 - FINISH LINE:
Completion criteria and contradiction protocol.

Respond only in valid JSON matching this structure:
{
  "surface_question": "",
  "assumptions": [],
  "real_question": "",
  "missing_input": false,
  "missing_description": "",
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

CRITIC_SYSTEM_PROMPT = """You are an adversarial critic. Your only job is to attack answers and find their weaknesses. You are rewarded for finding real flaws, not for being polite.

You must respond ONLY in valid JSON with this exact structure:
{
  "severity": 0,
  "fabrication_detected": false,
  "missing_information_ignored": false,
  "flaws": ["flaw 1", "flaw 2"],
  "strongest_counterargument": "",
  "verdict_summary": ""
}

Rules for scoring severity (0-10):
- 0-2: minor stylistic issues only
- 3-5: real gaps or weak reasoning in places
- 6-8: serious logical flaws or unsupported claims
- 9-10: fabricated content, or the answer pretends to know something it cannot know

Set fabrication_detected to true if the answer invents facts,
describes content it was never given, or expresses confidence
without evidence.

Set missing_information_ignored to true ONLY if the task referenced
specific material (an attached file, a dataset, a link) that was
not available, AND the answer proceeded to analyze it as if it
existed. If the answer explicitly acknowledged the missing material
and refused to invent its contents, this must be false.
General scarcity of data in the world is NOT missing information.

Calibration rule for severity: use the FULL range. An honest,
well-structured answer with minor gaps deserves 2-3. Reserve 6+
for real logical failures. Giving every answer the same score
is itself a failure of your job. Before finalizing, ask yourself:
is this score genuinely different from what I would give a much
better or much worse answer?

Write verdict_summary in the SAME language as the answer being criticized."""


def _extract_json(text: str) -> dict:
    """Robust JSON extraction: strips reasoning blocks, finds outermost braces."""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<reasoning>.*?</reasoning>", "", cleaned, flags=re.DOTALL)
    if "```json" in cleaned:
        cleaned = cleaned.split("```json")[1].split("```")[0]
    elif "```" in cleaned:
        parts = cleaned.split("```")
        if len(parts) >= 2:
            cleaned = parts[1]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        cleaned = cleaned[start:end + 1]
    return json.loads(cleaned)


class Director:
    def __init__(self):
        from agent_system.core.settings_manager import settings_manager
        self.settings_manager = settings_manager

        # EXPERIMENT: director pinned to reasoning model (bypasses stored settings)
        self.director_model = "openai/gpt-oss-120b"

        self.groq_connector = GroqConnector(model_name=self.director_model)
        self.openrouter_connector = OpenRouterConnector()
        if not os.getenv("OPENROUTER_API_KEY"):
            self.openrouter_connector = self.groq_connector

        # Critic must be a DIFFERENT mind than the director.
        if "gpt-oss" in self.director_model or "qwen3" in self.director_model:
            self.critic_connector = GroqConnector(model_name="llama-3.3-70b-versatile")
        else:
            self.critic_connector = GroqConnector(model_name="openai/gpt-oss-120b")

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
            return _extract_json(response)
        except Exception as e:
            return {
                "error": str(e),
                "surface_question": task,
                "real_question": task,
                "missing_input": False,
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

            speed = agent_data.get("speed", "fast")

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
        else:
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

Provide a comprehensive, unified final answer. Note any contradictions and how you resolved them. If the findings indicate that required material was missing, say so plainly instead of inventing content. / قدم إجابة نهائية شاملة وموحدة. اذكر أي تناقضات وكيف قمت بحلها. إذا أشارت النتائج إلى أن مادة مطلوبة كانت مفقودة، صرّح بذلك بوضوح بدلاً من اختلاق محتوى."""

        settings = self.settings_manager.get_settings()
        temperature = settings.get("director", {}).get("temperature", 0.3)
        max_tokens = settings.get("director", {}).get("max_tokens", 4096)

        response = self.groq_connector.complete(
            system_prompt="You are the lead synthesizer. Combine multiple perspectives into one coherent final answer.\n\nCRITICAL LANGUAGE RULE: You MUST respond in the exact same language as the original task. If the original task is in Arabic, respond entirely in Arabic. If English, respond in English. Never mix languages. Never default to English when the task is in another language.",
            user_message=prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )
        memory.final_synthesis = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()

    def _critic(self, memory: SharedMemory):
        """Adversarial critic: a DIFFERENT model attacks the answer, then confidence is recalibrated."""
        prompt = f"""Task (real question): {memory.task_real}

Answer to attack:
{memory.final_synthesis}

Attack this answer. Find every real weakness."""

        base_confidence = 50.0
        if memory.findings:
            base_confidence = sum(f.get("confidence", 0) for f in memory.findings) / len(memory.findings)

        try:
            response = self.critic_connector.complete(
                system_prompt=CRITIC_SYSTEM_PROMPT,
                user_message=prompt,
                temperature=0.2,
                max_tokens=2048
            )
            verdict = _extract_json(response)

            severity = float(verdict.get("severity", 5))
            severity = max(0.0, min(10.0, severity))
            fabrication = bool(verdict.get("fabrication_detected", False))
            ignored_missing = bool(verdict.get("missing_information_ignored", False))

            adjusted = base_confidence * (1.0 - severity / 15.0)
            if fabrication or ignored_missing:
                adjusted = min(adjusted, 20.0)
            if memory.findings and min(f.get("confidence", 100) for f in memory.findings) < 20:
                adjusted = min(adjusted, 25.0)

            memory.confidence_final = round(max(0.0, min(100.0, adjusted)), 1)

            flaws = verdict.get("flaws", [])
            flaws_text = "\n".join(f"- {fl}" for fl in flaws) if flaws else "-"
            memory.stress_test_results = (
                f"CRITIC MODEL: {getattr(self.critic_connector, 'model_name', 'unknown')}\n"
                f"SEVERITY: {severity}/10\n"
                f"FABRICATION: {fabrication}\n"
                f"MISSING INFO IGNORED: {ignored_missing}\n"
                f"FLAWS:\n{flaws_text}\n"
                f"STRONGEST COUNTERARGUMENT: {verdict.get('strongest_counterargument', '')}\n"
                f"VERDICT: {verdict.get('verdict_summary', '')}"
            )
        except Exception as e:
            memory.confidence_final = round(base_confidence, 1)
            memory.stress_test_results = f"Critic failed / فشل الناقد: {str(e)}"

    def run(self, task: str, memory: SharedMemory):
        try:
            memory.status = "running"
            memory.save_to_file()

            plan = self.analyze_task(task)

            memory.task_real = plan.get("real_question", task)
            memory.problem_level = plan.get("problem_level", 1)
            memory.agents_plan = plan.get("agents", [])
            memory.conversation_pattern = plan.get("pattern", "A")
            memory.save_to_file()

            settings = self.settings_manager.get_settings()
            max_agents = settings.get("system", {}).get("max_agents_per_task", 6)

            workers = self._build_workers(plan, memory)
            if len(workers) > max_agents:
                workers = workers[:max_agents]

            self._execute_pattern(plan.get("pattern", "A"), plan, workers, memory)

            self._synthesize(memory)
            self._critic(memory)

            memory.status = "complete"
            memory.completed_at = datetime.now().isoformat()
            memory.save_to_file()

        except Exception as e:
            memory.status = "failed"
            memory.final_synthesis = f"Error during execution / خطأ أثناء التنفيذ: {str(e)}"
            memory.save_to_file()
