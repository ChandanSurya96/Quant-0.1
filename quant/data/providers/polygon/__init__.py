"""Polygon.io market data provider package."""

from .client import MockPolygonClient, PolygonClientProtocol, PolygonRestClient
from .errors import (
    PolygonAuthenticationError,
    PolygonBadResponseError,
    PolygonConnectionError,
    PolygonError,
    PolygonNoDataError,
    PolygonRateLimitedError,
    PolygonUnknownStatusError,
)
from .mapper import PolygonMapper
from .models import PolygonAggregateBar, PolygonConfig
from .provider import PolygonProvider

__all__ = [
    "PolygonProvider",
    "PolygonClientProtocol",
    "PolygonRestClient",
    "MockPolygonClient",
    "PolygonError",
    "PolygonConnectionError",
    "PolygonAuthenticationError",
    "PolygonRateLimitedError",
    "PolygonBadResponseError",
    "PolygonNoDataError",
    "PolygonUnknownStatusError",
    "PolygonMapper",
    "PolygonConfig",
    "PolygonAggregateBar",
]
