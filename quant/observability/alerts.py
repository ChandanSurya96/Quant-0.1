"""Alert abstractions, severity levels, and dispatch sinks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging

from .events import AlertSeverity, EventType
from .logging import redact_secrets


@dataclass(frozen=True)
class Alert:
    """Standardized operational alert notification."""

    severity: AlertSeverity
    event_type: EventType
    component: str
    message: str
    run_id: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "severity": self.severity.value,
            "event_type": self.event_type.value,
            "component": self.component,
            "message": self.message,
            "run_id": self.run_id,
            "details": redact_secrets(self.details),
        }


class AlertSink(ABC):
    """Abstract sink for operational alerts (e.g. Logging, Telegram, Email)."""

    @abstractmethod
    def send_alert(self, alert: Alert) -> None:
        """Transmits an alert to the destination channel."""
        raise NotImplementedError


class LoggingAlertSink(AlertSink):
    """Local logging alert sink for Paper / Research environments."""

    def __init__(self, logger_name: str = "quant.alerts") -> None:
        self.logger = logging.getLogger(logger_name)
        self.alerts: list[Alert] = []

    def send_alert(self, alert: Alert) -> None:
        """Records alert in memory and emits a structured JSON alert log."""
        self.alerts.append(alert)
        clean_dict = alert.to_dict()
        level_map = {
            AlertSeverity.INFO: logging.INFO,
            AlertSeverity.WARNING: logging.WARNING,
            AlertSeverity.CRITICAL: logging.CRITICAL,
        }
        log_level = level_map.get(alert.severity, logging.INFO)
        self.logger.log(log_level, f"[ALERT] {json.dumps(clean_dict)}")


class AlertDispatcher:
    """Manages and dispatches alerts to registered sinks."""

    def __init__(self, sinks: list[AlertSink] | None = None) -> None:
        self.sinks: list[AlertSink] = sinks or [LoggingAlertSink()]

    def register_sink(self, sink: AlertSink) -> None:
        self.sinks.append(sink)

    def dispatch(self, alert: Alert) -> None:
        """Dispatches an alert to all registered sinks with fail-safe error isolation."""
        for sink in self.sinks:
            try:
                sink.send_alert(alert)
            except Exception as e:
                # Never crash the main execution pipeline on alerting sink failures
                logging.getLogger("quant.alerts").error(f"Failed to dispatch alert to {sink}: {e}")
