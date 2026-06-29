import os
import requests
from .base import BaseConnector
import logging

logger = logging.getLogger(__name__)

class OpenRouterConnector(BaseConnector):
    def __init__(self, model_name: str = "qwen/qwen-72b-chat"):
        self.model_name = model_name
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        
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
            response = requests.get("https://openrouter.ai/api/v1/models", headers=self.headers)
            if response.status_code == 200:
                return True
            else:
                logger.error(f"OpenRouter connection failed: {response.text} / فشل اتصال OpenRouter")
                return False
        except Exception as e:
            logger.error(f"OpenRouter network error: {e} / خطأ في شبكة OpenRouter")
            return False

    def complete(self, system_prompt: str, user_message: str, temperature: float, max_tokens: int) -> str:
        if not self.api_key:
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
            response = requests.post(self.base_url, headers=self.headers, json=payload)
            response_data = response.json()
            
            if response.status_code == 200:
                return response_data["choices"][0]["message"]["content"]
            else:
                error_msg = response.text.lower()
                if "authentication" in error_msg or "unauthorized" in error_msg or response.status_code == 401:
                    return f"Authentication error / خطأ في المصادقة: {response.text}"
                elif "rate limit" in error_msg or response.status_code == 429:
                    return f"Rate limit error / خطأ في حد المعدل: {response.text}"
                elif "not found" in error_msg or response.status_code == 404:
                    return f"Model not found error / خطأ: النموذج غير موجود: {response.text}"
                else:
                    return f"API error / خطأ في واجهة برمجة التطبيقات: {response.text}"
        except Exception as e:
            return f"Network error / خطأ في الشبكة: {e}"
