import json
import os
import yaml
from datetime import datetime
from typing import Dict, Any, List, Optional
from agent_system.core.auth.manager import auth_manager

STORAGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'storage')
SETTINGS_FILE = os.path.join(STORAGE_DIR, 'settings.json')
SETTINGS_HISTORY_FILE = os.path.join(STORAGE_DIR, 'settings_history.json')
MODELS_YAML_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config', 'models.yaml')

AVAILABLE_MODELS = {
   "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "qwen/qwen3-32b",
        "groq/compound",
        "gemma2-9b-it"
    ],
    "openrouter": [
        "qwen/qwen-72b-chat",
        "mistralai/mixtral-8x7b-instruct",
        "deepseek/deepseek-coder",
        "meta-llama/llama-3.1-405b-instruct"
    ]
}

class SettingsManager:
    def __init__(self):
        os.makedirs(STORAGE_DIR, exist_ok=True)
        self.settings = self._load_settings()

    def _load_settings(self) -> dict:
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
                
        # Initialize from models.yaml if missing
        settings = {
            "director": {
                "provider": "groq",
                "model": "llama-3.3-70b-versatile",
                "temperature": 0.3,
                "max_tokens": 4096
            },
            "workers": {},
            "system": {
                "max_agents_per_task": 6,
                "max_debate_rounds": 3,
                "allow_user_registration": False,
                "default_language": "ar",
                "session_retention_days": 30
            }
        }
        
        try:
            if os.path.exists(MODELS_YAML_FILE):
                with open(MODELS_YAML_FILE, 'r', encoding='utf-8') as f:
                    yaml_data = yaml.safe_load(f)
                    if yaml_data:
                        if "director" in yaml_data:
                            settings["director"] = yaml_data["director"]
                        if "workers" in yaml_data:
                            settings["workers"] = yaml_data["workers"]
        except Exception:
            pass
            
        self._save_settings_to_file(settings)
        return settings

    def _save_settings_to_file(self, settings_data: dict):
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings_data, f, indent=2)
            self.settings = settings_data
        except Exception as e:
            print(f"Failed to save settings: {e}")

    def _log_setting_change(self, performed_by: str, section: str, field: str, old_value: Any, new_value: Any):
        # Log to activity log
        change_info = {
            "section": section,
            "field": field,
            "old_value": old_value,
            "new_value": new_value
        }
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "action": "settings_changed",
            "performed_by": performed_by,
            "change": change_info
        }
        logs = []
        logs_file = os.path.join(STORAGE_DIR, 'activity_log.json')
        if os.path.exists(logs_file):
            try:
                with open(logs_file, 'r', encoding='utf-8') as f:
                    logs = json.load(f)
            except:
                pass
        logs.append(log_entry)
        try:
            with open(logs_file, 'w', encoding='utf-8') as f:
                json.dump(logs, f, indent=2)
        except:
            pass
            
        # Also log to settings history
        history = []
        if os.path.exists(SETTINGS_HISTORY_FILE):
            try:
                with open(SETTINGS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                    history = json.load(f)
            except:
                pass
                
        history_entry = {
            "timestamp": datetime.now().isoformat(),
            "performed_by": performed_by,
            "change": change_info,
            "previous_full_settings": self.settings
        }
        history.insert(0, history_entry)
        history = history[:20]  # Keep last 20
        
        try:
            with open(SETTINGS_HISTORY_FILE, 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=2)
        except:
            pass

    def get_settings(self) -> dict:
        return self._load_settings()

    def _validate_model_config(self, config: dict) -> bool:
        if not isinstance(config.get("temperature"), (int, float)) or config["temperature"] < 0.0 or config["temperature"] > 1.0:
            return False
        if not isinstance(config.get("max_tokens"), int) or config["max_tokens"] <= 0:
            return False
        provider = config.get("provider")
        if provider not in AVAILABLE_MODELS:
            return False
        if config.get("model") not in AVAILABLE_MODELS[provider]:
            return False
        return True

    def update_director(self, config: dict, user_id: str) -> bool:
        if not self._validate_model_config(config):
            return False
            
        current = self.get_settings()
        for k, v in config.items():
            old_val = current["director"].get(k)
            if old_val != v:
                self._log_setting_change(user_id, "director", k, old_val, v)
                
        current["director"].update(config)
        self._save_settings_to_file(current)
        return True

    def update_worker(self, worker_type: str, config: dict, user_id: str) -> bool:
        if not self._validate_model_config(config):
            return False
            
        current = self.get_settings()
        if worker_type not in current.get("workers", {}):
            return False
            
        for k, v in config.items():
            old_val = current["workers"][worker_type].get(k)
            if old_val != v:
                self._log_setting_change(user_id, f"workers.{worker_type}", k, old_val, v)
                
        current["workers"][worker_type].update(config)
        self._save_settings_to_file(current)
        return True

    def add_worker(self, worker_type: str, config: dict, user_id: str) -> bool:
        if not self._validate_model_config(config):
            return False
            
        current = self.get_settings()
        if worker_type in current.get("workers", {}):
            return False
            
        current["workers"][worker_type] = config
        self._save_settings_to_file(current)
        self._log_setting_change(user_id, "workers", worker_type, None, config)
        return True

    def remove_worker(self, worker_type: str, user_id: str) -> bool:
        current = self.get_settings()
        if worker_type not in current.get("workers", {}):
            return False
        if len(current.get("workers", {})) <= 1:
            return False
            
        old_val = current["workers"][worker_type]
        del current["workers"][worker_type]
        self._save_settings_to_file(current)
        self._log_setting_change(user_id, "workers", worker_type, old_val, None)
        return True

    def update_system(self, config: dict, user_id: str) -> bool:
        current = self.get_settings()
        for k, v in config.items():
            old_val = current["system"].get(k)
            if old_val != v:
                self._log_setting_change(user_id, "system", k, old_val, v)
                
        current["system"].update(config)
        self._save_settings_to_file(current)
        return True

    def restore_history(self, history_index: int, user_id: str) -> bool:
        if not os.path.exists(SETTINGS_HISTORY_FILE):
            return False
        try:
            with open(SETTINGS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
                
            if history_index < 0 or history_index >= len(history):
                return False
                
            historical_state = history[history_index].get("previous_full_settings")
            if not historical_state:
                return False
                
            self._save_settings_to_file(historical_state)
            self._log_setting_change(user_id, "system", "RESTORE", None, f"Restored from history index {history_index}")
            return True
        except:
            return False

settings_manager = SettingsManager()
