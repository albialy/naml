import re
import time
from agent_system.core.connectors.base import BaseConnector
from agent_system.core.memory import SharedMemory

# Connector error strings start with these (GroqConnector returns errors as text)
ERROR_PREFIXES = (
    "Network or API error",
    "Rate limit error",
    "Model not found error",
    "Authentication error",
    "Error:",
    "Worker",
)


def _is_error_response(text: str) -> bool:
    t = (text or "").strip()
    return any(t.startswith(p) for p in ERROR_PREFIXES)


def _extract_pheromone(text: str) -> str:
    """Extract the structured pheromone block a worker emits at the end
    of its answer. Falls back to a truncated response if missing."""
    match = re.search(r"===PHEROMONE===(.*?)(?:===END===|$)", text, flags=re.DOTALL)
    if match:
        block = match.group(1).strip()
        if block:
            return block
    cleaned = (text or "").strip()
    return (cleaned[:250] + "…") if len(cleaned) > 250 else cleaned


class Worker:
    def __init__(self, name: str, role: str, sub_question: str, perspective: str, bias_warning: str, speed: str, connector: BaseConnector, shared_memory: SharedMemory, web_enabled: bool = False):
        self.name = name
        self.role = role
        self.sub_question = sub_question
        self.perspective = perspective
        self.bias_warning = bias_warning
        self.speed = speed
        self.connector = connector
        self.shared_memory = shared_memory
        self.web_enabled = web_enabled

        from agent_system.core.settings_manager import settings_manager
        self.settings_manager = settings_manager

    def _build_context(self) -> str:
        """PHEROMONE PROTOCOL: pass only concentrated pheromones from
        previous agents, never their full raw responses."""
        if not self.shared_memory.findings:
            return "No previous findings yet. / لا توجد نتائج سابقة بعد."

        context_parts = []
        for finding in self.shared_memory.findings:
            if finding["agent_name"] != self.name:
                scent = finding.get("pheromone") or _extract_pheromone(finding.get("response", ""))
                context_parts.append(
                    f"[Pheromone from {finding['agent_name']} | confidence {finding.get('confidence', '?')}%]\n{scent}"
                )
        return "\n\n".join(context_parts)

    def _full_prompt(self) -> str:
        """Full ceremony for reasoning workers."""
        return f"""You are {self.name}.
Your role: {self.role}
Your unique perspective: {self.perspective}
Your known bias to watch for: {self.bias_warning}

You are part of a thinking system working on:
ORIGINAL TASK: {self.shared_memory.task_original}
REAL QUESTION: {self.shared_memory.task_real}

Your specific sub-question:
{self.sub_question}

Pheromone trail from previous agents (concentrated findings, not full texts):
{self._build_context()}

Rules:
1. Answer only your sub-question.
2. Do not repeat what previous agents said.
3. Add only what your perspective uniquely sees.
4. ANTI-HALLUCINATION RULE (most important): If the task refers to material that was not provided to you (an attached file, a document, an image), you MUST NOT invent or imagine its contents. State clearly that the referenced material was not provided, and set your confidence very low, below 20. Refusing to fabricate is a success, not a failure.
5. Base every claim only on information actually present in the task and the context above. If you are speculating, say so explicitly.
6. End with: CONFIDENCE: [0-100]% (be honest: use low confidence when information is missing)
7. End with: WHAT I MIGHT HAVE MISSED: [honest reflection]
8. CRITICAL LANGUAGE RULE: You MUST respond in the exact same language as the original task. If the task is in Arabic, respond entirely in Arabic. If English, respond in English. Never mix languages.
9. PHEROMONE RULE (mandatory): You MUST end your entire response with this exact block (content in the task's language, each line ONE short sentence):
===PHEROMONE===
DISCOVERY: [your single most important finding]
EVIDENCE: [what it rests on]
GAPS: [what you could not answer]
HANDOFF: [what the next agent most needs to know]
===END==="""

    def _lean_web_prompt(self) -> str:
        """One-line system for compound (long system + search can trigger 413)."""
        return f"You are {self.name}, a web researcher. Respond in the same language as the task."

    def _web_user_message(self) -> str:
        """All researcher instructions live in the USER message for compound."""
        return f"""TASK CONTEXT: {self.shared_memory.task_real}

YOUR RESEARCH QUESTION (answer ONLY this, narrowly):
{self.sub_question}

Rules:
1. USE your live web search. Bring current, real facts only.
2. CITE source name and date for every fact (e.g., "FIFA.com, 15 July 2026").
3. If search finds nothing useful, say so honestly. Never guess live facts.
4. Respond in the SAME language as the task context above.
5. End with: CONFIDENCE: [0-100]%
6. Then end with this exact block (task's language, one short line each):
===PHEROMONE===
DISCOVERY: [most important finding]
EVIDENCE: [sources it rests on]
GAPS: [what you could not find]
HANDOFF: [what the next agent needs]
===END==="""

    def _call(self, prompt: str, temperature, max_tokens) -> str:
        return self.connector.complete(prompt, f"Answer your research/sub question now: {self.sub_question}", temperature, max_tokens)

    def _call_web(self, max_tokens: int) -> str:
        # Compound: minimal system, instructions in user message, NO temperature
        return self.connector.complete(self._lean_web_prompt(), self._web_user_message(), None, max_tokens)

    def execute(self) -> str:
        settings = self.settings_manager.get_settings()
        workers_config = settings.get("workers", {})

        temperature = 0.8 if self.speed == "fast" else 0.2
        max_tokens = 2048 if self.speed == "fast" else 4096

        worker_type = "fast" if self.speed == "fast" else "deep_analytical"
        if worker_type in workers_config:
            temperature = workers_config[worker_type].get("temperature", temperature)
            max_tokens = workers_config[worker_type].get("max_tokens", max_tokens)

        try:
            if self.web_enabled:
                # Compound quirks: no temperature, tiny system, narrow question
                response = self._call_web(1500)
                if _is_error_response(response):
                    time.sleep(2)
                    response = self._call_web(1024)
            else:
                response = self._call(self._full_prompt(), temperature, max_tokens)

            if _is_error_response(response):
                # Honest failure: zero confidence, clean pheromone, no poisoning
                fail_pheromone = (
                    "DISCOVERY: web search tool failed / فشل البحث في الويب.\n"
                    "EVIDENCE: technical error, no data retrieved.\n"
                    "GAPS: this sub-question remains unanswered.\n"
                    "HANDOFF: do not treat this as information; the data is missing."
                ) if self.web_enabled else (response[:200])
                self.shared_memory.add_finding(self.name, self.sub_question, response, 0.0, fail_pheromone)
                return response

            confidence = 80.0
            if "CONFIDENCE:" in response.upper():
                try:
                    conf_str = response.upper().split("CONFIDENCE:")[1].split("%")[0].strip()
                    confidence = float(conf_str)
                except:
                    pass

            pheromone = _extract_pheromone(response)
            self.shared_memory.add_finding(self.name, self.sub_question, response, confidence, pheromone)
            return response
        except Exception as e:
            error_response = f"Worker {self.name} failed / فشل العامل: {str(e)}"
            self.shared_memory.add_finding(self.name, self.sub_question, error_response, 0.0, error_response[:200])
            return error_response
