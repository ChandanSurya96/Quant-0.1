"""Structured JSON logging with automatic secret redaction."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any

from .context import RunContext
from .events import EventType

SENSITIVE_KEY_PATTERN = re.compile(
    r"(api_?key|token|password|secret|auth|credential|private_?key)",
    re.IGNORECASE,
)


def redact_secrets(obj: Any) -> Any:
    """Recursively redacts sensitive keys and values from data structures."""
    if isinstance(obj, dict):
        redacted = {}
        for k, v in obj.items():
            if isinstance(k, str) and SENSITIVE_KEY_PATTERN.search(k):
                if isinstance(v, (dict, list)):
                    redacted[k] = redact_secrets(v)
                else:
                    redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_secrets(v)
        return redacted
    elif isinstance(obj, list):
        return [redact_secrets(item) for item in obj]
    elif isinstance(obj, str):
        if any(token in obj.lower() for token in ["bearer ", "secret=", "password="]):
            return "[REDACTED]"
        return obj
    return obj


class StructuredLogger:
    """Standardized structured JSON logger for operational traceability."""

    def __init__(self, logger_name: str = "quant.system") -> None:
        self.logger = logging.getLogger(logger_name)

    def log_event(
        self,
        event_type: EventType,
        level: str,
        component: str,
        message: str,
        context: RunContext | None = None,
        extra: dict | None = None,
    ) -> dict:
        """Emits a structured log event with correlation tracking and secret redaction."""
        now_iso = datetime.now(timezone.utc).isoformat()
        clean_extra = redact_secrets(extra or {})

        record = {
            "timestamp": now_iso,
            "level": level.upper(),
            "component": component,
            "event_type": event_type.value,
            "message": message,
        }

        if context is not None:
            record["run_id"] = context.run_id
            record["execution_mode"] = context.execution_mode.value
            record["strategy_id"] = context.strategy_id
            record["code_version"] = context.code_version
            if context.correlation_ids:
                record["correlation_ids"] = dict(context.correlation_ids)

        if clean_extra:
            record["extra"] = clean_extra

        log_level = getattr(logging, level.upper(), logging.INFO)
        self.logger.log(log_level, json.dumps(record))
        return record

    def info(self, message: str, **kwargs: Any) -> dict:
        return self.log_event(EventType.STRATEGY_STARTED, "INFO", "system", message, extra=kwargs)

    def warning(self, message: str, **kwargs: Any) -> dict:
        return self.log_event(EventType.SYSTEM_STOPPED, "WARNING", "system", message, extra=kwargs)

    def error(self, message: str, **kwargs: Any) -> dict:
        return self.log_event(EventType.SYSTEM_RECOVERY_REQUIRED, "ERROR", "system", message, extra=kwargs)

    def critical(self, message: str, **kwargs: Any) -> dict:
        return self.log_event(EventType.SYSTEM_RECOVERY_REQUIRED, "CRITICAL", "system", message, extra=kwargs)
