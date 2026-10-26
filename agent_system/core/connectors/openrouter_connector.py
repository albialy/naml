import os
import requests
from agent_system.core.connectors.base import BaseConnector
import logging

logger = logging.getLogger(__name__)

class OpenRouterConnector(BaseConnector):
    provider = "openrouter"

    def __init__(self, model_name: str = ""):
        self.model_name = model_name
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.last_result = {}
        self.request_timeout = 90.0
        
        # Build headers dictionary
        self.headers = {}
        if self.api_key:
            self.headers["Authorization"] = f"Bearer {self.api_key}"
        self.headers["HTTP-Referer"] = "http://localhost:3000"
        self.headers["X-Title"] = "AgentSystem"

    def get_model_name(self) -> str:
        return self.model_name

    def validate_connection(self) -> bool:
        if not self.api_key:
            logger.error("OpenRouter API key not found / مفتاح API لـ OpenRouter غير موجود")
            return False
        # Minimal test
        try:
            response = requests.get("https://openrouter.ai/api/v1/models", headers=self.headers, timeout=15)
            if response.status_code == 200:
                return True
            else:
                logger.error(f"OpenRouter connection failed: {response.text} / فشل اتصال OpenRouter")
                return False
        except Exception as e:
            logger.error(f"OpenRouter network error: {e} / خطأ في شبكة OpenRouter")
            return False

    def complete(self, system_prompt: str, user_message: str, temperature: float, max_tokens: int) -> str:
        self.last_result = {}
        if not self.api_key:
            self.last_result = {"status_code": 401}
            return "Error: OpenRouter API key missing / خطأ: مفتاح OpenRouter مفقود"

        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        try:
            from .metadata import usage_counts, retry_seconds
            response = requests.post(self.base_url, headers=self.headers, json=payload, timeout=self.request_timeout)
            self.last_result = {"status_code": response.status_code, "retry_after": retry_seconds(response.headers)}
            response_data = response.json()
            
            if response.status_code == 200:
                if response_data.get("error"):
                    from .errors import failure, error_code
                    self.last_result["status_code"] = response_data["error"].get("code", 502)
                    return failure("OpenRouter", self.model_name, self.last_result["status_code"], error_code(response_data))
                self.last_result.update(usage=usage_counts(response_data.get("usage")),
                                        finish_reason=response_data.get("choices", [{}])[0].get("finish_reason"))
                text=response_data.get("choices", [{}])[0].get("message", {}).get("content")
                if not text or not text.strip():
                    return "Error: OpenRouter أعاد ردًا فارغًا للنموذج " + self.model_name
                return text
            from .errors import failure,error_code
            return failure("OpenRouter",self.model_name,response.status_code,error_code(response_data))
        except Exception:
            from .errors import failure
            if not self.last_result.get("status_code") or self.last_result.get("status_code") == 200:
                self.last_result["status_code"] = 502
            return failure("OpenRouter",self.model_name)
