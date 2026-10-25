from types import SimpleNamespace
import pytest
from agent_system.core.connectors.groq_connector import GroqConnector
from agent_system.core.connectors.openrouter_connector import OpenRouterConnector
from agent_system.core.connectors.metadata import retry_seconds


def test_groq_reports_usage_and_limits_reasoning_parameter_to_supported_models(monkeypatch):
    seen = []
    response = SimpleNamespace(usage={"prompt_tokens": 6, "completion_tokens": 2, "total_tokens": 8},
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="answer"))])
    def create(**kwargs):
        seen.append(kwargs)
        return response
    connector = GroqConnector()
    connector.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    connector.reasoning_effort = "low"
    connector.request_timeout = 7
    assert connector.complete("system", "user", 0.1, 1024) == "answer"
    assert seen[0]["reasoning_effort"] == "low" and seen[0]["timeout"] == 7
    assert connector.last_result["usage"]["total_tokens"] == 8
    connector.model_name = "custom/model"
    connector.complete("system", "user", 0.1, 1024)
    assert "reasoning_effort" not in seen[1]


def test_groq_sdk_has_no_hidden_retries(monkeypatch):
    from agent_system.core.connectors import groq_connector
    captured = []
    monkeypatch.setenv("GROQ_API_KEY", "fake-test-value")
    monkeypatch.setattr(groq_connector, "Groq", lambda **kwargs: captured.append(kwargs))
    GroqConnector()
    assert captured[0]["max_retries"] == 0


@pytest.mark.parametrize("status", [200, 429, 401])
def test_openrouter_captures_usage_and_retry_after_without_secret_logging(monkeypatch, status):
    from agent_system.core.connectors import openrouter_connector
    body = {"choices": [{"finish_reason": "stop", "message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}}
    response = SimpleNamespace(status_code=status, headers={"retry-after": "45"}, json=lambda: body)
    monkeypatch.setattr(openrouter_connector.requests, "post", lambda *a, **kwargs: response)
    connector = OpenRouterConnector("test/model")
    connector.api_key = "fake-test-value"
    answer = connector.complete("system", "user", 0, 512)
    assert connector.last_result["status_code"] == status
    assert connector.last_result["retry_after"] == 45
    if status == 200:
        assert answer == "ok" and connector.last_result["usage"]["total_tokens"] == 7
    else:
        assert answer.startswith("Error:")
    assert "fake-test-value" not in str(connector.last_result)


def test_bad_retry_header_is_not_a_sleep_forever():
    assert retry_seconds({"retry-after": "nan"}) is None
    assert retry_seconds({"retry-after": "garbage"}) is None
