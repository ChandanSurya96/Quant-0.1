"""Polygon.io client interface, REST transport, and deterministic simulation client."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from .errors import (
    PolygonAuthenticationError,
    PolygonBadResponseError,
    PolygonConnectionError,
    PolygonRateLimitedError,
    PolygonUnknownStatusError,
)
from .models import PolygonAggregateBar, PolygonConfig

OK_STATUSES = frozenset({"OK", "DELAYED"})


class PolygonClientProtocol(ABC):
    """Abstract protocol for low-level Polygon.io communication."""

    @abstractmethod
    def fetch_daily_aggregates(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> list[PolygonAggregateBar]:
        """Fetches daily aggregate bars for `ticker` between ISO dates `start` and `end` inclusive."""
        raise NotImplementedError


class PolygonRestClient(PolygonClientProtocol):
    """HTTP transport for the Polygon.io aggregates API using only the standard library."""

    def __init__(self, config: PolygonConfig | None = None) -> None:
        self.config = config or PolygonConfig()
        self.config.validate_credentials()

    def fetch_daily_aggregates(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> list[PolygonAggregateBar]:
        """Fetches daily bars, following `next_url` pagination up to `max_pages`."""
        path = f"/v2/aggs/ticker/{urllib.parse.quote(ticker)}/range/1/day/{start}/{end}"
        query = urllib.parse.urlencode(
            {
                "adjusted": "true" if self.config.adjusted else "false",
                "sort": "asc",
                "limit": 50000,
            }
        )
        url: str | None = f"{self.config.base_url}{path}?{query}"

        bars: list[PolygonAggregateBar] = []
        pages = 0
        while url is not None and pages < self.config.max_pages:
            payload = self._request(url)
            bars.extend(self._parse_results(payload, ticker))
            url = payload.get("next_url")
            pages += 1
            if url is not None and self.config.pace_seconds > 0:
                time.sleep(self.config.pace_seconds)

        return bars

    def _request(self, url: str) -> dict:
        """Issues one authenticated GET with 429-aware retry, returning the decoded payload."""
        raw = b""

        for attempt in range(1, self.config.retries + 1):
            request = urllib.request.Request(url, method="GET")
            request.add_header("Authorization", f"Bearer {self.config.api_key}")
            request.add_header("Accept", "application/json")

            try:
                with urllib.request.urlopen(request, timeout=self.config.timeout_seconds) as response:
                    raw = response.read()
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise PolygonAuthenticationError(
                        f"Polygon rejected the API key (HTTP {exc.code}). Ingestion failed closed."
                    ) from exc
                if exc.code == 429:
                    if attempt < self.config.retries:
                        time.sleep(self.config.pause * attempt)
                        continue
                    raise PolygonRateLimitedError(
                        f"Polygon rate limit hit (HTTP 429) after {self.config.retries} attempts. "
                        "Ingestion failed closed."
                    ) from exc
                if attempt < self.config.retries:
                    time.sleep(self.config.pause)
                    continue
                raise PolygonConnectionError(
                    f"Polygon request failed with HTTP {exc.code} after {self.config.retries} attempts "
                    f"(last error: {exc}). Ingestion failed closed."
                ) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt < self.config.retries:
                    time.sleep(self.config.pause)
                    continue
                raise PolygonConnectionError(
                    f"Polygon transport failed after {self.config.retries} attempts "
                    f"(last error: {exc}). Ingestion failed closed."
                ) from exc

        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise PolygonBadResponseError(f"Polygon returned a non-JSON payload: {exc}") from exc

        if not isinstance(payload, dict):
            raise PolygonBadResponseError(
                f"Polygon returned {type(payload).__name__}, expected a JSON object."
            )

        return payload

    @staticmethod
    def _parse_results(payload: dict, ticker: str) -> list[PolygonAggregateBar]:
        """Validates the response status and converts raw result rows to aggregate bars."""
        status = payload.get("status")
        if status is None:
            raise PolygonBadResponseError(f"Polygon response for {ticker!r} has no 'status' field.")
        if status == "NOT_AUTHORIZED":
            message = payload.get("error") or payload.get("message") or "no detail supplied"
            raise PolygonAuthenticationError(
                f"Polygon denied access for {ticker!r}: {message}. Ingestion failed closed."
            )
        if status == "ERROR":
            message = payload.get("error") or payload.get("message") or "no detail supplied"
            raise PolygonBadResponseError(f"Polygon reported an error for {ticker!r}: {message}")
        if status not in OK_STATUSES:
            raise PolygonUnknownStatusError(
                f"Polygon returned unrecognized status {status!r} for {ticker!r}. Failing closed."
            )

        rows = payload.get("results") or []
        bars: list[PolygonAggregateBar] = []
        for row in rows:
            try:
                bars.append(
                    PolygonAggregateBar(
                        timestamp_ms=int(row["t"]),
                        open=float(row["o"]),
                        high=float(row["h"]),
                        low=float(row["l"]),
                        close=float(row["c"]),
                        volume=float(row.get("v", 0.0)),
                        vwap=float(row["vw"]) if row.get("vw") is not None else None,
                        transactions=int(row["n"]) if row.get("n") is not None else None,
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PolygonBadResponseError(
                    f"Polygon returned a malformed aggregate row for {ticker!r}: {row!r} ({exc})"
                ) from exc
        return bars


class MockPolygonClient(PolygonClientProtocol):
    """Deterministic, testable mock of the Polygon.io aggregates API."""

    def __init__(
        self,
        config: PolygonConfig | None = None,
        bars_by_ticker: dict[str, list[PolygonAggregateBar]] | None = None,
    ) -> None:
        self.config = config or PolygonConfig(api_key="mock_key")
        self._bars: dict[str, list[PolygonAggregateBar]] = dict(bars_by_ticker or {})
        self._errors: dict[str, Exception] = {}
        self.calls: list[tuple[str, str, str]] = []

    def set_bars(self, ticker: str, bars: list[PolygonAggregateBar]) -> None:
        """Registers the aggregate bars the mock will return for `ticker`."""
        self._bars[ticker] = list(bars)

    def set_error(self, ticker: str, error: Exception) -> None:
        """Registers an exception the mock will raise when `ticker` is requested."""
        self._errors[ticker] = error

    def fetch_daily_aggregates(
        self,
        ticker: str,
        start: str,
        end: str,
    ) -> list[PolygonAggregateBar]:
        """Returns the registered bars for `ticker`, or raises the registered error."""
        self.calls.append((ticker, start, end))
        if ticker in self._errors:
            raise self._errors[ticker]
        return list(self._bars.get(ticker, []))
