"""Order Management System (OMS) engine."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from ..core.enums import ExecutionMode, OrderSide, OrderStatus, OrderType
from ..core.exceptions import OMSError, RiskViolationError
from ..core.interfaces import Holding, Order, OrderBatch, RiskDecision, TargetPortfolio
from ..portfolio.sizer import target_weights_to_shares


class OrderManagementSystem:
    """Transforms approved target portfolios and current holdings into executable OrderBatches."""

    @staticmethod
    def generate_order_batch(
        current_holdings: dict[str, Holding],
        target_portfolio: TargetPortfolio,
        current_prices: dict[str, float],
        nav: float,
        run_id: str,
        execution_mode: ExecutionMode = ExecutionMode.PAPER,
        batch_id: str | None = None,
        target_portfolio_id: str | None = None,
        risk_decision: RiskDecision | None = None,
        require_risk_approval: bool = False,
    ) -> OrderBatch:
        """Generates an OrderBatch from current holdings and target weights.

        delta_shares = target_shares - current_shares
        delta > 0 -> BUY
        delta < 0 -> SELL
        delta == 0 -> No order
        """
        if nav <= 0:
            raise OMSError(f"NAV must be positive to size orders, got {nav}")
        if not current_prices:
            raise OMSError("current_prices cannot be empty")

        b_id = batch_id or f"batch_{uuid.uuid4().hex[:12]}"
        tp_id = target_portfolio_id or (risk_decision.portfolio_id if risk_decision and risk_decision.portfolio_id else f"tp_{uuid.uuid4().hex[:12]}")

        # Pre-Trade Risk Authority Validation
        if require_risk_approval and risk_decision is None:
            raise RiskViolationError("Pre-trade risk decision missing. OMS cannot generate orders without an approved RiskDecision.")

        if risk_decision is not None:
            if not risk_decision.approved:
                raise RiskViolationError(f"TargetPortfolio was rejected by RiskEngine: {risk_decision.violations}")
            if risk_decision.portfolio_id and tp_id and risk_decision.portfolio_id != tp_id:
                raise RiskViolationError(
                    f"RiskDecision portfolio_id mismatch: decision for {risk_decision.portfolio_id!r}, "
                    f"target portfolio is {tp_id!r}."
                )
            if risk_decision.strategy_id and risk_decision.strategy_id != target_portfolio.strategy_id:
                raise RiskViolationError(
                    f"RiskDecision strategy_id mismatch: decision for {risk_decision.strategy_id!r}, "
                    f"target portfolio is {target_portfolio.strategy_id!r}."
                )

        active_weights = (
            risk_decision.adjusted_weights
            if (risk_decision and risk_decision.adjusted_weights)
            else target_portfolio.target_weights
        )

        # Convert target weights to shares
        target_shares = target_weights_to_shares(
            active_weights,
            nav=nav,
            prices=current_prices,
        )

        all_symbols = sorted(set(active_weights.keys()) | set(current_holdings.keys()))
        orders: list[Order] = []

        for sym in all_symbols:
            px = current_prices.get(sym)
            if px is None or px <= 0:
                continue

            target_q = target_shares.get(sym, 0.0)
            holding = current_holdings.get(sym)
            current_q = holding.shares if holding is not None else 0.0
            delta_q = target_q - current_q

            # Filter tiny floating point residual noise (< 1e-6)
            if abs(delta_q) < 1e-6:
                continue

            side = OrderSide.BUY if delta_q > 0 else OrderSide.SELL
            qty = abs(delta_q)
            client_oid = f"{b_id}_{sym}_{side.value}"
            oid = f"ord_{uuid.uuid4().hex[:12]}"

            orders.append(
                Order(
                    order_id=oid,
                    run_id=run_id,
                    strategy_id=target_portfolio.strategy_id,
                    symbol=sym,
                    side=side,
                    order_type=OrderType.MARKET,
                    quantity=qty,
                    client_order_id=client_oid,
                    execution_mode=execution_mode,
                    created_at=datetime.now(timezone.utc),
                    status=OrderStatus.CREATED,
                )
            )

        return OrderBatch(
            batch_id=b_id,
            target_portfolio_id=tp_id,
            strategy_id=target_portfolio.strategy_id,
            orders=orders,
            execution_mode=execution_mode,
            generated_at=datetime.now(timezone.utc),
            metadata={
                "risk_decision_id": risk_decision.decision_id if risk_decision else None,
                "run_id": run_id,
            },
        )
