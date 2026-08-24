"""Execution run context and correlation tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..core.enums import ExecutionMode


@dataclass
class RunContext:
    """Carries execution metadata, environment mode, and correlation IDs across components."""

    run_id: str
    execution_mode: ExecutionMode
    strategy_id: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    code_version: str = "1.0.0"
    correlation_ids: dict[str, str] = field(default_factory=dict)

    def bind_correlation(self, key: str, value: str) -> None:
        """Binds a correlation identifier (e.g. portfolio_id, order_batch_id, fill_id)."""
        self.correlation_ids[key] = value

    def get_correlation(self, key: str) -> str | None:
        """Retrieves a bound correlation identifier."""
        return self.correlation_ids.get(key)

    def to_dict(self) -> dict:
        """Serializes context for structured logging or telemetry."""
        return {
            "run_id": self.run_id,
            "execution_mode": self.execution_mode.value,
            "strategy_id": self.strategy_id,
            "started_at": self.started_at.isoformat(),
            "code_version": self.code_version,
            "correlation_ids": dict(self.correlation_ids),
        }
