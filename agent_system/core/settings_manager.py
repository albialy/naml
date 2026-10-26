import copy
from datetime import datetime, timezone
from pathlib import Path
import yaml
from agent_system.core.database import get_database
from agent_system.core.role_cards import RoleCard
from pydantic import ValidationError
import re

# Offline suggestions only; live catalog is fetched on explicit refresh.
AVAILABLE_MODELS = {
    "groq": ["openai/gpt-oss-120b", "openai/gpt-oss-20b"],
    "openrouter": [],
}



class SettingsManager:
    def __init__(self):
        self.database = get_database()
        self.database.mutate_document("settings", lambda saved: saved if saved is not None else self._defaults())

    def _defaults(self):
        defaults = {"director": {"provider": "groq", "model": "openai/gpt-oss-120b", "temperature": 0.3, "max_tokens": 4096}, "workers": {}, "system": {"max_agents_per_task": 6, "max_debate_rounds": 3, "allow_user_registration": False, "default_language": "ar", "session_retention_days": 30}}
        config_dir = Path(__file__).resolve().parents[1] / "config"
        for filename in ["agents_template.yaml", "models.yaml"]:
            path = config_dir / filename
            if path.exists():
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                for key in ("director", "workers"):
                    if key in data:
                        defaults[key] = data[key]
        return defaults

    def get_settings(self):
        from agent_system.core.execution_policy import ExecutionPolicy
        current = self.database.get_document("settings")
        if "execution" not in current and "critic" in current.get("workers", {}):
            current["execution"] = {"critic_role": "critic"}
        current["execution"] = ExecutionPolicy(**current.get("execution", {})).model_dump()
        return current

    def update_execution(self, config, user_id):
        from agent_system.core.execution_policy import ExecutionPolicy
        config = ExecutionPolicy(**config).model_dump()
        def update(current):
            roles = {"director", *current.get("workers", {})}
            if any(config[key] and config[key] not in roles for key in
                   ("router_role", "single_role", "research_role", "critic_role", "fallback_role")):
                return False
            current["execution"] = config
        return self._change(user_id, "execution", update)

    def _validate_model_config(self, config):
        if config.get("role_card") is not None:
            try:
                RoleCard.model_validate(config["role_card"])
            except (ValidationError, TypeError):
                return False
        temperature = config.get("temperature")
        tokens = config.get("max_tokens")
        return (isinstance(temperature, (int, float)) and 0 <= temperature <= 1 and isinstance(tokens, int) and tokens > 0 and config.get("provider") in AVAILABLE_MODELS and isinstance(config.get("model"),str) and 0 < len(config["model"]) <= 200 and not any(c.isspace() for c in config["model"]))

    def _change(self, user_id, section, mutation):
        with self.database.connection(write=True) as conn:
            for key in ["settings", "settings_history", "activity_log"]:
                self.database.lock(conn, key)
            current = self.database._get(conn, "settings")
            old = copy.deepcopy(current)
            if mutation(current) is False:
                return False
            if current == old:
                return True
            timestamp = datetime.now(timezone.utc).isoformat()
            history = self.database._get(conn, "settings_history", [])
            history.insert(0, {"timestamp": timestamp, "performed_by": user_id, "section": section, "previous_full_settings": old})
            logs = self.database._get(conn, "activity_log", [])
            logs.append({"timestamp": timestamp, "action": "settings_changed", "performed_by": user_id, "change": {"section": section, "old_value": old, "new_value": copy.deepcopy(current)}})
            self.database._put(conn, "settings", current)
            self.database._put(conn, "settings_history", history[:20])
            self.database._put(conn, "activity_log", logs)
        return True

    def update_director(self, config, user_id):
        if not self._validate_model_config(config):
            return False
        return self._change(user_id, "director", lambda current: current["director"].update(config))

    def update_worker(self, worker_type, config, user_id):
        if not self._validate_model_config(config):
            return False
        def update(current):
            if worker_type not in current["workers"]:
                return False
            current["workers"][worker_type].update(config)
        return self._change(user_id, "workers." + worker_type, update)

    def add_worker(self, worker_type, config, user_id):
        if (not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", worker_type)
                or worker_type == "director" or not self._validate_model_config(config)):
            return False
        def add(current):
            if worker_type in current["workers"]:
                return False
            current["workers"][worker_type] = config
        return self._change(user_id, "workers", add)

    def remove_worker(self, worker_type, user_id):
        def remove(current):
            if worker_type not in current["workers"] or len(current["workers"]) <= 1:
                return False
            del current["workers"][worker_type]
            for role, value in current.get("execution", {}).items():
                if role.endswith("_role") and value == worker_type:
                    current["execution"][role] = "" if role == "fallback_role" else "director"
        return self._change(user_id, "workers", remove)

    def update_system(self, config, user_id):
        limits = {"max_agents_per_task": (1, 20), "max_debate_rounds": (1, 10), "session_retention_days": (1, 3650)}
        for key, (minimum, maximum) in limits.items():
            if key in config and (not isinstance(config[key], int) or not minimum <= config[key] <= maximum):
                return False
        return self._change(user_id, "system", lambda current: current["system"].update(config))

    def restore_history(self, history_index, user_id):
        history = self.database.get_document("settings_history", [])
        if history_index < 0 or history_index >= len(history):
            return False
        previous = history[history_index].get("previous_full_settings")
        if not previous:
            return False
        def restore(current):
            current.clear()
            current.update(copy.deepcopy(previous))
        return self._change(user_id, "RESTORE", restore)


settings_manager = SettingsManager()
