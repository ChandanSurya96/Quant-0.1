"""Order preview generation and formatting for human execution approval."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..core.enums import OrderSide, OrderType
from ..core.interfaces import Holding, OrderBatch, RiskDecision, TargetPortfolio


@dataclass(frozen=True)
class OrderPreviewItem:
    """Detailed financial and execution projection for a single trade."""
    symbol: str
    side: OrderSide
    quantity: float
    order_type: OrderType
    limit_price: float | None
    current_price: float
    current_shares: float
    target_shares: float
    estimated_notional: float
    estimated_commission: float = 0.0
    estimated_borrow_cost: float = 0.0


@dataclass
class OrderPreview:
    """Immutable pre-trade audit and risk projection presented to human approver."""
    run_id: str
    strategy_id: str
    target_portfolio_id: str
    risk_decision_id: str
    order_batch_id: str
    created_at: datetime
    items: list[OrderPreviewItem]
    gross_exposure: float
    net_exposure: float
    current_cash: float
    resulting_cash: float
    risk_approved: bool
    risk_violations: list[str] = field(default_factory=list)
    broker_constraints: dict[str, Any] = field(default_factory=dict)

    def to_text_preview(self) -> str:
        """Renders human-readable order preview block."""
        dt_str = self.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        total_notional = sum(item.estimated_notional for item in self.items)
        total_comm = sum(item.estimated_commission for item in self.items)

        lines = [
            "=" * 64,
            f"ORDER BATCH PREVIEW FOR HUMAN APPROVAL — {dt_str}",
            "=" * 64,
            f"Run ID:              {self.run_id}",
            f"Strategy ID:         {self.strategy_id}",
            f"Target Portfolio ID: {self.target_portfolio_id}",
            f"Risk Decision ID:    {self.risk_decision_id} (Approved={self.risk_approved})",
            f"Order Batch ID:      {self.order_batch_id}",
            f"Projected Gross Exp: {self.gross_exposure * 100:.2f}%",
            f"Projected Net Exp:   {self.net_exposure * 100:.2f}%",
            f"Current Cash:        ${self.current_cash:,.2f}",
            f"Resulting Cash:      ${self.resulting_cash:,.2f}",
            f"Total Trade Notional:${total_notional:,.2f}",
            f"Est. Total Friction: ${total_comm:,.2f}",
            "-" * 64,
            f"{'SYM':<6} {'SIDE':<5} {'QTY':>6} {'PX':>8} {'NOTIONAL':>11} {'CURR_SHS':>9} {'TGT_SHS':>9}",
            "-" * 64,
        ]
        for it in self.items:
            lines.append(
                f"{it.symbol:<6} {it.side.value:<5} {it.quantity:>6.0f} ${it.current_price:>7.2f} "
                f"${it.estimated_notional:>10.2f} {it.current_shares:>9.0f} {it.target_shares:>9.0f}"
            )
        lines.append("=" * 64)
        if self.risk_violations:
            lines.append("WARNING - RISK VIOLATIONS DETECTED:")
            for v in self.risk_violations:
                lines.append(f"  * {v}")
            lines.append("=" * 64)
        return "\n".join(lines)


class OrderPreviewBuilder:
    """Builds an OrderPreview from domain objects."""

    @classmethod
    def build(
        cls,
        order_batch: OrderBatch,
        target_portfolio: TargetPortfolio,
        risk_decision: RiskDecision,
        current_holdings: dict[str, Holding],
        current_prices: dict[str, float],
        cash: float,
        commission_rate: float = 0.0010,
        broker_constraints: dict[str, Any] | None = None,
    ) -> OrderPreview:
        now = datetime.now(timezone.utc)
        items: list[OrderPreviewItem] = []
        projected_cash = cash

        for o in order_batch.orders:
            px = current_prices.get(o.symbol, 0.0)
            holding = current_holdings.get(o.symbol)
            curr_shs = holding.shares if holding is not None else 0.0
            mult = 1.0 if o.side == OrderSide.BUY else -1.0
            tgt_shs = curr_shs + (o.quantity * mult)
            notional = o.quantity * px
            comm = notional * commission_rate

            if o.side == OrderSide.BUY:
                projected_cash -= (notional + comm)
            else:
                projected_cash += (notional - comm)

            items.append(
                OrderPreviewItem(
                    symbol=o.symbol,
                    side=o.side,
                    quantity=o.quantity,
                    order_type=o.order_type,
                    limit_price=o.limit_price,
                    current_price=px,
                    current_shares=curr_shs,
                    target_shares=tgt_shs,
                    estimated_notional=notional,
                    estimated_commission=comm,
                )
            )

        active_weights = risk_decision.adjusted_weights or target_portfolio.target_weights
        gross = sum(abs(w) for w in active_weights.values())
        net = sum(w for w in active_weights.values())

        return OrderPreview(
            run_id=order_batch.metadata.get("run_id", "run_unknown"),
            strategy_id=order_batch.strategy_id,
            target_portfolio_id=order_batch.target_portfolio_id,
            risk_decision_id=order_batch.metadata.get("risk_decision_id", "dec_unknown"),
            order_batch_id=order_batch.batch_id,
            created_at=now,
            items=items,
            gross_exposure=gross,
            net_exposure=net,
            current_cash=cash,
            resulting_cash=projected_cash,
            risk_approved=risk_decision.approved,
            risk_violations=risk_decision.violations,
            broker_constraints=broker_constraints or {},
        )
