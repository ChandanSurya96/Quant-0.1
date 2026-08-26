"""Data models and configuration for the Polygon.io market data provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os

DEFAULT_BASE_URL = "https://api.polygon.io"


@dataclass(frozen=True)
class PolygonConfig:
    """Configuration for Polygon.io connectivity, pacing, and retry budget."""

    api_key: str = field(default_factory=lambda: os.getenv("POLYGON_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.getenv("POLYGON_BASE_URL", DEFAULT_BASE_URL))
    timeout_seconds: float = 10.0
    retries: int = 3
    pause: float = 2.0
    pace_seconds: float = field(default_factory=lambda: float(os.getenv("POLYGON_PACE_SECONDS", "0.0")))
    adjusted: bool = True
    max_pages: int = 10

    def validate_credentials(self) -> None:
        """Enforces that an API key is present. Polygon is never reachable anonymously."""
        if not self.api_key or not self.api_key.strip():
            from .errors import PolygonAuthenticationError

            raise PolygonAuthenticationError(
                "POLYGON_API_KEY is not set. Polygon requires an API key; ingestion failed closed."
            )


@dataclass(frozen=True)
class PolygonAggregateBar:
    """A single daily aggregate bar as reported by Polygon.io."""

    timestamp_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    vwap: float | None = None
    transactions: int | None = None

    @property
    def timestamp(self) -> datetime:
        """UTC timestamp of the aggregate window start."""
        return datetime.fromtimestamp(self.timestamp_ms / 1000.0, tz=timezone.utc)
