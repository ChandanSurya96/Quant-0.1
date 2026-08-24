"""Interactive Brokers adapter package."""

from .adapter import IBKRBrokerAdapter
from .client import IBKRClientProtocol, MockIBKRClient
from .errors import (
    IBKRAuthenticationError,
    IBKRConnectionError,
    IBKRError,
    IBKRInsufficientFundsError,
    IBKRInvalidOrderError,
    IBKRLiveSafetyLockedError,
    IBKRMarketClosedError,
    IBKROrderRejectedError,
    IBKRRateLimitedError,
    IBKRShortUnavailableError,
    IBKRUnknownBrokerError,
)
from .health import IBKRHealthTracker
from .mapper import IBKRMapper
from .models import BuyingPowerInfo, IBKRConfig, IBKRExecutionRecord, IBKROrderRecord, ShortAvailability

__all__ = [
    "IBKRBrokerAdapter",
    "IBKRClientProtocol",
    "MockIBKRClient",
    "IBKRError",
    "IBKRConnectionError",
    "IBKRAuthenticationError",
    "IBKROrderRejectedError",
    "IBKRInvalidOrderError",
    "IBKRInsufficientFundsError",
    "IBKRShortUnavailableError",
    "IBKRMarketClosedError",
    "IBKRRateLimitedError",
    "IBKRUnknownBrokerError",
    "IBKRLiveSafetyLockedError",
    "IBKRHealthTracker",
    "IBKRMapper",
    "IBKRConfig",
    "BuyingPowerInfo",
    "IBKROrderRecord",
    "IBKRExecutionRecord",
    "ShortAvailability",
]
