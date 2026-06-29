from abc import ABC, abstractmethod

class BaseConnector(ABC):
    @abstractmethod
    def complete(self, system_prompt: str, user_message: str, temperature: float, max_tokens: int) -> str:
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        pass

    @abstractmethod
    def validate_connection(self) -> bool:
        pass
