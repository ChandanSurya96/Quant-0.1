"""Unit tests for structured logging and secret redaction."""

from __future__ import annotations

from quant.core.enums import ExecutionMode
from quant.observability.context import RunContext
from quant.observability.events import EventType
from quant.observability.logging import StructuredLogger, redact_secrets


def test_structured_event_emitted():
    logger = StructuredLogger("test.logger")
    record = logger.log_event(
        event_type=EventType.STRATEGY_STARTED,
        level="INFO",
        component="SystematicMacroStrategy",
        message="Starting factor calculation",
    )
    assert record["event_type"] == "STRATEGY_STARTED"
    assert record["level"] == "INFO"
    assert record["component"] == "SystematicMacroStrategy"
    assert record["message"] == "Starting factor calculation"
    assert "timestamp" in record


def test_run_context_propagation():
    ctx = RunContext(
        run_id="run_test_999",
        execution_mode=ExecutionMode.PAPER,
        strategy_id="macro_v1",
    )
    ctx.bind_correlation("portfolio_id", "tp_999")
    ctx.bind_correlation("decision_id", "dec_999")

    logger = StructuredLogger("test.logger")
    record = logger.log_event(
        event_type=EventType.RISK_APPROVED,
        level="INFO",
        component="RiskEngine",
        message="Target portfolio passed all pre-trade risk controls",
        context=ctx,
    )

    assert record["run_id"] == "run_test_999"
    assert record["execution_mode"] == "PAPER"
    assert record["strategy_id"] == "macro_v1"
    assert record["correlation_ids"]["portfolio_id"] == "tp_999"
    assert record["correlation_ids"]["decision_id"] == "dec_999"


def test_secret_redaction():
    sensitive_data = {
        "user": "quant_trader",
        "api_key": "secret_alphavantage_key_12345",
        "token": "bearer_jwt_token_98765",
        "password": "super_secret_password",
        "broker_secret": "ib_gateway_secret",
        "nested": {
            "auth_token": "token_nested_111",
            "safe_value": 42.0,
            "private_key": "-----BEGIN RSA PRIVATE KEY-----",
        },
        "list_of_secrets": [
            {"access_token": "token_in_list"},
            "safe_string",
        ],
    }

    clean = redact_secrets(sensitive_data)
    assert clean["user"] == "quant_trader"
    assert clean["api_key"] == "[REDACTED]"
    assert clean["token"] == "[REDACTED]"
    assert clean["password"] == "[REDACTED]"
    assert clean["broker_secret"] == "[REDACTED]"
    assert clean["nested"]["auth_token"] == "[REDACTED]"
    assert clean["nested"]["safe_value"] == 42.0
    assert clean["nested"]["private_key"] == "[REDACTED]"
    assert clean["list_of_secrets"][0]["access_token"] == "[REDACTED]"
    assert clean["list_of_secrets"][1] == "safe_string"
