import os
from groq import Groq
from .base import BaseConnector
import logging

logger = logging.getLogger(__name__)

class GroqConnector(BaseConnector):
    def __init__(self, model_name: str = "llama-3.3-70b-versatile"):
        self.model_name = model_name
        self.api_key = os.getenv("GROQ_API_KEY")
        self.client = None
        if self.api_key:
            try:
                self.client = Groq(api_key=self.api_key)
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
        if not self.client:
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

        try:
            response = self.client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except Exception as e:
            error_msg = str(e).lower()
            if "authentication" in error_msg or "api key" in error_msg or "unauthorized" in error_msg:
                return f"Authentication error / خطأ في المصادقة: {e}"
            elif "rate limit" in error_msg or "429" in error_msg:
                return f"Rate limit error / خطأ في حد المعدل: {e}"
            elif "request_too_large" in error_msg or "413" in error_msg:
                return f"Network or API error / خطأ في الشبكة أو واجهة برمجة التطبيقات: {e}"
            elif "not found" in error_msg or "model" in error_msg:
                return f"Model not found error / خطأ: النموذج غير موجود: {e}"
            else:
                return f"Network or API error / خطأ في الشبكة أو واجهة برمجة التطبيقات: {e}"
