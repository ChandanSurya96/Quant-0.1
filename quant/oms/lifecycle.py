"""Order state machine and lifecycle validation."""

from __future__ import annotations

from dataclasses import replace

from ..core.enums import OrderStatus
from ..core.exceptions import InvalidStateTransitionError
from ..core.interfaces import Order

VALID_ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {OrderStatus.APPROVED, OrderStatus.CANCELLED, OrderStatus.REJECTED},
    OrderStatus.APPROVED: {OrderStatus.SUBMITTED, OrderStatus.CANCELLED, OrderStatus.REJECTED},
    OrderStatus.SUBMITTED: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED, OrderStatus.REJECTED},
    OrderStatus.PARTIALLY_FILLED: {OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED, OrderStatus.CANCELLED},
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
}


def validate_transition(current_status: OrderStatus, new_status: OrderStatus) -> bool:
    """Validates that a requested order state transition is legal."""
    if current_status == new_status:
        return True

    allowed = VALID_ORDER_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise InvalidStateTransitionError(
            f"Illegal order state transition from {current_status.value} to {new_status.value} "
            f"(allowed: {[s.value for s in allowed]})."
        )
    return True


def transition_order(order: Order, new_status: OrderStatus) -> Order:
    """Validates and returns a new Order instance with updated status."""
    validate_transition(order.status, new_status)
    return replace(order, status=new_status)
