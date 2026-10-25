import os
from groq import Groq
from .base import BaseConnector
import logging

logger = logging.getLogger(__name__)

class GroqConnector(BaseConnector):
    provider = "groq"

    def __init__(self, model_name: str = "openai/gpt-oss-20b"):
        self.model_name = model_name
        self.api_key = os.getenv("GROQ_API_KEY")
        self.client = None
        self.last_result = {}
        self.request_timeout = 90.0
        self.reasoning_effort = None
        if self.api_key:
            try:
                # Retries are controlled by Naml, so one recorded call is one API attempt.
                self.client = Groq(api_key=self.api_key, max_retries=0, timeout=90.0)
            except Exception as e:
                logger.error(f"Failed to initialize Groq client: {e} / فشل في تهيئة عميل Groq")

    def get_model_name(self) -> str:
        return self.model_name

    def validate_connection(self) -> bool:
        if not self.api_key:
            logger.error("Groq API key not found / مفتاح API لـ Groq غير موجود")
            return False
        if not self.client:
            return False
        try:
            self.client.models.list()
            return True
        except Exception as e:
            logger.error(f"Groq connection validation failed: {e} / فشل التحقق من اتصال Groq")
            return False

    def complete(self, system_prompt: str, user_message: str, temperature=None, max_tokens=None) -> str:
        """Params are OPTIONAL: pass None to omit them from the request.
        Compound systems reject some params with a misleading 413, so web
        researcher calls send only what is strictly needed."""
        self.last_result = {}
        if not self.client:
            self.last_result = {"status_code": 401}
            return "Error: Groq client not initialized / خطأ: لم يتم تهيئة عميل Groq"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        kwargs = {"messages": messages, "model": self.model_name}
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if self.reasoning_effort and self.model_name in ("openai/gpt-oss-20b", "openai/gpt-oss-120b"):
            kwargs["reasoning_effort"] = self.reasoning_effort
            kwargs["include_reasoning"] = False

        try:
            from .metadata import usage_counts
            response = self.client.chat.completions.create(**kwargs, timeout=self.request_timeout)
            self.last_result = {"status_code": 200, "usage": usage_counts(response.usage),
                                "finish_reason": response.choices[0].finish_reason}
            text = response.choices[0].message.content
            if not text or not text.strip():
                return "Error: Groq أعاد ردًا فارغًا للنموذج " + self.model_name
            return text
        except Exception as e:
            from .errors import failure, error_code
            from .metadata import retry_seconds
            self.last_result = {"status_code": getattr(e, "status_code", None) or 503,
                                "retry_after": retry_seconds(getattr(getattr(e, "response", None), "headers", {}))}
            return failure("Groq",self.model_name,getattr(e,"status_code",None),error_code(getattr(e,"body",{})))
