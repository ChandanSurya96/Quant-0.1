"""Domain and operational exceptions for Quant engine."""


class QuantError(Exception):
    """Base exception for all Quant framework errors."""
    pass


class DataError(QuantError):
    """Base exception for data layer errors."""
    pass


class FailClosedDataError(DataError):
    """Raised when market data ingestion fails or is invalid in a fail-closed environment."""
    pass


class AnomalyGapError(DataError):
    """Raised when an unhandled single-bar price anomaly exceeds the data gate threshold."""
    pass


class StaleDataError(DataError):
    """Raised when market data timestamps are older than expected execution window."""
    pass


class ModeViolationError(QuantError):
    """Raised when an operation violates the active ExecutionMode constraints."""
    pass


class RiskViolationError(QuantError):
    """Raised when a target portfolio violates pre-trade risk engine rules."""
    pass


class ReconciliationError(QuantError):
    """Raised when internal holdings do not match broker reported positions."""
    pass


class OMSError(QuantError):
    """Base exception for order management system errors."""
    pass


class InvalidStateTransitionError(OMSError):
    """Raised when an order attempts an illegal status transition."""
    pass


class BrokerError(QuantError):
    """Base exception for physical and simulated broker execution errors."""
    pass
