"""Configurable pre-trade portfolio risk limits and constraints."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskConfig:
    """Pre-trade risk limits and portfolio constraints (RESEARCH / PAPER DEFAULTS).
    
    All limits are configurable and represent baseline pre-trade risk controls.
    """
    max_gross_exposure: float = 1.0
    max_net_exposure: float = 0.5
    max_single_position_weight: float = 0.25
    max_long_exposure: float = 0.6
    max_short_exposure: float = 0.6
    min_cash_buffer_pct: float = 0.02
    max_leverage: float = 1.0
    max_drawdown_pct: float = 0.15
    max_volatility_annualized: float = 0.30
    vol_lookback_bars: int = 60
    min_vol_history_bars: int = 20
    scale_gross_leverage: bool = False
    allow_risk_reduction: bool = False

    def __post_init__(self) -> None:
        if self.max_gross_exposure <= 0:
            raise ValueError(f"max_gross_exposure must be positive, got {self.max_gross_exposure}")
        if self.max_single_position_weight <= 0:
            raise ValueError(f"max_single_position_weight must be positive, got {self.max_single_position_weight}")
        if self.min_cash_buffer_pct < 0:
            raise ValueError(f"min_cash_buffer_pct cannot be negative, got {self.min_cash_buffer_pct}")

    @classmethod
    def macro_mandate(cls) -> RiskConfig:
        """Returns risk configuration aligned with 200% gross dollar-neutral macro mandate."""
        return cls(
            max_gross_exposure=2.0,
            max_net_exposure=0.5,
            max_single_position_weight=0.60,
            max_long_exposure=1.0,
            max_short_exposure=1.0,
            max_leverage=2.0,
            max_drawdown_pct=0.35,
            max_volatility_annualized=0.35,
            scale_gross_leverage=False,
        )
