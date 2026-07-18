import re
from agent_system.core.connectors.base import BaseConnector
from agent_system.core.memory import SharedMemory


def _extract_pheromone(text: str) -> str:
    """Extract the structured pheromone block a worker emits at the end
    of its answer. Falls back to a truncated response if missing."""
    match = re.search(r"===PHEROMONE===(.*?)(?:===END===|$)", text, flags=re.DOTALL)
    if match:
        block = match.group(1).strip()
        if block:
            return block
    cleaned = text.strip()
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

    def execute(self) -> str:
        web_rules = ""
        if self.web_enabled:
            web_rules = """
SPECIAL CAPABILITY - LIVE WEB ACCESS:
You have a built-in live web search tool that activates automatically.
- USE it to fetch current, real information for your sub-question.
- CITE the source name and date for every fact you bring from the web
  (e.g., "according to FIFA.com, Dec 2022...").
- If search returns nothing useful, say so honestly instead of guessing.
- Never present a web-sourced claim without attribution."""

        system_prompt = f"""You are {self.name}.
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
{web_rules}
Rules:
1. Answer only your sub-question.
2. Do not repeat what previous agents said.
3. Add only what your perspective uniquely sees.
4. ANTI-HALLUCINATION RULE (most important): If the task refers to material that was not provided to you (an attached file, a document, an image), you MUST NOT invent or imagine its contents. State clearly that the referenced material was not provided, and set your confidence very low, below 20. Refusing to fabricate is a success, not a failure.
5. Base every claim only on information actually present in the task, the context above, or (if you have web access) verifiable web sources you cite. If you are speculating, say so explicitly.
6. End with: CONFIDENCE: [0-100]% (be honest: use low confidence when information is missing)
7. End with: WHAT I MIGHT HAVE MISSED: [honest reflection]
8. CRITICAL LANGUAGE RULE: You MUST respond in the exact same language as the original task. If the task is in Arabic, respond entirely in Arabic. If English, respond in English. Never mix languages. Never default to English when the task is in another language.
9. PHEROMONE RULE (mandatory): You MUST end your entire response with this exact block (content in the task's language, each line ONE short sentence):
===PHEROMONE===
DISCOVERY: [your single most important finding]
EVIDENCE: [what it rests on]
GAPS: [what you could not answer]
HANDOFF: [what the next agent most needs to know]
===END==="""

        user_message = f"Please answer your sub-question: {self.sub_question}"

        settings = self.settings_manager.get_settings()
        workers_config = settings.get("workers", {})

        temperature = 0.8 if self.speed == "fast" else 0.2
        max_tokens = 2048 if self.speed == "fast" else 4096

        worker_type = "fast" if self.speed == "fast" else "deep_analytical"
        if worker_type in workers_config:
            temperature = workers_config[worker_type].get("temperature", temperature)
            max_tokens = workers_config[worker_type].get("max_tokens", max_tokens)

        if self.web_enabled:
            # Built-in tools consume tokens; give researchers breathing room
            max_tokens = max(max_tokens, 3072)
            temperature = min(temperature, 0.3)

        try:
            response = self.connector.complete(system_prompt, user_message, temperature, max_tokens)

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
            self.shared_memory.add_finding(self.name, self.sub_question, error_response, 0.0, error_response)
            return error_response
