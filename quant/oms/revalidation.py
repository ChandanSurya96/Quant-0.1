"""Pre-submission revalidation engine for final pre-broker safety checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..broker.base import BrokerAdapter
from ..core.enums import ExecutionMode, OrderSide, OrderType
from ..core.interfaces import OrderBatch, TargetPortfolio
from ..persistence.database import DatabaseManager
from ..reconciliation.engine import ReconciliationEngine
from ..risk.engine import RiskEngine
from .approval import ApprovalToken


@dataclass
class PreSubmissionValidationResult:
    """Outcome of the pre-submission revalidation gate."""
    passed: bool
    errors: list[str] = field(default_factory=list)
    revalidated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PreSubmissionValidator:
    """Enforces final multi-gate revalidation immediately before broker order submission."""

    @classmethod
    def validate(
        cls,
        order_batch: OrderBatch,
        target_portfolio: TargetPortfolio,
        broker: BrokerAdapter,
        db_manager: DatabaseManager,
        approval_token: ApprovalToken | None,
        risk_engine: RiskEngine,
        current_prices: dict[str, float],
        instrument_whitelist: list[str] | None = None,
        allowed_order_types: list[OrderType] | None = None,
        live_capital_limit: float | None = None,
        emergency_stop_active: bool = False,
        execution_mode: ExecutionMode = ExecutionMode.PAPER,
    ) -> PreSubmissionValidationResult:
        errors: list[str] = []

        # 1. Emergency Stop / Kill Switch
        if emergency_stop_active:
            errors.append("EMERGENCY STOP (KILL SWITCH) IS ACTIVE. Order submission blocked.")

        # 2. Broker Connection Health
        broker_health = broker.health_check()
        if broker_health != "CONNECTED":
            errors.append(f"Broker connection is not healthy (status={broker_health!r}).")

        # 3. Approval Token Validation
        if execution_mode == ExecutionMode.LIVE or approval_token is not None:
            if approval_token is None:
                errors.append("Mandatory approval token is missing.")
            elif not approval_token.is_valid():
                errors.append(
                    f"Approval token {approval_token.token_id} is invalid or expired ({approval_token.status.value})."
                )
            elif approval_token.order_batch_id != order_batch.batch_id:
                errors.append(
                    f"Approval token order_batch_id ({approval_token.order_batch_id}) "
                    f"does not match submitted batch ID ({order_batch.batch_id})."
                )

        # 4. Instrument Whitelist Verification
        if instrument_whitelist is not None:
            whitelist_set = set(instrument_whitelist)
            for o in order_batch.orders:
                if o.symbol not in whitelist_set:
                    errors.append(f"Instrument {o.symbol!r} is outside the approved whitelist: {instrument_whitelist}.")

        # 5. Order Type Verification
        if allowed_order_types is not None:
            allowed_types_set = set(allowed_order_types)
            for o in order_batch.orders:
                if o.order_type not in allowed_types_set:
                    errors.append(f"Order type {o.order_type.value!r} for {o.symbol} is not permitted.")

        # 6. Live Capital Limit Check
        total_trade_notional = sum(o.quantity * current_prices.get(o.symbol, 0.0) for o in order_batch.orders)
        if live_capital_limit is not None and execution_mode == ExecutionMode.LIVE:
            if total_trade_notional > live_capital_limit:
                errors.append(
                    f"Total order batch notional (${total_trade_notional:,.2f}) "
                    f"exceeds live capital limit (${live_capital_limit:,.2f})."
                )

        # 7. Short Locate Availability & Buying Power
        buying_power = broker.get_buying_power()
        if execution_mode == ExecutionMode.LIVE:
            if buying_power is None:
                errors.append("Broker buying power is UNKNOWN. Failing closed in LIVE mode.")
            elif total_trade_notional > buying_power:
                errors.append(
                    f"Insufficient buying power: required=${total_trade_notional:,.2f}, available=${buying_power:,.2f}."
                )

        # Check short availability for all sell orders
        curr_positions = broker.get_positions()
        for o in order_batch.orders:
            if o.side == OrderSide.SELL:
                h = curr_positions.get(o.symbol)
                curr_shs = h.shares if h is not None else 0.0
                if curr_shs <= 0 or (curr_shs - o.quantity) < 0:
                    avail = broker.get_short_availability(o.symbol)
                    if avail != "AVAILABLE":
                        errors.append(f"Short borrow unavailable or unknown for {o.symbol!r} (status={avail!r}).")

        # 8. Pre-Execution State Reconciliation
        run_id = order_batch.metadata.get("run_id", "run_reval")
        try:
            rec_result = ReconciliationEngine.reconcile(run_id, execution_mode, db_manager, broker)
            if not rec_result.passed:
                errors.append(
                    f"Pre-submission reconciliation failed with {len(rec_result.issues)} issues: "
                    f"{[i.message for i in rec_result.issues]}"
                )
        except Exception as e:
            errors.append(f"Reconciliation error during pre-submission check: {e}")

        # 9. Risk Engine Re-Evaluation
        try:
            account_state = broker.get_account_state(current_prices=current_prices)
            risk_dec = risk_engine.evaluate(
                target_portfolio=target_portfolio,
                portfolio_state=account_state,
                current_prices=current_prices,
                portfolio_id=target_portfolio.metadata.get("target_portfolio_id", "tp_reval"),
            )
            if not risk_dec.approved:
                errors.append(f"RiskEngine rejected TargetPortfolio on revalidation: {risk_dec.violations}")
        except Exception as e:
            errors.append(f"RiskEngine revalidation error: {e}")

        return PreSubmissionValidationResult(
            passed=len(errors) == 0,
            errors=errors,
        )
