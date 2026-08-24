"""Execution approval boundary interfaces, preview structures, and manual approval gates."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
import uuid
from typing import Any

from ..core.enums import ExecutionMode, OrderStatus
from ..core.exceptions import ModeViolationError, OMSError
from ..core.interfaces import OrderBatch
from .lifecycle import transition_order


class ApprovalStatus(str, Enum):
    """Lifecycle status of a human execution approval token."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


@dataclass
class ApprovalToken:
    """Cryptographically unique approval token binding a specific batch to a human operator."""
    token_id: str
    order_batch_id: str
    risk_decision_id: str
    target_portfolio_id: str
    run_id: str
    approved_by: str
    approved_at: datetime
    expires_at: datetime
    status: ApprovalStatus = ApprovalStatus.APPROVED
    invalidation_reason: str | None = None

    def is_valid(self, as_of: datetime | None = None) -> bool:
        """Checks whether approval is active, unexpired, and not invalidated."""
        now = as_of or datetime.now(timezone.utc)
        if self.status != ApprovalStatus.APPROVED:
            return False
        if now > self.expires_at:
            return False
        return True

    def invalidate(self, reason: str) -> None:
        """Invalidates the approval token (e.g. upon order modification or market shock)."""
        self.status = ApprovalStatus.INVALIDATED
        self.invalidation_reason = reason


class ExecutionApprovalGate(ABC):
    """Abstract execution approval gate sitting between OMS and BrokerAdapter."""

    @abstractmethod
    def approve_batch(
        self,
        batch: OrderBatch,
        token: ApprovalToken | None = None,
    ) -> OrderBatch:
        """Processes an OrderBatch and returns approved orders."""
        raise NotImplementedError

    request_approval = approve_batch


class AutoApproveGate(ExecutionApprovalGate):
    """Automatic approval gate permitted ONLY for PaperBroker and simulated testing environments."""

    def approve_batch(
        self,
        batch: OrderBatch,
        token: ApprovalToken | None = None,
    ) -> OrderBatch:
        """Transitions all CREATED orders in batch to APPROVED status. Forbidden in LIVE mode."""
        if batch.execution_mode == ExecutionMode.LIVE:
            raise ModeViolationError(
                "CRITICAL: AutoApproveGate is strictly prohibited in LIVE mode! "
                "Mandatory human approval (ManualApprovalGate) is required."
            )

        approved_orders = []
        for order in batch.orders:
            if order.status == OrderStatus.CREATED:
                approved_orders.append(transition_order(order, OrderStatus.APPROVED))
            else:
                approved_orders.append(order)
        return replace(batch, orders=approved_orders)

    request_approval = approve_batch


class ManualApprovalGate(ExecutionApprovalGate):
    """Mandatory Human-In-The-Loop approval gate for controlled live and validated paper executions."""

    def __init__(self, default_ttl_minutes: float = 15.0) -> None:
        self.default_ttl = timedelta(minutes=default_ttl_minutes)
        self._tokens: dict[str, ApprovalToken] = {}  # batch_id -> token

    def grant_approval(
        self,
        order_batch_id: str,
        risk_decision_id: str,
        target_portfolio_id: str,
        run_id: str,
        approved_by: str = "operator_human",
        ttl_minutes: float | None = None,
    ) -> ApprovalToken:
        """Issues an ApprovalToken authorizing broker submission for this exact batch identity."""
        now = datetime.now(timezone.utc)
        ttl = timedelta(minutes=ttl_minutes) if ttl_minutes is not None else self.default_ttl
        token_id = f"tok_{uuid.uuid4().hex[:12]}"

        token = ApprovalToken(
            token_id=token_id,
            order_batch_id=order_batch_id,
            risk_decision_id=risk_decision_id,
            target_portfolio_id=target_portfolio_id,
            run_id=run_id,
            approved_by=approved_by,
            approved_at=now,
            expires_at=now + ttl,
            status=ApprovalStatus.APPROVED,
        )
        self._tokens[order_batch_id] = token
        return token

    def reject_approval(
        self,
        order_batch_id: str,
        reason: str = "Operator rejected order batch",
    ) -> None:
        """Explicitly records human operator rejection."""
        if order_batch_id in self._tokens:
            self._tokens[order_batch_id].status = ApprovalStatus.REJECTED
            self._tokens[order_batch_id].invalidation_reason = reason

    def invalidate_batch(self, order_batch_id: str, reason: str) -> None:
        """Invalidates an issued token."""
        if order_batch_id in self._tokens:
            self._tokens[order_batch_id].invalidate(reason)

    def approve_batch(
        self,
        batch: OrderBatch,
        token: ApprovalToken | None = None,
    ) -> OrderBatch:
        """Validates approval token against batch metadata before transitioning orders to APPROVED."""
        active_token = token or self._tokens.get(batch.batch_id)

        if active_token is None:
            raise OMSError(f"Execution rejected: OrderBatch {batch.batch_id} lacks human approval token.")

        if not active_token.is_valid():
            status_str = active_token.status.value
            if datetime.now(timezone.utc) > active_token.expires_at:
                status_str = "EXPIRED"
            raise OMSError(
                f"Execution rejected: ApprovalToken {active_token.token_id} is not valid ({status_str}). "
                f"Reason: {active_token.invalidation_reason or 'TTL expired or revoked'}."
            )

        # Strict identity verification
        if active_token.order_batch_id != batch.batch_id:
            raise OMSError(
                f"Execution rejected: ApprovalToken batch ID ({active_token.order_batch_id}) "
                f"does not match submitted batch ID ({batch.batch_id})."
            )

        if active_token.target_portfolio_id != batch.target_portfolio_id:
            raise OMSError(
                f"Execution rejected: TargetPortfolio ID mismatch on token ({active_token.target_portfolio_id}) "
                f"vs batch ({batch.target_portfolio_id})."
            )

        approved_orders = []
        for order in batch.orders:
            if order.status == OrderStatus.CREATED:
                approved_orders.append(transition_order(order, OrderStatus.APPROVED))
            else:
                approved_orders.append(order)

        return replace(batch, orders=approved_orders)

    request_approval = approve_batch


class AutonomousApprovalGate(ExecutionApprovalGate):
    """P9 Controlled Autonomous execution approval gate replacing human approval within strict boundaries."""

    def __init__(
        self,
        autonomous_execution_enabled: bool = False,
        strategy_whitelist: tuple[str, ...] = ("systematic_macro_v1", "systematic_macro"),
        emergency_stop_active: bool = False,
        ttl_minutes: float = 15.0,
    ) -> None:
        self.autonomous_execution_enabled = autonomous_execution_enabled
        self.strategy_whitelist = strategy_whitelist
        self.emergency_stop_active = emergency_stop_active
        self.default_ttl = timedelta(minutes=ttl_minutes)
        self._tokens: dict[str, ApprovalToken] = {}

    def generate_autonomous_token(
        self,
        order_batch_id: str,
        risk_decision_id: str,
        target_portfolio_id: str,
        run_id: str,
        strategy_id: str,
    ) -> ApprovalToken:
        """Generates an Autonomous ApprovalToken after verifying all autonomous precondition gates."""
        if not self.autonomous_execution_enabled:
            raise ModeViolationError(
                "Autonomous approval rejected: AUTONOMOUS_EXECUTION_ENABLED is false. "
                "Manual human approval is required."
            )

        if self.emergency_stop_active:
            raise ModeViolationError("Autonomous approval rejected: EMERGENCY_STOP is active.")

        if strategy_id not in self.strategy_whitelist:
            raise ModeViolationError(
                f"Autonomous approval rejected: Strategy {strategy_id!r} is not in autonomous whitelist {self.strategy_whitelist}."
            )

        now = datetime.now(timezone.utc)
        token_id = f"tok_auto_{uuid.uuid4().hex[:12]}"
        token = ApprovalToken(
            token_id=token_id,
            order_batch_id=order_batch_id,
            risk_decision_id=risk_decision_id,
            target_portfolio_id=target_portfolio_id,
            run_id=run_id,
            approved_by="P9_AUTONOMOUS_GATE",
            approved_at=now,
            expires_at=now + self.default_ttl,
            status=ApprovalStatus.APPROVED,
        )
        self._tokens[order_batch_id] = token
        return token

    def approve_batch(
        self,
        batch: OrderBatch,
        token: ApprovalToken | None = None,
    ) -> OrderBatch:
        """Approves batch using generated autonomous token."""
        if not self.autonomous_execution_enabled:
            raise ModeViolationError("Auto approval rejected: AUTONOMOUS_EXECUTION_ENABLED is false.")

        if self.emergency_stop_active:
            raise ModeViolationError("Auto approval rejected: EMERGENCY_STOP is active.")

        if batch.strategy_id not in self.strategy_whitelist:
            raise ModeViolationError(
                f"Strategy {batch.strategy_id!r} is not in autonomous whitelist {self.strategy_whitelist}."
            )

        active_token = token or self._tokens.get(batch.batch_id)
        if active_token is None:
            raise OMSError(f"Execution rejected: OrderBatch {batch.batch_id} lacks autonomous approval token.")

        if not active_token.is_valid():
            raise OMSError(f"Execution rejected: Autonomous token {active_token.token_id} is expired or invalid.")

        if active_token.order_batch_id != batch.batch_id:
            raise OMSError(f"Token batch ID ({active_token.order_batch_id}) mismatch vs batch ({batch.batch_id}).")

        approved_orders = []
        for order in batch.orders:
            if order.status == OrderStatus.CREATED:
                approved_orders.append(transition_order(order, OrderStatus.APPROVED))
            else:
                approved_orders.append(order)

        return replace(batch, orders=approved_orders)

    request_approval = approve_batch
