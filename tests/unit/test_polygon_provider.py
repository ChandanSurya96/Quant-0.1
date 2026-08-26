"""Unit tests for the fail-closed Polygon.io market data provider."""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import patch

import pytest

from quant.core.enums import ExecutionMode
from quant.core.exceptions import AnomalyGapError, DataError, FailClosedDataError
from quant.data.providers.polygon import (
    MockPolygonClient,
    PolygonAggregateBar,
    PolygonAuthenticationError,
    PolygonBadResponseError,
    PolygonConfig,
    PolygonConnectionError,
    PolygonError,
    PolygonMapper,
    PolygonNoDataError,
    PolygonProvider,
    PolygonRateLimitedError,
    PolygonRestClient,
    PolygonUnknownStatusError,
)

DAY_MS = 86_400_000
BASE_MS = 1_704_153_600_000  # 2024-01-02T00:00:00Z


def make_bars(
    count: int,
    base_price: float = 100.0,
    start_ms: int = BASE_MS,
) -> list[PolygonAggregateBar]:
    """Builds a deterministic ascending run of daily aggregate bars."""
    return [
        PolygonAggregateBar(
            timestamp_ms=start_ms + (i * DAY_MS),
            open=base_price + i,
            high=base_price + i + 1.0,
            low=base_price + i - 1.0,
            close=base_price + i,
            volume=1_000_000.0,
        )
        for i in range(count)
    ]


class _FakeResponse:
    """Minimal stand-in for the context manager urlopen returns."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


def ok_payload(rows: list[dict] | None = None, next_url: str | None = None) -> bytes:
    """Serialises a successful Polygon aggregates payload."""
    body: dict = {"status": "OK", "results": rows if rows is not None else []}
    if next_url is not None:
        body["next_url"] = next_url
    return json.dumps(body).encode("utf-8")


def http_error(code: int) -> urllib.error.HTTPError:
    """Builds an HTTPError carrying the given status code."""
    return urllib.error.HTTPError("https://api.polygon.io", code, "err", {}, None)


@pytest.fixture
def mock_client() -> MockPolygonClient:
    return MockPolygonClient(PolygonConfig(api_key="test_key"))


@pytest.fixture
def provider(mock_client: MockPolygonClient) -> PolygonProvider:
    return PolygonProvider(config=PolygonConfig(api_key="test_key"), client=mock_client)


# ---------------------------------------------------- 1. Configuration and credentials
def test_config_missing_api_key_fails_closed():
    """A blank API key is rejected before any network call is attempted."""
    cfg = PolygonConfig(api_key="")
    with pytest.raises(PolygonAuthenticationError, match="POLYGON_API_KEY is not set"):
        cfg.validate_credentials()


def test_config_whitespace_api_key_fails_closed():
    """A whitespace-only API key is treated as absent."""
    with pytest.raises(PolygonAuthenticationError):
        PolygonConfig(api_key="   ").validate_credentials()


def test_config_reads_api_key_from_environment(monkeypatch: pytest.MonkeyPatch):
    """POLYGON_API_KEY populates the config without an explicit argument."""
    monkeypatch.setenv("POLYGON_API_KEY", "env_key_value")
    assert PolygonConfig().api_key == "env_key_value"


def test_provider_without_client_requires_credentials(monkeypatch: pytest.MonkeyPatch):
    """Constructing the provider with no injected client validates the key fail-closed."""
    monkeypatch.setenv("POLYGON_API_KEY", "")
    with pytest.raises(PolygonAuthenticationError):
        PolygonProvider()


def test_polygon_errors_are_data_errors():
    """The Polygon hierarchy roots in the domain DataError so data gates catch it."""
    assert issubclass(PolygonError, DataError)
    for cls in (
        PolygonConnectionError,
        PolygonAuthenticationError,
        PolygonRateLimitedError,
        PolygonBadResponseError,
        PolygonNoDataError,
        PolygonUnknownStatusError,
    ):
        assert issubclass(cls, PolygonError)


# ---------------------------------------------------- 2. PolygonMapper
def test_mapper_converts_epoch_ms_to_tz_naive_dates():
    """Epoch milliseconds become a tz-naive normalised DatetimeIndex."""
    df = PolygonMapper.to_ohlcv_frame(make_bars(3))
    assert df.index.tz is None
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert str(df.index[0].date()) == "2024-01-02"


def test_mapper_sorts_and_deduplicates_by_date():
    """Repeated timestamps collapse to the last bar and the index comes back sorted."""
    bars = make_bars(3)
    duplicate = PolygonAggregateBar(
        timestamp_ms=bars[0].timestamp_ms, open=1.0, high=1.0, low=1.0, close=999.0, volume=5.0
    )
    df = PolygonMapper.to_ohlcv_frame([bars[2], bars[1], bars[0], duplicate])
    assert len(df) == 3
    assert df.index.is_monotonic_increasing
    assert df["Close"].iloc[0] == 999.0


def test_mapper_empty_bars_returns_empty_frame_and_series():
    """No bars produce empty containers rather than raising."""
    assert PolygonMapper.to_ohlcv_frame([]).empty
    assert PolygonMapper.to_close_series([]).empty


# ---------------------------------------------------- 3. PolygonRestClient transport
def test_rest_client_parses_successful_payload():
    """A well-formed OK payload maps to aggregate bars."""
    client = PolygonRestClient(PolygonConfig(api_key="test_key", pause=0.0))
    rows = [
        {"t": BASE_MS, "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.5, "v": 1_000_000, "vw": 100.2, "n": 42}
    ]
    with patch("urllib.request.urlopen", return_value=_FakeResponse(ok_payload(rows))):
        bars = client.fetch_daily_aggregates("SPY", "2024-01-01", "2024-01-31")
    assert len(bars) == 1
    assert bars[0].close == 100.5
    assert bars[0].transactions == 42


def test_rest_client_follows_next_url_pagination():
    """`next_url` is followed and results from every page are concatenated."""
    client = PolygonRestClient(PolygonConfig(api_key="test_key", pause=0.0, max_pages=5))
    page1 = ok_payload(
        [{"t": BASE_MS, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1}],
        next_url="https://api.polygon.io/next",
    )
    page2 = ok_payload([{"t": BASE_MS + DAY_MS, "o": 2.0, "h": 2.0, "l": 2.0, "c": 2.0, "v": 2}])
    with patch("urllib.request.urlopen", side_effect=[_FakeResponse(page1), _FakeResponse(page2)]):
        bars = client.fetch_daily_aggregates("SPY", "2024-01-01", "2024-01-31")
    assert [b.close for b in bars] == [1.0, 2.0]


def test_rest_client_stops_at_max_pages():
    """Pagination is bounded by max_pages so a cyclic next_url cannot spin forever."""
    client = PolygonRestClient(PolygonConfig(api_key="test_key", pause=0.0, max_pages=2))
    page = ok_payload(
        [{"t": BASE_MS, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1}],
        next_url="https://api.polygon.io/loop",
    )
    with patch("urllib.request.urlopen", return_value=_FakeResponse(page)) as mock_open:
        client.fetch_daily_aggregates("SPY", "2024-01-01", "2024-01-31")
    assert mock_open.call_count == 2


def test_rest_client_unauthorized_fails_closed():
    """HTTP 401 raises an authentication error without retrying."""
    client = PolygonRestClient(PolygonConfig(api_key="bad_key", pause=0.0, retries=3))
    with patch("urllib.request.urlopen", side_effect=http_error(401)) as mock_open:
        with pytest.raises(PolygonAuthenticationError, match="rejected the API key"):
            client.fetch_daily_aggregates("SPY", "2024-01-01", "2024-01-31")
    assert mock_open.call_count == 1


def test_rest_client_rate_limited_fails_closed_after_retries():
    """HTTP 429 is retried up to the budget and then fails closed."""
    client = PolygonRestClient(PolygonConfig(api_key="test_key", pause=0.0, retries=3))
    with patch("urllib.request.urlopen", side_effect=http_error(429)) as mock_open:
        with pytest.raises(PolygonRateLimitedError, match="rate limit"):
            client.fetch_daily_aggregates("SPY", "2024-01-01", "2024-01-31")
    assert mock_open.call_count == 3


def test_rest_client_transport_failure_fails_closed():
    """A URLError exhausts retries and surfaces as a connection error."""
    client = PolygonRestClient(PolygonConfig(api_key="test_key", pause=0.0, retries=2))
    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("dns failure")):
        with pytest.raises(PolygonConnectionError, match="transport failed"):
            client.fetch_daily_aggregates("SPY", "2024-01-01", "2024-01-31")


def test_rest_client_non_json_payload_fails_closed():
    """A non-JSON body is rejected rather than silently yielding zero bars."""
    client = PolygonRestClient(PolygonConfig(api_key="test_key", pause=0.0))
    with patch("urllib.request.urlopen", return_value=_FakeResponse(b"<html>gateway</html>")):
        with pytest.raises(PolygonBadResponseError, match="non-JSON payload"):
            client.fetch_daily_aggregates("SPY", "2024-01-01", "2024-01-31")


def test_rest_client_not_authorized_status_fails_closed():
    """A NOT_AUTHORIZED status body is an auth failure even on HTTP 200."""
    client = PolygonRestClient(PolygonConfig(api_key="test_key", pause=0.0))
    body = json.dumps({"status": "NOT_AUTHORIZED", "message": "plan does not include this"}).encode()
    with patch("urllib.request.urlopen", return_value=_FakeResponse(body)):
        with pytest.raises(PolygonAuthenticationError, match="denied access"):
            client.fetch_daily_aggregates("SPY", "2024-01-01", "2024-01-31")


def test_rest_client_unknown_status_fails_closed():
    """An unrecognised status is never treated as success."""
    client = PolygonRestClient(PolygonConfig(api_key="test_key", pause=0.0))
    body = json.dumps({"status": "SOMETHING_NEW", "results": []}).encode()
    with patch("urllib.request.urlopen", return_value=_FakeResponse(body)):
        with pytest.raises(PolygonUnknownStatusError, match="unrecognized status"):
            client.fetch_daily_aggregates("SPY", "2024-01-01", "2024-01-31")


def test_rest_client_malformed_row_fails_closed():
    """A result row missing required OHLC keys fails closed instead of being skipped."""
    client = PolygonRestClient(PolygonConfig(api_key="test_key", pause=0.0))
    body = ok_payload([{"t": BASE_MS, "o": 1.0}])
    with patch("urllib.request.urlopen", return_value=_FakeResponse(body)):
        with pytest.raises(PolygonBadResponseError, match="malformed aggregate row"):
            client.fetch_daily_aggregates("SPY", "2024-01-01", "2024-01-31")


def test_rest_client_delayed_status_is_accepted():
    """DELAYED is a valid Polygon success status for non-realtime plans."""
    client = PolygonRestClient(PolygonConfig(api_key="test_key", pause=0.0))
    body = json.dumps(
        {"status": "DELAYED", "results": [{"t": BASE_MS, "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0, "v": 1}]}
    ).encode()
    with patch("urllib.request.urlopen", return_value=_FakeResponse(body)):
        assert len(client.fetch_daily_aggregates("SPY", "2024-01-01", "2024-01-31")) == 1


# ---------------------------------------------------- 4. PolygonProvider fetch_ticker
def test_provider_fetch_ticker_returns_ohlcv(provider: PolygonProvider, mock_client: MockPolygonClient):
    """A healthy response maps to a validated OHLCV frame."""
    mock_client.set_bars("SPY", make_bars(30))
    df = provider.fetch_ticker("SPY")
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(df) == 30
    assert df.index.tz is None


def test_provider_fetch_ticker_no_bars_fails_closed(provider: PolygonProvider):
    """An empty result set is an ingestion failure, never an empty frame."""
    with pytest.raises(PolygonNoDataError, match="no aggregate bars"):
        provider.fetch_ticker("NOSUCHTICKER")


def test_provider_fetch_ticker_wraps_client_error(
    provider: PolygonProvider, mock_client: MockPolygonClient
):
    """A transport-level Polygon error surfaces as FailClosedDataError."""
    mock_client.set_error("SPY", PolygonRateLimitedError("429 exhausted"))
    with pytest.raises(FailClosedDataError, match="Polygon failed to fetch 'SPY'"):
        provider.fetch_ticker("SPY")


def test_provider_fetch_ticker_drops_vendor_artifacts(
    provider: PolygonProvider, mock_client: MockPolygonClient
):
    """Zero-volume flat bars are filtered by the shared DataValidationGate."""
    bars = make_bars(10)
    artifact = PolygonAggregateBar(
        timestamp_ms=BASE_MS + (20 * DAY_MS), open=5.0, high=5.0, low=5.0, close=5.0, volume=0.0
    )
    mock_client.set_bars("SPY", bars + [artifact])
    df = provider.fetch_ticker("SPY")
    assert len(df) == 10
    assert 5.0 not in df["Close"].values


def test_provider_fetch_ticker_all_artifacts_fails_closed(
    provider: PolygonProvider, mock_client: MockPolygonClient
):
    """If every bar is a vendor artifact the fetch fails rather than returning nothing."""
    artifacts = [
        PolygonAggregateBar(
            timestamp_ms=BASE_MS + (i * DAY_MS), open=5.0, high=5.0, low=5.0, close=5.0, volume=0.0
        )
        for i in range(5)
    ]
    mock_client.set_bars("SPY", artifacts)
    with pytest.raises(FailClosedDataError, match="was a vendor artifact"):
        provider.fetch_ticker("SPY")


# ---------------------------------------------------- 5. PolygonProvider fetch_daily_bars
def test_provider_fetch_daily_bars_aligns_universe(
    provider: PolygonProvider, mock_client: MockPolygonClient
):
    """Multiple tickers align into one Close matrix."""
    mock_client.set_bars("SPY", make_bars(30))
    mock_client.set_bars("TLT", make_bars(30, base_price=50.0))
    df = provider.fetch_daily_bars(["SPY", "TLT"], mode=ExecutionMode.RESEARCH)
    assert list(df.columns) == ["SPY", "TLT"]
    assert len(df) == 30


def test_provider_fetch_daily_bars_empty_universe_fails_closed(provider: PolygonProvider):
    """An empty universe is rejected up front."""
    with pytest.raises(FailClosedDataError, match="non-empty universe"):
        provider.fetch_daily_bars([])


def test_provider_fetch_daily_bars_missing_ticker_fails_closed(
    provider: PolygonProvider, mock_client: MockPolygonClient
):
    """A partially satisfied universe fails closed and names the missing tickers."""
    mock_client.set_bars("SPY", make_bars(30))
    with pytest.raises(FailClosedDataError, match=r"Polygon failed to fetch market data for \['TLT'\]"):
        provider.fetch_daily_bars(["SPY", "TLT"], mode=ExecutionMode.PAPER)


def test_provider_fetch_daily_bars_never_fabricates_on_total_failure(provider: PolygonProvider):
    """With no data at all the provider raises; it has no synthetic fallback in any mode."""
    for mode in (ExecutionMode.RESEARCH, ExecutionMode.PAPER, ExecutionMode.LIVE):
        with pytest.raises(FailClosedDataError):
            provider.fetch_daily_bars(["SPY"], mode=mode)


def test_provider_fetch_daily_bars_paper_mode_blocks_unhandled_gap(
    provider: PolygonProvider, mock_client: MockPolygonClient
):
    """An unadjusted corporate-action gap is blocked by the gate in PAPER mode."""
    bars = make_bars(20)
    gapped = list(bars)
    gapped[10] = PolygonAggregateBar(
        timestamp_ms=bars[10].timestamp_ms, open=50.0, high=50.0, low=50.0, close=50.0, volume=1_000_000.0
    )
    mock_client.set_bars("SPY", gapped)
    with pytest.raises(AnomalyGapError, match="Unhandled price anomaly gap"):
        provider.fetch_daily_bars(["SPY"], mode=ExecutionMode.PAPER)


def test_provider_fetch_daily_bars_requests_each_ticker_once(
    provider: PolygonProvider, mock_client: MockPolygonClient
):
    """One aggregates call is issued per ticker; Polygon has no multi-ticker aggregates endpoint."""
    mock_client.set_bars("SPY", make_bars(30))
    mock_client.set_bars("TLT", make_bars(30, base_price=50.0))
    provider.fetch_daily_bars(["SPY", "TLT"])
    assert [call[0] for call in mock_client.calls] == ["SPY", "TLT"]


# ---------------------------------------------------- 6. Health and registry wiring
def test_provider_health_unknown_before_first_fetch(provider: PolygonProvider):
    """No fetch yet is UNKNOWN, which the fail-closed gate never treats as safe."""
    assert provider.check_health().state.value == "UNKNOWN"


def test_provider_health_healthy_after_successful_fetch(
    provider: PolygonProvider, mock_client: MockPolygonClient
):
    """A successful fetch marks the data component healthy."""
    mock_client.set_bars("SPY", make_bars(30))
    provider.fetch_ticker("SPY")
    assert provider.check_health().state.value == "HEALTHY"


def test_provider_health_failed_after_ingestion_failure(provider: PolygonProvider):
    """A failed fetch marks the data component unavailable."""
    with pytest.raises(PolygonNoDataError):
        provider.fetch_ticker("SPY")
    assert provider.check_health().state.value == "FAILED"


def test_provider_name_is_stable(provider: PolygonProvider):
    """The provider reports a stable identity for logging and health details."""
    assert provider.provider_name == "PolygonProvider"


def test_polygon_provider_is_exported_from_data_package():
    """The provider is registered through the same path as the other providers."""
    from quant.data import PolygonProvider as ExportedProvider
    from quant.data.providers import PolygonProvider as ProvidersProvider

    assert ExportedProvider is PolygonProvider
    assert ProvidersProvider is PolygonProvider
