"""Pre-trade Risk Engine evaluating portfolio-level constraints."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
from typing import Any
import uuid
import numpy as np
import pandas as pd

from ..core.interfaces import PortfolioState, RiskDecision, TargetPortfolio
from ..observability.logging import StructuredLogger
from .config import RiskConfig
from .rules import (
    BorrowAvailabilityChecker,
    CashBufferRule,
    ConcentrationRule,
    DrawdownCircuitBreakerRule,
    GrossLeverageRule,
    ShortBorrowRule,
)


class RiskEngine:
    """Pre-trade risk engine enforcing mandatory portfolio risk controls."""

    def __init__(self, config: RiskConfig | None = None, logger: StructuredLogger | None = None) -> None:
        self.config = config or RiskConfig()
        self.logger = logger or StructuredLogger("RiskEngine")
        self._leverage_rule = GrossLeverageRule()
        self._concentration_rule = ConcentrationRule()
        self._cash_rule = CashBufferRule()
        self._borrow_rule = ShortBorrowRule()
        self._drawdown_rule = DrawdownCircuitBreakerRule()

    def evaluate(
        self,
        target_portfolio: TargetPortfolio,
        portfolio_state: PortfolioState,
        historical_returns: pd.Series | np.ndarray | None = None,
        peak_nav: float | None = None,
        borrow_checker: BorrowAvailabilityChecker | None = None,
        available_borrows: set[str] | dict[str, bool] | None = None,
        current_prices: dict[str, float] | None = None,
        config_override: RiskConfig | None = None,
        decision_id: str | None = None,
        portfolio_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> RiskDecision:
        """Evaluates all configured pre-trade risk rules against the target portfolio.

        Returns a frozen RiskDecision with structured violation reporting.
        """
        cfg = config_override or self.config
        now = datetime.now(timezone.utc)
        d_id = decision_id or f"risk_{uuid.uuid4().hex[:12]}"
        p_id = portfolio_id or f"tp_{uuid.uuid4().hex[:12]}"
        violations: list[str] = []
        rule_metrics: dict[str, float] = {}

        # 1. Input Integrity / Fail-Closed Checks
        if portfolio_state is None or portfolio_state.nav <= 0:
            violations.append(f"Invalid portfolio state: NAV must be positive (got {getattr(portfolio_state, 'nav', None)})")

        weights = target_portfolio.target_weights
        if not weights:
            # Empty portfolio is a valid flat allocation
            weights = {}

        for sym, w in weights.items():
            if not isinstance(w, (int, float)) or math.isnan(w) or math.isinf(w):
                violations.append(f"Invalid non-finite weight for {sym}: {w}")

        nav = portfolio_state.nav if portfolio_state and portfolio_state.nav > 0 else 1.0
        cash = portfolio_state.cash if portfolio_state else 0.0
        p_nav = peak_nav if peak_nav is not None and peak_nav > 0 else nav

        eval_context = dict(context or {})
        eval_context.setdefault("peak_nav", p_nav)
        eval_context.setdefault("current_prices", current_prices or {})
        if borrow_checker is not None:
            eval_context["borrow_checker"] = borrow_checker
        if available_borrows is not None:
            eval_context["available_borrows"] = available_borrows

        # 2. Rule Evaluations
        working_weights = dict(weights)
        was_scaled = False
        scale_factor = 1.0

        # Leverage & Scaling
        lev_pass, lev_viols, lev_mets, scaled_w = self._leverage_rule.evaluate(
            target_portfolio, portfolio_state, cfg, eval_context
        )
        rule_metrics.update(lev_mets)
        if not lev_pass:
            violations.extend(lev_viols)
        elif scaled_w is not None:
            was_scaled = True
            raw_gross = sum(abs(w) for w in weights.values())
            scaled_gross = sum(abs(w) for w in scaled_w.values())
            scale_factor = scaled_gross / max(1e-8, raw_gross)
            rule_metrics["gross_scale_factor"] = scale_factor

            self.logger.warning(
                "LOUD_LEVERAGE_SCALING_APPLIED",
                extra={
                    "decision_id": d_id,
                    "strategy_id": target_portfolio.strategy_id,
                    "raw_gross_exposure": raw_gross,
                    "scaled_gross_exposure": scaled_gross,
                    "scale_factor": scale_factor,
                    "max_gross_exposure_limit": cfg.max_gross_exposure,
                },
            )

            working_weights = scaled_w
            # Reconstruct target portfolio for downstream rule checks if scaled
            target_portfolio = TargetPortfolio(
                timestamp=target_portfolio.timestamp,
                strategy_id=target_portfolio.strategy_id,
                target_weights=working_weights,
                rebalance_horizon=target_portfolio.rebalance_horizon,
                metadata=target_portfolio.metadata,
            )

        # Concentration
        conc_pass, conc_viols, conc_mets, _ = self._concentration_rule.evaluate(
            target_portfolio, portfolio_state, cfg, eval_context
        )
        rule_metrics.update(conc_mets)
        if not conc_pass:
            violations.extend(conc_viols)

        # Cash Buffer
        cash_pass, cash_viols, cash_mets, _ = self._cash_rule.evaluate(
            target_portfolio, portfolio_state, cfg, eval_context
        )
        rule_metrics.update(cash_mets)
        if not cash_pass:
            violations.extend(cash_viols)

        # Short Borrow / Margin
        borrow_pass, borrow_viols, borrow_mets, _ = self._borrow_rule.evaluate(
            target_portfolio, portfolio_state, cfg, eval_context
        )
        rule_metrics.update(borrow_mets)
        if not borrow_pass:
            violations.extend(borrow_viols)

        # Drawdown Circuit Breaker
        dd_pass, dd_viols, dd_mets, _ = self._drawdown_rule.evaluate(
            target_portfolio, portfolio_state, cfg, eval_context
        )
        rule_metrics.update(dd_mets)
        if not dd_pass:
            violations.extend(dd_viols)

        # 3. Aggregated Exposure & Metric Verification
        gross_exp = float(sum(abs(w) for w in working_weights.values()))
        net_exp = float(sum(working_weights.values()))
        long_exp = float(sum(w for w in working_weights.values() if w > 0))
        short_exp = float(sum(abs(w) for w in working_weights.values() if w < 0))
        max_pos_w = float(max((abs(w) for w in working_weights.values()), default=0.0))
        cash_buffer_pct = cash / nav if nav > 0 else 0.0
        drawdown = (nav - p_nav) / p_nav if p_nav > 0 else 0.0

        rule_metrics.setdefault("gross_exposure", gross_exp)
        rule_metrics.setdefault("net_exposure", net_exp)
        rule_metrics.setdefault("leverage", gross_exp)
        rule_metrics.setdefault("long_exposure", long_exp)
        rule_metrics.setdefault("short_exposure", short_exp)
        rule_metrics.setdefault("max_position_weight", max_pos_w)
        rule_metrics.setdefault("cash_buffer_pct", cash_buffer_pct)
        rule_metrics.setdefault("drawdown", drawdown)

        # Exposure caps
        if abs(net_exp) > cfg.max_net_exposure + 1e-6:
            violations.append(f"Net exposure {net_exp:.4f} exceeds limit {cfg.max_net_exposure:.4f}")
        if long_exp > cfg.max_long_exposure + 1e-6:
            violations.append(f"Long exposure {long_exp:.4f} exceeds limit {cfg.max_long_exposure:.4f}")

        # Volatility Evaluation
        if historical_returns is not None:
            r_arr = np.asarray(historical_returns)
            if len(r_arr) < cfg.min_vol_history_bars:
                violations.append(
                    f"Insufficient volatility history: {len(r_arr)} bars (minimum {cfg.min_vol_history_bars} required). Ingestion failed closed."
                )
            else:
                window_rets = r_arr[-cfg.vol_lookback_bars:]
                sd = float(np.std(window_rets, ddof=1))
                ann_vol = float(sd * np.sqrt(252.0))
                rule_metrics["estimated_volatility"] = ann_vol

                if ann_vol > cfg.max_volatility_annualized + 1e-6:
                    violations.append(
                        f"Estimated annualized volatility {ann_vol*100:.2f}% exceeds limit {cfg.max_volatility_annualized*100:.2f}%"
                    )

        approved = (len(violations) == 0)
        adj_weights = dict(working_weights) if approved else {}

        decision_status = "approved" if approved and not was_scaled else ("approved_scaled" if approved else "rejected")

        return RiskDecision(
            decision_id=d_id,
            portfolio_id=p_id,
            strategy_id=target_portfolio.strategy_id,
            timestamp=now,
            approved=approved,
            violations=violations,
            adjusted_weights=adj_weights,
            metrics=rule_metrics,
            metadata={
                "evaluated_by": "RiskEngine_v1",
                "decision_status": decision_status,
                "was_scaled": was_scaled,
                "scale_factor": scale_factor,
            },
        )
