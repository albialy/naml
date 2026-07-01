from agent_system.core.connectors.base import BaseConnector
from agent_system.core.memory import SharedMemory

class Worker:
    def __init__(self, name: str, role: str, sub_question: str, perspective: str, bias_warning: str, speed: str, connector: BaseConnector, shared_memory: SharedMemory):
        self.name = name
        self.role = role
        self.sub_question = sub_question
        self.perspective = perspective
        self.bias_warning = bias_warning
        self.speed = speed
        self.connector = connector
        self.shared_memory = shared_memory
        
        from agent_system.core.settings_manager import settings_manager
        self.settings_manager = settings_manager

    def _build_context(self) -> str:
        if not self.shared_memory.findings:
            return "No previous findings yet. / لا توجد نتائج سابقة بعد."
        
        context_parts = []
        for finding in self.shared_memory.findings:
            if finding["agent_name"] != self.name:
                context_parts.append(
                    f"Agent {finding['agent_name']} answered '{finding['sub_question']}':\n{finding['response']}"
                )
        return "\n\n".join(context_parts)

    def execute(self) -> str:
        system_prompt = f"""You are {self.name}.
Your role: {self.role}
Your unique perspective: {self.perspective}
Your known bias to watch for: {self.bias_warning}

You are part of a thinking system working on:
ORIGINAL TASK: {self.shared_memory.task_original}
REAL QUESTION: {self.shared_memory.task_real}

Your specific sub-question:
{self.sub_question}

Context from previous agents:
{self._build_context()}

Rules:
1. Answer only your sub-question.
2. Do not repeat what previous agents said.
3. Add only what your perspective uniquely sees.
4. ANTI-HALLUCINATION RULE (most important): If the task refers to something you cannot actually see or that was not provided to you (an attached file, a document, data, an image, a link, or any missing context), you MUST NOT invent or imagine its contents. Do not describe what the file might contain or could include. Instead, state clearly and honestly that the referenced material was not provided to you, and set your confidence very low, below 20. Refusing to fabricate is a success, not a failure.
5. Base every claim only on information actually present in the task and the context above. If you are speculating, say so explicitly.
6. End with: CONFIDENCE: [0-100]% (be honest: use low confidence when information is missing)
7. End with: WHAT I MIGHT HAVE MISSED: [honest reflection]
8. CRITICAL LANGUAGE RULE: You MUST respond in the exact same language as the original task. If the task is in Arabic, respond entirely in Arabic. If English, respond in English. Never mix languages. Never default to English when the task is in another language."""

        user_message = f"Please answer your sub-question: {self.sub_question}"
        
        settings = self.settings_manager.get_settings()
        workers_config = settings.get("workers", {})
        
        temperature = 0.8 if self.speed == "fast" else 0.2
        max_tokens = 2048 if self.speed == "fast" else 4096
        
        worker_type = "fast" if self.speed == "fast" else "deep_analytical"
        if worker_type in workers_config:
            temperature = workers_config[worker_type].get("temperature", temperature)
            max_tokens = workers_config[worker_type].get("max_tokens", max_tokens)
        
        try:
            response = self.connector.complete(system_prompt, user_message, temperature, max_tokens)
            
            confidence = 80.0
            if "CONFIDENCE:" in response.upper():
                try:
                    conf_str = response.upper().split("CONFIDENCE:")[1].split("%")[0].strip()
                    confidence = float(conf_str)
                except:
                    pass
                    
            self.shared_memory.add_finding(self.name, self.sub_question, response, confidence)
            return response
        except Exception as e:
            error_response = f"Worker {self.name} failed / فشل العامل: {str(e)}"
            self.shared_memory.add_finding(self.name, self.sub_question, error_response, 0.0)
            return error_response
