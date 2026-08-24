"""Unit tests for alerting system and fail-safe dispatching."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from quant.observability.alerts import Alert, AlertDispatcher, AlertSink, LoggingAlertSink
from quant.observability.events import AlertSeverity, EventType


def test_logging_alert_sink():
    sink = LoggingAlertSink("test.alerts")
    alert = Alert(
        severity=AlertSeverity.CRITICAL,
        event_type=EventType.RISK_KILL_SWITCH,
        component="RiskEngine",
        message="Drawdown limit breached!",
        run_id="run_alert_01",
        details={"drawdown_pct": 0.22, "api_key": "sensitive_broker_key"},
    )

    sink.send_alert(alert)
    assert len(sink.alerts) == 1
    recorded = sink.alerts[0]
    assert recorded.severity == AlertSeverity.CRITICAL
    assert recorded.event_type == EventType.RISK_KILL_SWITCH
    assert recorded.details["api_key"] == "sensitive_broker_key"  # Original object
    # In serialized output, secrets are redacted:
    serialized = recorded.to_dict()
    assert serialized["details"]["api_key"] == "[REDACTED]"


class BrokenAlertSink(AlertSink):
    """Simulates a crashing network alert sink."""
    def send_alert(self, alert: Alert) -> None:
        raise ConnectionError("Network unreachable")


def test_alert_dispatcher_isolates_sink_failures():
    working_sink = LoggingAlertSink("test.working")
    broken_sink = BrokenAlertSink()

    dispatcher = AlertDispatcher([broken_sink, working_sink])
    alert = Alert(
        severity=AlertSeverity.WARNING,
        event_type=EventType.DATA_VALIDATION_FAILED,
        component="DataValidationGate",
        message="Gap anomaly detected",
    )

    # Dispatching should NOT raise exception despite broken_sink failure
    dispatcher.dispatch(alert)
    assert len(working_sink.alerts) == 1
