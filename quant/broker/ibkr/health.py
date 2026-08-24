"""Interactive Brokers health checking and connection telemetry."""

from __future__ import annotations

from datetime import datetime, timezone

from ...observability.events import HealthState
from ...observability.health import ComponentHealth


class IBKRHealthTracker:
    """Tracks socket connectivity, heartbeat latency, and error states for IBKR adapter."""

    def __init__(self) -> None:
        self.is_connected: bool = False
        self.last_heartbeat: datetime | None = None
        self.last_error: str | None = None
        self.consecutive_failures: int = 0

    def record_connected(self) -> None:
        self.is_connected = True
        self.last_heartbeat = datetime.now(timezone.utc)
        self.consecutive_failures = 0
        self.last_error = None

    def record_disconnected(self, error: str | None = None) -> None:
        self.is_connected = False
        self.consecutive_failures += 1
        self.last_error = error

    def record_heartbeat(self) -> None:
        self.last_heartbeat = datetime.now(timezone.utc)

    def check_health(self) -> ComponentHealth:
        """Returns normalized ComponentHealth for the IBKR adapter."""
        now = datetime.now(timezone.utc)
        if not self.is_connected:
            return ComponentHealth(
                name="ibkr_broker_adapter",
                state=HealthState.FAILED,
                message=f"IBKR disconnected: {self.last_error or 'No active socket session'}",
                checked_at=now,
                details={"consecutive_failures": self.consecutive_failures},
            )

        if self.last_heartbeat is not None:
            age = (now - self.last_heartbeat).total_seconds()
            if age > 30.0:
                return ComponentHealth(
                    name="ibkr_broker_adapter",
                    state=HealthState.DEGRADED,
                    message=f"IBKR heartbeat stale ({age:.1f}s since last message)",
                    checked_at=now,
                    details={"heartbeat_age_seconds": age},
                )

        return ComponentHealth(
            name="ibkr_broker_adapter",
            state=HealthState.HEALTHY,
            message="IBKR connection active and responsive",
            checked_at=now,
        )

    def status_string(self) -> str:
        """Returns standard status string ('CONNECTED', 'DISCONNECTED', 'UNKNOWN')."""
        if self.is_connected:
            return "CONNECTED"
        return "DISCONNECTED"
