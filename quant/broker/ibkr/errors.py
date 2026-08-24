"""Normalized Interactive Brokers error hierarchy."""

from __future__ import annotations

from ...core.exceptions import BrokerError


class IBKRError(BrokerError):
    """Base class for all Interactive Brokers specific errors."""


class IBKRConnectionError(IBKRError):
    """Raised when communication with TWS/Gateway fails or connection drops."""


class IBKRAuthenticationError(IBKRError):
    """Raised when authentication or session validation with IBKR fails."""


class IBKROrderRejectedError(IBKRError):
    """Raised when IBKR rejects an order submission."""


class IBKRInvalidOrderError(IBKRError):
    """Raised when an order specification violates IBKR contract or tick rules."""


class IBKRInsufficientFundsError(IBKRError):
    """Raised when account equity or buying power is insufficient for order size."""


class IBKRShortUnavailableError(IBKRError):
    """Raised when a short locate fails or security is Hard-To-Borrow/Restricted."""


class IBKRMarketClosedError(IBKRError):
    """Raised when trading is attempted outside permitted exchange session hours."""


class IBKRRateLimitedError(IBKRError):
    """Raised when API pacing or message rate limits are exceeded."""


class IBKRUnknownBrokerError(IBKRError):
    """Raised when an unrecognized IBKR error code or state occurs."""


class IBKRLiveSafetyLockedError(IBKRError):
    """Raised when live execution is attempted without explicit multi-condition safety unlocking."""
