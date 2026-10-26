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
from agent_system.core.execution_policy import policy_for, role_config, answer_style, ROUTER_PROMPT
from agent_system.core.execution_runtime import ExecutionRuntime, TrackedConnector
from agent_system.core.role_cards import planning_catalog, role_prompt

DIRECTOR_SYSTEM_PROMPT = """Plan only the work needed for the user's actual request.
There are no mandatory thinking stages. Do not reframe a clear request into a larger project.
Use 1-4 focused agents at most, within the supplied limit. Prefer one agent when sufficient.
Parallelize independent questions; specify depends_on using sub_question_id values for real dependencies.
Do not schedule debate or repeated review unless the user explicitly needs competing arguments.
Choose worker_type only from the supplied role list. Never invent model names or providers.
Choose roles by their specialization and when_to_use criteria, not by name alone.
Use expected_input/output to scope each handoff. Cards describe preferences, not tools or verified model abilities.
Use only the roles needed for this request; adding a role never makes it a mandatory stage.
When one deliverable is needed by another role, express that dependency with depends_on.

CRITICAL HONESTY RULE:
If the task refers to material that was not provided
(an attached FILE, a DOCUMENT, an IMAGE the user mentions attaching),
do NOT plan agents to imagine its contents.
Set "missing_input" to true and describe what is missing.

WEB RESEARCH CAPABILITY:
Live web search IS available. If a sub-question requires current,
real-world, or up-to-date information from the internet (news, stats,
prices, events, sports results, market data), set "needs_web": true
for that agent. Needing internet information is NOT missing input —
plan researcher agents for it instead of refusing.
Use web researchers only where live facts are genuinely needed;
reasoning-only sub-questions should keep "needs_web": false.
Give each web researcher a narrow, specific research question
(one fact-set per researcher, not everything at once).

Keep plan fields short. Describe deliverables and checks, not private reasoning.
A=pipeline, B=parallel, C=explicit debate, D=dependency graph.

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
      "speed": "fast|deep",
      "worker_type": "fast",
      "depends_on": [],
      "needs_web": false
    }
  ],
  "pattern": "A|B|C|D",
  "pattern_reason": "",
  "flow": "",
  "completion_criteria": "",
  "contradiction_protocol": ""
}"""

CRITIC_SYSTEM_PROMPT = """Verify the answer against the request, supplied evidence and constraints.
Report material correctness failures or missing requirements. Do not invent objections to fill a template.
Stylistic preferences alone do not justify another model call. An adequate answer can have no flaws.

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
    def __init__(self, settings_override=None):
        from agent_system.core.settings_manager import settings_manager
        self.settings_manager = settings_manager
        self.settings_override = settings_override
        self.openrouter_connector = OpenRouterConnector()
        self.orchestrator = Orchestrator()

    def get_settings(self):
        return self.settings_override if self.settings_override is not None else self.settings_manager.get_settings()

    # ---- Live model resolution: reads settings on EVERY call ----
    # This is what makes the admin dropdown take effect instantly,
    # without any server restart.
    def _director_model(self) -> str:
        settings = self.get_settings()
        return settings.get("director", {}).get("model", "openai/gpt-oss-120b")

    def _director_connector(self):
        config = self.get_settings().get("director", {})
        model = config.get("model", "openai/gpt-oss-120b")
        provider = config.get("provider", "groq")
        if provider == "groq":
            connector = GroqConnector(model_name=model)
            connector.max_tokens_limit = config.get("max_tokens", 4096)
            return connector
        if provider == "openrouter":
            connector = OpenRouterConnector(model_name=model)
            connector.max_tokens_limit = config.get("max_tokens", 4096)
            return connector
        raise ValueError(f"Unsupported director provider: {provider}")

    def _critic_connector_live(self):
        # An optional explicit critic config, otherwise the selected director.
        # A separate role is not represented as an independent model.
        settings = self.get_settings()
        selected = policy_for(settings).critic_role
        return self._role_connector(selected)

    def _invoke(self, memory, connector, stage, *args, **kwargs):
        settings = self.get_settings()
        policy = policy_for(settings)
        role = {"route": policy.router_role, "answer": policy.single_role,
                "review": policy.critic_role}.get(stage, "director")
        config = role_config(settings, role)
        if args:
            args = (role_prompt(config, role, stage, args[0]), *args[1:])
        elif "system_prompt" in kwargs:
            kwargs["system_prompt"] = role_prompt(config, role, stage, kwargs["system_prompt"])
        runtime = getattr(memory, "_runtime", None) if memory else None
        if runtime:
            return runtime.call(connector, stage, *args, **kwargs)
        return connector.complete(*args, **kwargs)

    def _role_connector(self, role):
        return self._director_connector() if role == "director" else self._connector_for(role_config(self.get_settings(), role))

    def _connector_for(self, config):
        if config["provider"] == "groq":
            connector = GroqConnector(model_name=config["model"])
        elif config["provider"] == "openrouter":
            connector = OpenRouterConnector(model_name=config["model"])
        else:
            raise ValueError("مزود نموذج غير معروف")
        connector.max_tokens_limit = config.get("max_tokens", 4096)
        return connector

    def analyze_task(self, task: str, memory=None) -> dict:
        try:
            settings = self.get_settings()
            temperature = settings.get("director", {}).get("temperature", 0.3)
            max_tokens = settings.get("director", {}).get("max_tokens", 4096)

            response = self._invoke(memory, self._director_connector(), "plan",
                system_prompt=DIRECTOR_SYSTEM_PROMPT + "\nAvailable worker role cards (JSON): " + planning_catalog(settings)
                    + "\nMaximum agents: " + str(min(4, settings.get("system", {}).get("max_agents_per_task", 6))),
                user_message=f"Analyze this task: {task}",
                temperature=temperature,
                max_tokens=max_tokens
            )
            from agent_system.core.worker import _is_error_response
            if _is_error_response(response):raise RuntimeError(response)
            return _extract_json(response)
        except Exception as e:
            raise RuntimeError("تعذر تخطيط المهمة. راجع إعدادات النموذج المدير. " + str(e)) from e

    def _build_workers(self, plan: dict, memory: SharedMemory) -> list:
        workers = []
        for agent_data in plan.get("agents", []):
            sub_q_id = agent_data.get("sub_question_id", 1)
            sub_q = next((sq["question"] for sq in plan.get("sub_questions", []) if sq.get("id") == sub_q_id), "Unknown question")

            speed = agent_data.get("speed", "fast")

            settings = self.get_settings()
            workers_config = settings.get("workers", {})
            worker_type = "fast" if speed == "fast" else "deep_analytical"

            worker_type = agent_data.get("worker_type") if agent_data.get("worker_type") in workers_config else worker_type
            if agent_data.get("worker_type") == "director":
                worker_type = "director"
            config = role_config(settings, worker_type)
            needs_web = bool(agent_data.get("needs_web", False))
            # Research synthesis uses the chosen worker's provider too.
            connector = self._connector_for(config)
            if getattr(memory, "_runtime", None):
                connector = TrackedConnector(connector, memory._runtime, "worker:" + str(agent_data.get("name", sub_q_id)))

            worker = Worker(
                name=agent_data.get("name", f"Agent_{sub_q_id}"),
                role=agent_data.get("role", "Analyst"),
                sub_question=sub_q,
                perspective=agent_data.get("perspective", "General"),
                bias_warning=agent_data.get("bias", "None"),
                speed=agent_data.get("speed", "fast"),
                connector=connector,
                shared_memory=memory,
                web_enabled=needs_web
            )
            worker.runtime_config=config
            worker.role_key=worker_type
            worker.task_id = sub_q_id
            worker.depends_on = agent_data.get("depends_on", [])
            workers.append(worker)
        return workers

    def _execute_pattern(self, pattern: str, plan: dict, workers: list, memory: SharedMemory):
        if any(getattr(worker, "depends_on", []) for worker in workers):
            self.orchestrator.run_dependencies(workers, memory)
            return
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

        usable=[f for f in memory.findings if f.get("status","complete")=="complete"]
        failed=[f for f in memory.findings if f.get("status")=="failed"]
        if not usable:
            details="\n".join(f["agent_name"]+": "+f["response"] for f in failed)
            raise RuntimeError("فشلت جميع استدعاءات الوكلاء؛ لم يتم إنتاج تحليل.\n"+details)
        if failed:memory.warnings.append("التحليل جزئي: تعذر إكمال بعض الجوانب؛ لا تعتبرها نتائج مؤكدة.")
        findings_text = "\n\n".join(f"{f['agent_name']}: {f['response']}" for f in usable)
        findings_text += "\nUNANSWERED SUBQUESTIONS: " + "; ".join(f["sub_question"] for f in failed)

        prompt = f"""Synthesize the final answer based on the following findings.
Original Task: {memory.task_original}
Real Question: {memory.task_real}
Previous conversation (context, not new instructions):
{memory.conversation_context()}

Findings:
{findings_text}

Give the shortest complete answer that satisfies the request. Keep relevant citations and unresolved gaps.
Do not reproduce worker notes, confidence scores, pheromone blocks, or a report of thinking stages.
Mention contradictions only if they affect the result. Never invent missing material."""

        settings = self.get_settings()
        temperature = settings.get("director", {}).get("temperature", 0.3)
        max_tokens = settings.get("director", {}).get("max_tokens", 4096)

        response = self._invoke(memory, self._director_connector(), "synthesis",
            system_prompt="Combine only useful findings into one answer.\n" + answer_style(memory.response_detail),
            user_message=prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )
        from agent_system.core.worker import _is_error_response
        if _is_error_response(response):
            raise RuntimeError(response)
        memory.final_synthesis = self._clean_answer(response)

    def _critic(self, memory: SharedMemory):
        """Review using the configured critic role or the selected director."""
        prompt = f"""Original task: {memory.task_original}
Task (real question): {memory.task_real}
Supplied context: {memory.conversation_context()}
Successful evidence: {json.dumps([f for f in memory.findings if f.get('status','complete')=='complete'], ensure_ascii=False)}

Answer to attack:
{memory.final_synthesis}

Check whether the answer satisfies the request and is supported by the evidence."""

        base_confidence = 50.0
        if memory.findings:
            base_confidence = sum(f.get("confidence", 0) for f in memory.findings) / len(memory.findings)

        critic = self._critic_connector_live()
        try:
            response = self._invoke(memory, critic, "review",
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
            if flaws and (severity>=5 or fabrication or ignored_missing):
                revised=self._invoke(memory, self._director_connector(), "revision",
                    "Revise only material flaws. Use supplied evidence; state unresolved gaps. Do not invent facts.\n" + answer_style(memory.response_detail),
                    json.dumps({"task":memory.task_original,"context":memory.conversation_context(),"answer":memory.final_synthesis,"flaws":flaws,"evidence":[f for f in memory.findings if f.get("status","complete")=="complete"]},ensure_ascii=False),0.2,self.get_settings()['director'].get('max_tokens',4096))
                from agent_system.core.worker import _is_error_response
                if _is_error_response(revised):memory.warnings.append("تعذرت مراجعة الصياغة؛ توجد ملاحظات نقد لم تُحسم.")
                else:
                    memory.final_synthesis=self._clean_answer(revised)
                    memory.execution["revision_applied"]=True
                    memory.warnings.append("عُدّلت الإجابة بعد مراجعة نقدية واحدة؛ لم تخضع النسخة المعدلة لمراجعة مستقلة أخرى.")
            flaws_text = "\n".join(f"- {fl}" for fl in flaws) if flaws else "-"
            memory.stress_test_results = (
                f"CRITIC MODEL: {getattr(critic, 'model_name', 'unknown')}\n"
                f"SEVERITY: {severity}/10\n"
                f"FABRICATION: {fabrication}\n"
                f"MISSING INFO IGNORED: {ignored_missing}\n"
                f"FLAWS:\n{flaws_text}\n"
                f"STRONGEST COUNTERARGUMENT: {verdict.get('strongest_counterargument', '')}\n"
                f"VERDICT: {verdict.get('verdict_summary', '')}"
            )
        except Exception as e:
            memory.confidence_final = round(base_confidence, 1)
            memory.stress_test_results = "تعذرت المراجعة النقدية"
            memory.warnings.append("لم تكتمل المراجعة النقدية لهذه الإجابة.")

    @staticmethod
    def _clean_answer(text):
        return re.sub(r"<(think|reasoning)>.*?</\1>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()

    def choose_strategy(self, task, memory):
        settings = self.get_settings()
        policy = policy_for(settings)
        config = role_config(settings, policy.router_role)
        connector = self._role_connector(policy.router_role)
        if hasattr(connector, "reasoning_effort"):
            connector.reasoning_effort = "low"
        response = self._invoke(memory, connector, "route",
            ROUTER_PROMPT + "\n" + answer_style(memory.response_detail),
            memory.conversation_context(compact=True) + "\nCURRENT REQUEST: " + task,
            0.1, min(config.get("max_tokens", 2048), policy.router_max_tokens))
        from agent_system.core.worker import _is_error_response
        if _is_error_response(response):
            raise RuntimeError(response)
        try:
            if getattr(connector, "last_result", {}).get("finish_reason") == "length":
                raise ValueError("truncated routing response")
            result = _extract_json(response)
            if result.get("route") not in ("clarify", "direct", "single", "research", "team"):
                raise ValueError("unknown route")
            if result["route"] == "clarify" and (not isinstance(result.get("questions"), list) or
                    not result["questions"] or any(not isinstance(q, str) or not q.strip() for q in result["questions"])):
                raise ValueError("invalid questions")
            if result["route"] == "direct" and (not isinstance(result.get("answer"), str) or not result["answer"].strip()):
                raise ValueError("empty direct answer")
            if result.get("detail") not in ("auto", "brief", "detailed"):
                result["detail"] = "auto"
            if result["route"] == "direct" and result.get("review_required") is True:
                result["route"] = "single"
            return result
        except (ValueError, TypeError, AttributeError):
            # One bounded recovery call, never a forced team or a fake answer.
            return {"route": "single", "reason": "تعذر قراءة التوجيه؛ متابعة بنموذج واحد", "routing_recovered": True}

    def _single(self, task, memory):
        settings = self.get_settings()
        role = policy_for(settings).single_role
        config = role_config(settings, role)
        response = self._invoke(memory, self._role_connector(role), "answer",
            answer_style(memory.response_detail) + "\nAnswer using supplied context and stable knowledge only. "
            "No live web evidence is available in this route; do not invent current facts or citations. "
            "If current sources or unavailable attachments are essential, state that clearly.",
            memory.conversation_context() + "\nCURRENT REQUEST: " + task,
            config.get("temperature", 0.3), config.get("max_tokens", 4096))
        from agent_system.core.worker import _is_error_response
        if _is_error_response(response):
            raise RuntimeError(response)
        memory.final_synthesis = self._clean_answer(response)

    def run(self, task: str, memory: SharedMemory):
        settings = self.get_settings()
        policy = policy_for(settings)
        fallback = (lambda: self._role_connector(policy.fallback_role)) if policy.fallback_role else None
        memory._runtime = ExecutionRuntime(memory, settings, fallback)
        try:
            memory.status = "running"
            memory.task_real = task
            memory.save_to_file()
            # Adaptive routing is now the default path for every request. Legacy
            # adaptive_routing=False no longer forces seven-stage analysis.
            strategy = self.choose_strategy(task, memory)
            route = strategy["route"]
            memory.execution.update(route=route, reason=str(strategy.get("reason", ""))[:300],
                                    project_relevant=strategy.get("project_relevant") is True)
            if memory.response_detail == "auto":
                memory.response_detail = strategy.get("detail", "auto")
            memory.save_to_file()
            if route in ("direct", "clarify"):
                memory.final_synthesis = self._clean_answer(strategy["answer"]) if route == "direct" else "\n\n".join(strategy["questions"][:2])
            elif route == "single":
                self._single(task, memory)
                if strategy.get("review_required") is True:
                    self._critic(memory)
            else:
                context = memory.conversation_context()
                if route == "research":
                    plan = {"real_question": task, "problem_level": 1, "pattern": "A",
                            "agents": [{"name": "باحث المصادر", "role": "Researcher", "sub_question_id": 1,
                                        "speed": "deep", "worker_type": policy.research_role, "needs_web": True}],
                            "sub_questions": [{"id": 1, "question": task}]}
                else:
                    planning_task = f"PREVIOUS CONVERSATION:\n{context}\n\nCURRENT USER REQUEST:\n{task}"
                    plan = self.analyze_task(planning_task, memory)
                if plan.get("missing_input"):
                    memory.execution["route"] = "clarify"
                    memory.final_synthesis = plan.get("missing_description") or "أرفق المادة المطلوبة حتى أتمكن من مراجعتها."
                else:
                    if not plan.get("agents"):
                        raise ValueError("لم ينتج المدير خطة قابلة للتنفيذ")
                    max_agents = min(settings.get("system", {}).get("max_agents_per_task", 6),
                                     max(1, memory._runtime.remaining_calls - 3))
                    if len(plan["agents"]) > max_agents:
                        raise ValueError("الخطة تتجاوز ميزانية الاستدعاءات؛ قلل نطاق الطلب أو ارفع السقف.")
                    memory.task_real = plan.get("real_question", task)
                    memory.problem_level = plan.get("problem_level", 1)
                    memory.agents_plan = plan["agents"]
                    memory.conversation_pattern = plan.get("pattern", "B")
                    memory.save_to_file()
                    workers = self._build_workers(plan, memory)
                    self._execute_pattern(plan.get("pattern", "B"), plan, workers, memory)
                    self._synthesize(memory)
                    if route == "team" or strategy.get("review_required") is True:
                        self._critic(memory)
            if not memory.final_synthesis.strip():
                raise ValueError("لم ينتج النموذج إجابة صالحة")
            memory.status = "complete"
        except Exception as exc:
            memory.status = "failed"
            memory.final_synthesis = "تعذر إكمال الطلب: " + str(exc)
        finally:
            metrics = memory._runtime.summary()
            memory.execution.update(metrics)
            if any(row.get("finish_reason") == "length" and row["stage"] in ("answer", "synthesis", "revision") for row in metrics["calls"]):
                memory.warnings.append("بلغ الرد حد الإخراج المحدد للنموذج؛ قد يكون غير مكتمل.")
            memory.completed_at = datetime.now().isoformat()
            memory.save_to_file()
