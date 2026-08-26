"""Normalized Polygon.io error hierarchy."""

from __future__ import annotations

from ....core.exceptions import DataError


class PolygonError(DataError):
    """Base class for all Polygon.io specific errors."""


class PolygonConnectionError(PolygonError):
    """Raised when the HTTP transport to Polygon fails or times out."""


class PolygonAuthenticationError(PolygonError):
    """Raised when the API key is missing, malformed, or rejected by Polygon."""


class PolygonRateLimitedError(PolygonError):
    """Raised when Polygon returns HTTP 429 and the retry budget is exhausted."""


class PolygonBadResponseError(PolygonError):
    """Raised when Polygon returns a payload that is not valid JSON or lacks a status field."""


class PolygonNoDataError(PolygonError):
    """Raised when Polygon responds successfully but returns zero aggregate bars."""


class PolygonUnknownStatusError(PolygonError):
    """Raised when Polygon reports an unrecognized response status."""
