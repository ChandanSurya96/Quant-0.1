"""Reconciliation engine comparing internal SQLite state against broker reported state."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from ..broker.base import BrokerAdapter
from ..core.enums import ExecutionMode, OrderSide, OrderStatus
from ..persistence.database import DatabaseManager
from ..persistence.repositories.fill_repo import FillRepository
from ..persistence.repositories.holding_repo import HoldingRepository
from ..persistence.repositories.order_repo import OrderRepository
from ..persistence.repositories.snapshot_repo import SnapshotRepository
from .types import (
    ReconciliationConfig,
    ReconciliationIssue,
    ReconciliationIssueType,
    ReconciliationResult,
    ReconciliationStatus,
)


class ReconciliationEngine:
    """Detects discrepancies between internal operational state and external broker execution state."""

    @staticmethod
    def reconcile(
        run_id: str,
        execution_mode: ExecutionMode,
        db_manager: DatabaseManager,
        broker: BrokerAdapter,
        config: ReconciliationConfig | None = None,
        reconciliation_id: str | None = None,
    ) -> ReconciliationResult:
        """Compares internal holdings, cash, NAV, orders, and fills against broker reported state."""
        cfg = config or ReconciliationConfig()
        rec_id = reconciliation_id or f"rec_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)
        issues: list[ReconciliationIssue] = []

        holding_repo = HoldingRepository(db_manager)
        order_repo = OrderRepository(db_manager)
        fill_repo = FillRepository(db_manager)
        snap_repo = SnapshotRepository(db_manager)

        # ------------------------------------------------ 1. Position Reconciliation
        internal_holdings_map = holding_repo.get_holdings()
        broker_positions_map = broker.get_positions()

        all_symbols = sorted(set(internal_holdings_map.keys()) | set(broker_positions_map.keys()))
        int_holdings_dict: dict[str, float] = {}
        brk_positions_dict: dict[str, float] = {}

        for sym in all_symbols:
            h_int = internal_holdings_map.get(sym)
            q_int = h_int.shares if h_int is not None else 0.0
            int_holdings_dict[sym] = q_int

            h_brk = broker_positions_map.get(sym)
            q_brk = h_brk.shares if h_brk is not None else 0.0
            brk_positions_dict[sym] = q_brk

            diff = q_int - q_brk
            if abs(diff) > cfg.position_qty_tolerance:
                if sym in internal_holdings_map and sym not in broker_positions_map:
                    issues.append(
                        ReconciliationIssue(
                            issue_type=ReconciliationIssueType.POSITION_MISSING_BROKER,
                            symbol=sym,
                            internal_value=q_int,
                            broker_value=0.0,
                            discrepancy=diff,
                            message=f"Position {sym} exists internally ({q_int} shares) but missing at broker.",
                        )
                    )
                elif sym not in internal_holdings_map and sym in broker_positions_map:
                    issues.append(
                        ReconciliationIssue(
                            issue_type=ReconciliationIssueType.POSITION_MISSING_INTERNAL,
                            symbol=sym,
                            internal_value=0.0,
                            broker_value=q_brk,
                            discrepancy=diff,
                            message=f"Position {sym} exists at broker ({q_brk} shares) but missing internally.",
                        )
                    )
                else:
                    issues.append(
                        ReconciliationIssue(
                            issue_type=ReconciliationIssueType.POSITION_QUANTITY_MISMATCH,
                            symbol=sym,
                            internal_value=q_int,
                            broker_value=q_brk,
                            discrepancy=diff,
                            message=f"Position quantity mismatch for {sym}: internal={q_int}, broker={q_brk} (diff={diff}).",
                        )
                    )

        # ------------------------------------------------ 2. Cash & NAV Reconciliation
        latest_snap = snap_repo.get_latest_snapshot()
        broker_account = broker.get_account_state()

        int_cash = latest_snap["cash"] if latest_snap is not None else 0.0
        brk_cash = broker_account.cash
        cash_diff = int_cash - brk_cash
        if abs(cash_diff) > cfg.cash_tolerance:
            issues.append(
                ReconciliationIssue(
                    issue_type=ReconciliationIssueType.CASH_MISMATCH,
                    internal_value=int_cash,
                    broker_value=brk_cash,
                    discrepancy=cash_diff,
                    message=f"Cash mismatch: internal=${int_cash:.2f}, broker=${brk_cash:.2f} (diff=${cash_diff:.2f}).",
                )
            )

        # Mark internal holdings to market using current prices
        expected_internal_nav = int_cash + sum(
            h_int.shares * (broker_positions_map[sym].current_price if sym in broker_positions_map else h_int.current_price)
            for sym, h_int in internal_holdings_map.items()
        )
        brk_nav = broker_account.nav
        nav_diff = expected_internal_nav - brk_nav
        if abs(nav_diff) > cfg.nav_tolerance:
            issues.append(
                ReconciliationIssue(
                    issue_type=ReconciliationIssueType.NAV_MISMATCH,
                    internal_value=expected_internal_nav,
                    broker_value=brk_nav,
                    discrepancy=nav_diff,
                    message=f"NAV mismatch: internal=${expected_internal_nav:.2f}, broker=${brk_nav:.2f} (diff=${nav_diff:.2f}).",
                )
            )

        # Invariant: Broker NAV Conservation NAV == Cash + sum(Shares * Price)
        expected_brk_nav = brk_cash + sum(h.shares * h.current_price for h in broker_positions_map.values())
        if abs(brk_nav - expected_brk_nav) > cfg.nav_tolerance:
            issues.append(
                ReconciliationIssue(
                    issue_type=ReconciliationIssueType.NAV_CONSERVATION_VIOLATION,
                    internal_value=expected_brk_nav,
                    broker_value=brk_nav,
                    discrepancy=brk_nav - expected_brk_nav,
                    message=f"NAV conservation violation: reported NAV=${brk_nav:.2f} != Cash + Market Value (${expected_brk_nav:.2f}).",
                )
            )

        # ------------------------------------------------ 3. Order Reconciliation
        internal_orders = order_repo.list_orders_for_run(run_id)
        broker_orders = broker.get_all_orders()

        int_orders_map = {o.order_id: o for o in internal_orders}
        brk_orders_map = {o.order_id: o for o in broker_orders}

        for oid, o_int in int_orders_map.items():
            if oid not in brk_orders_map:
                issues.append(
                    ReconciliationIssue(
                        issue_type=ReconciliationIssueType.ORDER_MISSING_BROKER,
                        order_id=oid,
                        symbol=o_int.symbol,
                        internal_value=o_int.status.value,
                        broker_value=None,
                        message=f"Order {oid} ({o_int.symbol}) exists internally but missing at broker.",
                    )
                )
            else:
                o_brk = brk_orders_map[oid]
                # Check for unknown / unmapped broker order statuses
                if not isinstance(o_brk.status, OrderStatus):
                    issues.append(
                        ReconciliationIssue(
                            issue_type=ReconciliationIssueType.ORDER_UNKNOWN_STATE,
                            order_id=oid,
                            symbol=o_brk.symbol,
                            internal_value=o_int.status.value,
                            broker_value=str(o_brk.status),
                            message=f"Order {oid} has unknown/unrecognized broker state: {o_brk.status}.",
                        )
                    )
                elif o_int.status != o_brk.status:
                    issues.append(
                        ReconciliationIssue(
                            issue_type=ReconciliationIssueType.ORDER_STATUS_MISMATCH,
                            order_id=oid,
                            symbol=o_int.symbol,
                            internal_value=o_int.status.value,
                            broker_value=o_brk.status.value,
                            message=f"Order {oid} status mismatch: internal={o_int.status.value}, broker={o_brk.status.value}.",
                        )
                    )
                if abs(o_int.quantity - o_brk.quantity) > cfg.position_qty_tolerance:
                    issues.append(
                        ReconciliationIssue(
                            issue_type=ReconciliationIssueType.ORDER_QUANTITY_MISMATCH,
                            order_id=oid,
                            symbol=o_int.symbol,
                            internal_value=o_int.quantity,
                            broker_value=o_brk.quantity,
                            discrepancy=o_int.quantity - o_brk.quantity,
                            message=f"Order {oid} quantity mismatch: internal={o_int.quantity}, broker={o_brk.quantity}.",
                        )
                    )

        for oid, o_brk in brk_orders_map.items():
            if oid not in int_orders_map:
                existing_int = order_repo.get_order(oid)
                if existing_int is None:
                    issues.append(
                        ReconciliationIssue(
                            issue_type=ReconciliationIssueType.ORDER_MISSING_INTERNAL,
                            order_id=oid,
                            symbol=o_brk.symbol,
                            internal_value=None,
                            broker_value=o_brk.status.value if isinstance(o_brk.status, OrderStatus) else str(o_brk.status),
                            message=f"Order {oid} ({o_brk.symbol}) exists at broker but missing internally.",
                        )
                    )

        # ------------------------------------------------ 4. Fill & Overfill Reconciliation
        broker_fills = broker.get_fills()
        brk_fills_map = {f.fill_id: f for f in broker_fills}

        # Check fills by order for overfill detection
        fills_by_order: dict[str, list] = {}
        for f_brk in broker_fills:
            fills_by_order.setdefault(f_brk.order_id, []).append(f_brk)

        for oid, fills_list in fills_by_order.items():
            o_int = int_orders_map.get(oid) or brk_orders_map.get(oid)
            if o_int is not None:
                cum_qty = sum(f.quantity for f in fills_list)
                if cum_qty > o_int.quantity + cfg.position_qty_tolerance:
                    issues.append(
                        ReconciliationIssue(
                            issue_type=ReconciliationIssueType.FILL_OVERFILL,
                            order_id=oid,
                            symbol=o_int.symbol,
                            internal_value=o_int.quantity,
                            broker_value=cum_qty,
                            discrepancy=cum_qty - o_int.quantity,
                            message=f"Cumulative fills ({cum_qty}) exceed order quantity ({o_int.quantity}) for order {oid}.",
                        )
                    )

        # Check unique broker fills
        for fid, f_brk in brk_fills_map.items():
            int_fill = fill_repo.get_fill(fid)
            if int_fill is None:
                int_fill = fill_repo.get_fill_by_broker_execution_id(fid)

            if int_fill is None:
                issues.append(
                    ReconciliationIssue(
                        issue_type=ReconciliationIssueType.FILL_MISSING_INTERNAL,
                        fill_id=fid,
                        order_id=f_brk.order_id,
                        symbol=f_brk.symbol,
                        internal_value=None,
                        broker_value=f_brk.quantity,
                        message=f"Fill {fid} for order {f_brk.order_id} exists at broker but missing internally.",
                    )
                )
            else:
                if abs(int_fill.quantity - f_brk.quantity) > cfg.position_qty_tolerance:
                    issues.append(
                        ReconciliationIssue(
                            issue_type=ReconciliationIssueType.FILL_QUANTITY_MISMATCH,
                            fill_id=fid,
                            order_id=f_brk.order_id,
                            symbol=f_brk.symbol,
                            internal_value=int_fill.quantity,
                            broker_value=f_brk.quantity,
                            discrepancy=int_fill.quantity - f_brk.quantity,
                            message=f"Fill {fid} quantity mismatch: internal={int_fill.quantity}, broker={f_brk.quantity}.",
                        )
                    )
                if abs(int_fill.fill_price - f_brk.fill_price) > cfg.price_tolerance:
                    issues.append(
                        ReconciliationIssue(
                            issue_type=ReconciliationIssueType.FILL_PRICE_MISMATCH,
                            fill_id=fid,
                            order_id=f_brk.order_id,
                            symbol=f_brk.symbol,
                            internal_value=int_fill.fill_price,
                            broker_value=f_brk.fill_price,
                            discrepancy=int_fill.fill_price - f_brk.fill_price,
                            message=f"Fill {fid} price mismatch: internal={int_fill.fill_price}, broker={f_brk.fill_price}.",
                        )
                    )

        status = ReconciliationStatus.MATCHED if len(issues) == 0 else ReconciliationStatus.MISMATCHED

        return ReconciliationResult(
            reconciliation_id=rec_id,
            run_id=run_id,
            timestamp=now,
            execution_mode=execution_mode,
            status=status,
            issues=issues,
            internal_holdings=int_holdings_dict,
            broker_positions=brk_positions_dict,
            internal_cash=int_cash,
            broker_cash=brk_cash,
            internal_nav=expected_internal_nav,
            broker_nav=brk_nav,
        )
