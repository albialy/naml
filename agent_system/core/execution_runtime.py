"""Per-turn call accounting and provider admission control (one server process).

No retry loops and no credential rotation. A fallback is an explicit configured
role, used at most once for transient failures. Usage is reported, never guessed.
"""
import threading
import time
from contextlib import contextmanager
from agent_system.core.execution_policy import policy_for


class ExecutionLimit(RuntimeError):
    pass


class ProviderBusy(RuntimeError):
    pass


class ProviderGate:
    def __init__(self):
        self.condition = threading.Condition()
        self.active = {}
        self.cooldown = {}

    @contextmanager
    def slot(self, provider, model, limit, deadline):
        with self.condition:
            while True:
                now = time.monotonic()
                # Provider feedback is shared across all turns using this model.
                if self.cooldown.get((provider, model), 0) > now:
                    raise ProviderBusy("المصدر في مهلة انتظار بعد بلوغ حد الاستخدام؛ حاول لاحقًا.")
                if now >= deadline:
                    raise ExecutionLimit("انتهت مهلة المهمة قبل بدء استدعاء جديد.")
                if self.active.get(provider, 0) < limit:
                    self.active[provider] = self.active.get(provider, 0) + 1
                    break
                self.condition.wait(timeout=min(1.0, deadline - now))
        try:
            yield
        finally:
            with self.condition:
                self.active[provider] -= 1
                self.condition.notify_all()

    def pause(self, provider, model, seconds):
        with self.condition:
            key = (provider, model)
            self.cooldown[key] = max(self.cooldown.get(key, 0), time.monotonic() + max(1, seconds))
            self.condition.notify_all()


PROVIDER_GATE = ProviderGate()


def _failed(answer):
    from agent_system.core.worker import _is_error_response
    return _is_error_response(answer)


class ExecutionRuntime:
    def __init__(self, memory, settings, fallback_factory=None):
        self.memory = memory
        self.policy = policy_for(settings)
        self.start = time.monotonic()
        self.deadline = self.start + self.policy.time_budget_seconds
        self.lock = threading.RLock()
        self.calls = []
        self.fallback_factory = fallback_factory

    @property
    def remaining_calls(self):
        with self.lock:
            return self.policy.max_model_calls - len(self.calls)

    def check(self):
        if time.monotonic() >= self.deadline:
            raise ExecutionLimit("انتهت مهلة العمل؛ قلل نطاق الطلب أو ارفع المهلة من إعدادات التنفيذ.")
        if self.remaining_calls <= 0:
            raise ExecutionLimit("بلغت المهمة سقف استدعاءات النماذج المحدد.")

    def _attempt(self, connector, stage, system_prompt, user_message, temperature, max_tokens, fallback=False):
        provider = getattr(connector, "provider", "unknown")
        model = getattr(connector, "model_name", "unknown")
        with PROVIDER_GATE.slot(provider, model, self.policy.provider_concurrency, self.deadline):
            with self.lock:
                self.check()
                row = {"stage": stage, "provider": provider, "model": model, "fallback": fallback,
                       "status": "running", "input_tokens": None, "output_tokens": None, "total_tokens": None}
                self.calls.append(row)
            started = time.monotonic()
            connector.request_timeout = max(0.1, min(90.0, self.deadline - started))
            connector.last_result = {}
            try:
                if max_tokens is not None:
                    max_tokens = min(max_tokens, getattr(connector, "max_tokens_limit", max_tokens))
                answer = connector.complete(system_prompt=system_prompt, user_message=user_message,
                                            temperature=temperature, max_tokens=max_tokens)
                metadata = getattr(connector, "last_result", {}) or {}
                metadata["served_by"] = {"provider": provider, "model": model}
                connector.last_result = metadata
                usage = metadata.get("usage") or {}
                with self.lock:
                    row.update(status="failed" if _failed(answer) else "complete",
                               input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
                               total_tokens=usage.get("total_tokens"), finish_reason=metadata.get("finish_reason"))
                if metadata.get("status_code") == 429:
                    PROVIDER_GATE.pause(provider, model, metadata.get("retry_after") or 30)
                return answer, metadata.get("status_code")
            except Exception:
                with self.lock:
                    row["status"] = "failed"
                return "Error: تعذر الاتصال بالمصدر؛ لم تُنتج إجابة صالحة.", 503
            finally:
                with self.lock:
                    row["duration_ms"] = round((time.monotonic() - started) * 1000)

    def call(self, connector, stage, system_prompt, user_message, temperature, max_tokens, allow_fallback=True):
        self.check()
        try:
            answer, status = self._attempt(connector, stage, system_prompt, user_message, temperature, max_tokens)
        except ProviderBusy as exc:
            answer, status = "Error: " + str(exc), 429
        if (allow_fallback and _failed(answer) and status in (429, 500, 502, 503, 504)
                and self.fallback_factory and self.remaining_calls > 0):
            backup = self.fallback_factory()
            if (backup.provider, backup.model_name) != (connector.provider, connector.model_name):
                try:
                    answer, _ = self._attempt(backup, stage, system_prompt, user_message, temperature, max_tokens, True)
                    connector.last_result = dict(getattr(backup, "last_result", {}))
                except ProviderBusy:
                    pass
        return answer

    def summary(self):
        with self.lock:
            calls = [dict(row) for row in self.calls]
        known = [row for row in calls if row["total_tokens"] is not None]
        return {"model_calls": len(calls), "duration_ms": round((time.monotonic() - self.start) * 1000),
                "reported_tokens": sum(row["total_tokens"] for row in known),
                "usage_complete": len(known) == len(calls), "calls": calls}


class TrackedConnector:
    def __init__(self, inner, runtime, stage):
        self.inner, self.runtime, self.stage = inner, runtime, stage
        self.provider, self.model_name = inner.provider, inner.model_name

    def get_model_name(self):
        return self.model_name

    def complete(self, system_prompt, user_message, temperature=None, max_tokens=None):
        answer = self.runtime.call(self.inner, self.stage, system_prompt, user_message, temperature, max_tokens)
        actual = getattr(self.inner, "last_result", {}).get("served_by", {})
        self.provider = actual.get("provider", self.provider)
        self.model_name = actual.get("model", self.model_name)
        return answer
