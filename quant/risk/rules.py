"""Concrete risk limit rules for pre-trade portfolio controls."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable
import numpy as np

from ..core.interfaces import PortfolioState, TargetPortfolio
from .config import RiskConfig


@runtime_checkable
class BorrowAvailabilityChecker(Protocol):
    """Protocol for checking short borrow / locate availability."""

    def is_borrow_available(self, symbol: str) -> bool:
        """Returns True if the security can be borrowed for short selling."""
        ...


class AbstractRiskRule(ABC):
    """Base class for modular pre-trade risk evaluation rules."""

    @abstractmethod
    def evaluate(
        self,
        target_portfolio: TargetPortfolio,
        portfolio_state: PortfolioState,
        config: RiskConfig,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str], dict[str, float], dict[str, float] | None]:
        """Evaluates rule constraints.

        Returns:
            passed (bool): True if rule passed or was successfully scaled.
            violations (list[str]): List of violation descriptions.
            metrics (dict[str, float]): Computed numerical metrics.
            adjusted_weights (dict[str, float] | None): Adjusted weights if scaling occurred, else None.
        """
        raise NotImplementedError


class GrossLeverageRule(AbstractRiskRule):
    """Enforces gross leverage cap: sum(|w_i|) <= max_gross_exposure (default 1.0).

    Supports deterministic proportional scaling if configured.
    """

    def evaluate(
        self,
        target_portfolio: TargetPortfolio,
        portfolio_state: PortfolioState,
        config: RiskConfig,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str], dict[str, float], dict[str, float] | None]:
        weights = target_portfolio.target_weights
        gross = float(sum(abs(w) for w in weights.values()))
        metrics = {"gross_exposure": gross, "leverage": gross}
        violations: list[str] = []
        adjusted: dict[str, float] | None = None

        if gross > config.max_gross_exposure + 1e-6:
            if getattr(config, "scale_gross_leverage", False):
                scale = config.max_gross_exposure / gross
                adjusted = {sym: float(w * scale) for sym, w in weights.items()}
                violations.append(
                    f"Gross leverage {gross:.4f} exceeded limit {config.max_gross_exposure:.4f}; "
                    f"deterministically scaled by factor {scale:.4f}."
                )
                metrics["gross_exposure_scaled"] = float(sum(abs(w) for w in adjusted.values()))
                return True, violations, metrics, adjusted
            else:
                violations.append(f"Gross exposure {gross:.4f} exceeds limit {config.max_gross_exposure:.4f}")
                return False, violations, metrics, None

        return True, violations, metrics, None


class ConcentrationRule(AbstractRiskRule):
    """Enforces single-position absolute concentration: |w_i| <= max_single_position_weight (default 0.25)."""

    def evaluate(
        self,
        target_portfolio: TargetPortfolio,
        portfolio_state: PortfolioState,
        config: RiskConfig,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str], dict[str, float], dict[str, float] | None]:
        weights = target_portfolio.target_weights
        max_pos = float(max((abs(w) for w in weights.values()), default=0.0))
        metrics = {"max_position_weight": max_pos}
        violations: list[str] = []

        for sym, w in weights.items():
            if abs(w) > config.max_single_position_weight + 1e-6:
                violations.append(
                    f"Single position concentration {abs(w):.4f} exceeds limit {config.max_single_position_weight:.4f}"
                )

        return (len(violations) == 0), violations, metrics, None


class CashBufferRule(AbstractRiskRule):
    """Enforces minimum cash buffer: Cash >= min_cash_buffer_pct * NAV (default 2%)."""

    def evaluate(
        self,
        target_portfolio: TargetPortfolio,
        portfolio_state: PortfolioState,
        config: RiskConfig,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str], dict[str, float], dict[str, float] | None]:
        nav = portfolio_state.nav if portfolio_state.nav > 0 else 1.0
        current_cash = portfolio_state.cash
        current_holdings = portfolio_state.holdings
        prices = (context or {}).get("current_prices", {})

        current_cash_pct = current_cash / nav
        metrics = {
            "cash_buffer_pct": float(current_cash_pct),
        }
        violations: list[str] = []

        # Current cash check
        if current_cash_pct < config.min_cash_buffer_pct - 1e-6:
            violations.append(
                f"Cash buffer {current_cash_pct*100:.2f}% below minimum required {config.min_cash_buffer_pct*100:.2f}%"
            )
            return False, violations, metrics, None

        # Projected cash check if prices available
        target_weights = target_portfolio.target_weights
        if prices:
            net_cash_flow = 0.0
            turnover_notional = 0.0
            for sym in set(target_weights.keys()) | set(current_holdings.keys()):
                px = prices.get(sym, 1.0)
                target_w = target_weights.get(sym, 0.0)
                target_shares = (target_w * nav) / px
                current_shares = current_holdings.get(sym).shares if sym in current_holdings else 0.0
                delta_shares = target_shares - current_shares
                trade_notional = abs(delta_shares) * px
                turnover_notional += trade_notional
                net_cash_flow -= (delta_shares * px)

            est_commission = turnover_notional * 0.0010  # 10 bps estimated cost
            projected_cash = current_cash + net_cash_flow - est_commission
            projected_cash_pct = projected_cash / nav
            metrics["projected_cash"] = float(projected_cash)
            metrics["projected_cash_pct"] = float(projected_cash_pct)

            if projected_cash_pct < config.min_cash_buffer_pct - 1e-6:
                violations.append(
                    f"Projected cash buffer {projected_cash_pct*100:.2f}% below minimum required {config.min_cash_buffer_pct*100:.2f}%"
                )
                return False, violations, metrics, None

        return True, violations, metrics, None


class ShortBorrowRule(AbstractRiskRule):
    """Enforces borrow availability validation for all negative/short target positions."""

    def evaluate(
        self,
        target_portfolio: TargetPortfolio,
        portfolio_state: PortfolioState,
        config: RiskConfig,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str], dict[str, float], dict[str, float] | None]:
        weights = target_portfolio.target_weights
        short_weights = {sym: w for sym, w in weights.items() if w < -1e-6}
        short_exp = float(sum(abs(w) for w in short_weights.values()))
        metrics = {"short_exposure": short_exp}
        violations: list[str] = []

        # Check borrow availability provider/set if passed in context
        ctx = context or {}
        borrow_checker = ctx.get("borrow_checker")
        available_borrows = ctx.get("available_borrows")  # set or dict

        for sym, w in short_weights.items():
            is_avail = True
            if borrow_checker is not None:
                is_avail = borrow_checker.is_borrow_available(sym)
            elif available_borrows is not None:
                if isinstance(available_borrows, dict):
                    is_avail = bool(available_borrows.get(sym, False))
                elif isinstance(available_borrows, set):
                    is_avail = sym in available_borrows

            if not is_avail:
                violations.append(f"Short position in {sym} ({w:.4f}) rejected: borrow unavailable.")

        if short_exp > config.max_short_exposure + 1e-6:
            violations.append(f"Short exposure {short_exp:.4f} exceeds limit {config.max_short_exposure:.4f}")

        return (len(violations) == 0), violations, metrics, None


class DrawdownCircuitBreakerRule(AbstractRiskRule):
    """Enforces -15.0% drawdown circuit breaker with support for risk reduction/position closure."""

    def evaluate(
        self,
        target_portfolio: TargetPortfolio,
        portfolio_state: PortfolioState,
        config: RiskConfig,
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str], dict[str, float], dict[str, float] | None]:
        nav = portfolio_state.nav if portfolio_state.nav > 0 else 1.0
        peak_nav = (context or {}).get("peak_nav", nav)
        drawdown = (nav - peak_nav) / peak_nav if peak_nav > 0 else 0.0
        metrics = {"drawdown": float(drawdown)}
        violations: list[str] = []

        if drawdown < -config.max_drawdown_pct - 1e-6:
            allow_reduction = getattr(config, "allow_risk_reduction", False) or (context or {}).get("allow_risk_reduction", False)
            if allow_reduction:
                current_holdings = portfolio_state.holdings
                current_gross = sum(abs(h.market_value) for h in current_holdings.values()) / nav
                target_gross = sum(abs(w) for w in target_portfolio.target_weights.values())
                is_risk_reduction = (target_gross <= current_gross + 1e-6)
                if not is_risk_reduction:
                    violations.append(
                        f"Portfolio drawdown {drawdown*100:.2f}% breached circuit breaker (-{config.max_drawdown_pct*100:.2f}%). "
                        f"New risk expansion frozen (target gross {target_gross:.4f} > current gross {current_gross:.4f})."
                    )
                    return False, violations, metrics, None
            else:
                violations.append(
                    f"Portfolio drawdown {drawdown*100:.2f}% breached kill-switch threshold -{config.max_drawdown_pct*100:.2f}%"
                )
                return False, violations, metrics, None

        return True, violations, metrics, None
