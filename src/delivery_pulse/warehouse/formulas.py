"""Small Python references used only to test SQL metric parity."""

from __future__ import annotations

from decimal import Decimal


def delay_minutes(promised_minutes: int, actual_minutes: int) -> int:
    """Return non-negative lateness from comparable minute offsets."""
    return max(0, actual_minutes - promised_minutes)


def total_delivery_cost(*components: Decimal | None) -> Decimal | None:
    """Sum known cost components, preserving unknown financial values."""
    if any(component is None for component in components):
        return None
    return sum(
        (component for component in components if component is not None), Decimal()
    )


def net_revenue(
    quoted_revenue: Decimal | None,
    penalty_amount: Decimal | None,
) -> Decimal | None:
    """Subtract SLA penalty from quoted revenue when both are known."""
    if quoted_revenue is None or penalty_amount is None:
        return None
    return quoted_revenue - penalty_amount


def delivery_profit(
    revenue: Decimal | None,
    cost: Decimal | None,
) -> Decimal | None:
    """Return contribution profit when revenue and cost are known."""
    if revenue is None or cost is None:
        return None
    return revenue - cost


def margin_pct(
    profit: Decimal | None,
    revenue: Decimal | None,
) -> Decimal | None:
    """Return row margin, preserving NULL for unknown or zero revenue."""
    if profit is None or revenue is None or revenue == 0:
        return None
    return profit / revenue


def group_margin_pct(
    profits: list[Decimal],
    revenues: list[Decimal],
) -> Decimal | None:
    """Return ratio of sums rather than an average of row margins."""
    total_revenue = sum(revenues, Decimal())
    if total_revenue == 0:
        return None
    return sum(profits, Decimal()) / total_revenue
