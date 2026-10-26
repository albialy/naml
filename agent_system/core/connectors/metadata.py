"""Only provider counters/HTTP status enter task telemetry, never response bodies."""
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def retry_seconds(headers):
    value = (headers or {}).get("retry-after")
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else None
    except (TypeError, ValueError):
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def usage_counts(usage):
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, dict):
        return {}
    return {key: value for key in ("prompt_tokens", "completion_tokens", "total_tokens")
            if isinstance(value := usage.get(key), int) and not isinstance(value, bool) and value >= 0}
