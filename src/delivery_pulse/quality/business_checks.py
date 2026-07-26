"""Numeric, temporal, status, and cross-table business checks."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import numpy as np
import pandas as pd

from delivery_pulse.quality.contracts import (
    MAX_OPERATIONAL_OVERLOAD_RATIO,
    PRIMARY_KEYS,
    UPPER_BOUNDS,
)
from delivery_pulse.quality.models import CheckResult, QualityIssue, Severity

NONNEGATIVE: dict[str, tuple[str, ...]] = {
    "customers": ("payment_terms_days",),
    "drivers": ("experience_years",),
    "vehicles": ("odometer_at_observation_start_km",),
    "orders": ("quoted_revenue",),
    "deliveries": (
        "fuel_cost",
        "driver_cost",
        "toll_cost",
        "maintenance_allocated_cost",
        "other_cost",
        "penalty_amount",
    ),
    "route_events": ("delay_minutes", "extra_cost"),
    "maintenance": ("odometer_km", "cost_amount", "downtime_hours"),
}
POSITIVE: dict[str, tuple[str, ...]] = {
    "customers": ("default_sla_hours",),
    "routes": ("standard_distance_km", "standard_transit_hours"),
    "vehicles": ("capacity_kg", "fuel_consumption_l_100km"),
    "orders": ("cargo_weight_kg", "distance_planned_km"),
    "deliveries": ("distance_actual_km",),
}


def _samples(
    frame: pd.DataFrame,
    mask: pd.Series,
    columns: Iterable[str],
    max_samples: int,
) -> list[str]:
    usable = [column for column in columns if column in frame]
    return cast(
        list[str],
        frame.loc[mask, usable]
        .head(max_samples)
        .astype(str)
        .agg(" | ".join, axis=1)
        .tolist(),
    )


def _add(
    result: CheckResult,
    *,
    check_id: str,
    severity: Severity,
    table: str,
    column: str | None,
    issue_type: str,
    message: str,
    mask: pd.Series,
    frame: pd.DataFrame,
    sample_columns: Iterable[str],
    max_samples: int,
    hint: str,
) -> None:
    if not mask.any():
        return
    result.issues.append(
        QualityIssue(
            check_id,
            severity,
            table,
            column,
            PRIMARY_KEYS.get(table),
            issue_type,
            message,
            int(mask.sum()),
            _samples(frame, mask, sample_columns, max_samples),
            hint,
        )
    )


def run_business_checks(
    tables: dict[str, pd.DataFrame],
    max_samples: int,
) -> CheckResult:
    """Run physical, financial, temporal, and operational rules."""
    result = CheckResult()
    _check_numbers(tables, max_samples, result)
    _check_statuses(tables, max_samples, result)
    _check_chronology(tables, max_samples, result)
    _check_overload(tables, max_samples, result)
    _check_maintenance(tables, max_samples, result)
    _check_resource_overlaps(tables, max_samples, result)
    _check_breakdown_repairs(tables, max_samples, result)
    return result


def _check_numbers(
    tables: dict[str, pd.DataFrame],
    max_samples: int,
    result: CheckResult,
) -> None:
    for table, columns in NONNEGATIVE.items():
        if table not in tables:
            continue
        for column in columns:
            if column not in tables[table]:
                continue
            frame = tables[table]
            check_id = f"business.nonnegative.{table}.{column}"
            result.checks.add(check_id)
            invalid = frame[column].notna() & (
                ~np.isfinite(frame[column].astype(float)) | (frame[column] < 0)
            )
            _add(
                result,
                check_id=check_id,
                severity=Severity.ERROR,
                table=table,
                column=column,
                issue_type="invalid_numeric_value",
                message="Value must be finite and non-negative.",
                mask=invalid,
                frame=frame,
                sample_columns=[PRIMARY_KEYS[table], column],
                max_samples=max_samples,
                hint="Quarantine impossible values and correct the source.",
            )
    for table, columns in POSITIVE.items():
        if table not in tables:
            continue
        for column in columns:
            if column not in tables[table]:
                continue
            frame = tables[table]
            check_id = f"business.positive.{table}.{column}"
            result.checks.add(check_id)
            invalid = frame[column].notna() & (
                ~np.isfinite(frame[column].astype(float)) | (frame[column] <= 0)
            )
            _add(
                result,
                check_id=check_id,
                severity=Severity.ERROR,
                table=table,
                column=column,
                issue_type="invalid_numeric_value",
                message="Value must be finite and positive when present.",
                mask=invalid,
                frame=frame,
                sample_columns=[PRIMARY_KEYS[table], column],
                max_samples=max_samples,
                hint="Quarantine impossible values and correct the source.",
            )
    for (table, column), upper in UPPER_BOUNDS.items():
        if table not in tables or column not in tables[table]:
            continue
        frame = tables[table]
        check_id = f"business.upper_bound.{table}.{column}"
        result.checks.add(check_id)
        high = frame[column].notna() & (frame[column] > upper)
        issue_type = "cost_outlier" if "cost" in column else "suspicious_outlier"
        _add(
            result,
            check_id=check_id,
            severity=Severity.WARNING,
            table=table,
            column=column,
            issue_type=issue_type,
            message=f"Value exceeds the documented plausibility ceiling {upper:g}.",
            mask=high,
            frame=frame,
            sample_columns=[PRIMARY_KEYS[table], column],
            max_samples=max_samples,
            hint="Investigate the source; do not remove rare values automatically.",
        )
    if "vehicles" in tables and "manufacture_year" in tables["vehicles"]:
        frame = tables["vehicles"]
        check_id = "business.vehicle_manufacture_year"
        result.checks.add(check_id)
        invalid = frame["manufacture_year"].notna() & (
            (frame["manufacture_year"] < 1980)
            | (frame["manufacture_year"] > pd.Timestamp.now(tz="UTC").year)
        )
        _add(
            result,
            check_id=check_id,
            severity=Severity.ERROR,
            table="vehicles",
            column="manufacture_year",
            issue_type="invalid_numeric_value",
            message="Manufacture year is outside a plausible historical range.",
            mask=invalid,
            frame=frame,
            sample_columns=["vehicle_id", "manufacture_year"],
            max_samples=max_samples,
            hint="Correct the year or quarantine the vehicle record.",
        )


def _check_statuses(
    tables: dict[str, pd.DataFrame],
    max_samples: int,
    result: CheckResult,
) -> None:
    if "orders" not in tables or "deliveries" not in tables:
        return
    orders = tables["orders"]
    deliveries = tables["deliveries"]
    if not {"order_id", "order_status"} <= set(orders) or not {
        "order_id",
        "delivery_status",
    } <= set(deliveries):
        return
    merged = deliveries.merge(
        orders[["order_id", "order_status"]],
        on="order_id",
        how="left",
        suffixes=("", "_order"),
    )
    check_id = "business.status_matrix"
    result.checks.add(check_id)
    allowed = {
        ("assigned", "planned"),
        ("assigned", "in_transit"),
        ("completed", "delivered"),
        ("completed", "failed"),
        ("cancelled", "cancelled"),
    }
    valid = pd.Series(
        [
            (order_status, delivery_status) in allowed
            for order_status, delivery_status in zip(
                merged["order_status"], merged["delivery_status"], strict=True
            )
        ],
        index=merged.index,
    )
    _add(
        result,
        check_id=check_id,
        severity=Severity.CRITICAL,
        table="deliveries",
        column="delivery_status",
        issue_type="invalid_status_pair",
        message="Order and delivery statuses violate the first-release matrix.",
        mask=~valid,
        frame=merged,
        sample_columns=["delivery_id", "order_id", "order_status", "delivery_status"],
        max_samples=max_samples,
        hint="Quarantine inconsistent terminal states and reconcile lifecycle history.",
    )
    check_id = "business.delivered_required_fields"
    result.checks.add(check_id)
    delivered = deliveries["delivery_status"].eq("delivered")
    required = [
        "actual_departure_at",
        "actual_delivery_at",
        "distance_actual_km",
        "fuel_cost",
        "driver_cost",
        "toll_cost",
        "maintenance_allocated_cost",
        "other_cost",
        "penalty_amount",
    ]
    available = [column for column in required if column in deliveries]
    missing = delivered & deliveries[available].isna().any(axis=1)
    _add(
        result,
        check_id=check_id,
        severity=Severity.ERROR,
        table="deliveries",
        column=",".join(available),
        issue_type="missing_status_required_value",
        message="Delivered rows require actual times, distance, and complete finances.",
        mask=missing,
        frame=deliveries,
        sample_columns=["delivery_id", *available],
        max_samples=max_samples,
        hint="Quarantine incomplete delivered rows until the values are restored.",
    )
    check_id = "business.unfinished_without_completion"
    result.checks.add(check_id)
    unfinished = ~delivered
    invalid = unfinished & deliveries["actual_delivery_at"].notna()
    _add(
        result,
        check_id=check_id,
        severity=Severity.ERROR,
        table="deliveries",
        column="actual_delivery_at",
        issue_type="status_completion_conflict",
        message="Unfinished deliveries must not have actual_delivery_at.",
        mask=invalid,
        frame=deliveries,
        sample_columns=["delivery_id", "delivery_status", "actual_delivery_at"],
        max_samples=max_samples,
        hint="Reconcile delivery status and completion timestamp.",
    )
    failed = deliveries["delivery_status"].eq("failed")
    failed_ids = set(deliveries.loc[failed, "delivery_id"])
    events = tables.get("route_events")
    if events is not None and {"delivery_id", "event_type"} <= set(events):
        documented = set(events.loc[events["event_type"].notna(), "delivery_id"])
        missing_reason = failed & ~deliveries["delivery_id"].isin(documented)
        check_id = "business.failed_reason"
        result.checks.add(check_id)
        _add(
            result,
            check_id=check_id,
            severity=Severity.ERROR,
            table="deliveries",
            column="delivery_status",
            issue_type="missing_failed_reason",
            message="Failed delivery requires a documented route event reason.",
            mask=missing_reason,
            frame=deliveries,
            sample_columns=["delivery_id", "order_id"],
            max_samples=max_samples,
            hint="Add a documented operational reason without inventing one.",
        )
        del failed_ids


def _check_chronology(
    tables: dict[str, pd.DataFrame],
    max_samples: int,
    result: CheckResult,
) -> None:
    comparisons = [
        ("orders", "created_at", "requested_pickup_at", "<="),
        ("orders", "requested_pickup_at", "promised_delivery_at", "<"),
        ("deliveries", "actual_departure_at", "actual_delivery_at", "<="),
        ("route_events", "event_at", "event_end_at", "<="),
        ("maintenance", "started_at", "completed_at", "<="),
    ]
    for table, left, right, operator in comparisons:
        check_id = f"business.chronology.{table}.{left}.{right}"
        result.checks.add(check_id)
        if table not in tables or not {left, right} <= set(tables[table]):
            continue
        frame = tables[table]
        comparable = frame[left].notna() & frame[right].notna()
        valid = (
            frame[left] <= frame[right]
            if operator == "<="
            else frame[left] < frame[right]
        )
        invalid = comparable & ~valid
        _add(
            result,
            check_id=check_id,
            severity=Severity.ERROR,
            table=table,
            column=right,
            issue_type="chronology_violation",
            message=f"Required chronology {left} {operator} {right} is violated.",
            mask=invalid,
            frame=frame,
            sample_columns=[PRIMARY_KEYS[table], left, right],
            max_samples=max_samples,
            hint="Quarantine the row and correct timestamps from source history.",
        )
    _check_event_intervals(tables, max_samples, result)
    _check_odometer_sequence(tables, max_samples, result)


def _check_event_intervals(
    tables: dict[str, pd.DataFrame],
    max_samples: int,
    result: CheckResult,
) -> None:
    if "route_events" not in tables or "deliveries" not in tables:
        return
    events = tables["route_events"]
    deliveries = tables["deliveries"]
    required = {"delivery_id", "event_at", "event_end_at"}
    if not required <= set(events) or not {
        "delivery_id",
        "planned_departure_at",
        "actual_departure_at",
        "actual_delivery_at",
    } <= set(deliveries):
        return
    merged = events.merge(
        deliveries[
            [
                "delivery_id",
                "planned_departure_at",
                "actual_departure_at",
                "actual_delivery_at",
            ]
        ],
        on="delivery_id",
        how="left",
    )
    check_id = "business.event_delivery_interval"
    result.checks.add(check_id)
    lower = merged["planned_departure_at"]
    upper = merged["actual_delivery_at"].fillna(
        merged["actual_departure_at"] + pd.Timedelta(hours=12)
    )
    invalid = (
        merged["event_at"].notna()
        & lower.notna()
        & upper.notna()
        & ((merged["event_at"] < lower) | (merged["event_end_at"] > upper))
    )
    _add(
        result,
        check_id=check_id,
        severity=Severity.ERROR,
        table="route_events",
        column="event_at,event_end_at",
        issue_type="event_outside_delivery",
        message="Route event lies outside its allowed delivery interval.",
        mask=invalid,
        frame=merged,
        sample_columns=["event_id", "delivery_id", "event_at", "event_end_at"],
        max_samples=max_samples,
        hint="Quarantine the event and reconcile it to the correct delivery.",
    )


def _check_odometer_sequence(
    tables: dict[str, pd.DataFrame],
    max_samples: int,
    result: CheckResult,
) -> None:
    if "maintenance" not in tables:
        return
    frame = tables["maintenance"]
    if not {"vehicle_id", "started_at", "odometer_km"} <= set(frame):
        return
    ordered = frame.sort_values(["vehicle_id", "started_at", "maintenance_id"])
    previous = ordered.groupby("vehicle_id")["odometer_km"].shift()
    invalid = (
        ordered["odometer_km"].notna()
        & previous.notna()
        & (ordered["odometer_km"] < previous)
    )
    check_id = "business.maintenance_odometer_sequence"
    result.checks.add(check_id)
    _add(
        result,
        check_id=check_id,
        severity=Severity.ERROR,
        table="maintenance",
        column="odometer_km",
        issue_type="odometer_decrease",
        message="Vehicle maintenance odometer decreases over time.",
        mask=invalid,
        frame=ordered,
        sample_columns=["maintenance_id", "vehicle_id", "odometer_km"],
        max_samples=max_samples,
        hint="Reconcile odometer history before reliability analysis.",
    )


def _check_overload(
    tables: dict[str, pd.DataFrame],
    max_samples: int,
    result: CheckResult,
) -> None:
    if not {"orders", "deliveries", "vehicles"} <= set(tables):
        return
    frame = (
        tables["deliveries"][["delivery_id", "order_id", "vehicle_id"]]
        .merge(
            tables["orders"][["order_id", "cargo_weight_kg"]],
            on="order_id",
            how="left",
        )
        .merge(
            tables["vehicles"][["vehicle_id", "capacity_kg"]],
            on="vehicle_id",
            how="left",
        )
    )
    utilization = frame["cargo_weight_kg"] / frame["capacity_kg"]
    check_id = "business.capacity_utilization"
    result.checks.add(check_id)
    operational = (utilization > 1) & (utilization <= MAX_OPERATIONAL_OVERLOAD_RATIO)
    artificial = utilization > MAX_OPERATIONAL_OVERLOAD_RATIO
    frame = frame.assign(capacity_utilization=utilization)
    _add(
        result,
        check_id=check_id,
        severity=Severity.WARNING,
        table="orders",
        column="cargo_weight_kg",
        issue_type="operational_overload",
        message="Documented operational overload is within the 5% tolerance.",
        mask=operational,
        frame=frame,
        sample_columns=["order_id", "vehicle_id", "capacity_utilization"],
        max_samples=max_samples,
        hint="Keep for analysis and review the vehicle assignment process.",
    )
    _add(
        result,
        check_id=check_id,
        severity=Severity.ERROR,
        table="orders",
        column="cargo_weight_kg",
        issue_type="artificial_overload",
        message="Capacity utilization exceeds the documented operational limit.",
        mask=artificial,
        frame=frame,
        sample_columns=["order_id", "vehicle_id", "capacity_utilization"],
        max_samples=max_samples,
        hint="Quarantine the row and validate cargo mass and assigned vehicle.",
    )


def _delivery_intervals(deliveries: pd.DataFrame) -> pd.DataFrame:
    usable = deliveries.dropna(subset=["actual_departure_at"]).copy()
    usable["interval_end"] = usable["actual_delivery_at"].fillna(
        usable["actual_departure_at"] + pd.Timedelta(hours=12)
    )
    return usable


def _check_maintenance(
    tables: dict[str, pd.DataFrame],
    max_samples: int,
    result: CheckResult,
) -> None:
    if "maintenance" not in tables or "deliveries" not in tables:
        return
    maintenance = tables["maintenance"]
    deliveries = _delivery_intervals(tables["deliveries"])
    check_id = "business.maintenance_delivery_overlap"
    result.checks.add(check_id)
    offenders: list[dict[str, object]] = []
    for service in maintenance.dropna(subset=["started_at"]).itertuples(index=False):
        service_end = (
            service.completed_at
            if pd.notna(service.completed_at)
            else service.started_at
        )
        assigned = deliveries.loc[deliveries["vehicle_id"] == service.vehicle_id]
        overlap = (assigned["actual_departure_at"] < service_end) & (
            assigned["interval_end"] > service.started_at
        )
        for delivery_id in assigned.loc[overlap, "delivery_id"]:
            offenders.append(
                {
                    "maintenance_id": service.maintenance_id,
                    "vehicle_id": service.vehicle_id,
                    "delivery_id": delivery_id,
                }
            )
    if offenders:
        samples = [
            " | ".join(str(value) for value in row.values())
            for row in offenders[:max_samples]
        ]
        result.issues.append(
            QualityIssue(
                check_id,
                Severity.ERROR,
                "maintenance",
                "started_at,completed_at",
                "maintenance_id",
                "maintenance_delivery_overlap",
                "Vehicle maintenance overlaps an assigned delivery.",
                len(offenders),
                samples,
                "Quarantine conflicting assignments and repair scheduling history.",
            )
        )
    check_id = "business.preperiod_maintenance"
    result.checks.add(check_id)
    if "orders" in tables and not tables["orders"].empty:
        observation_start = tables["orders"]["requested_pickup_at"].min()
        active_ids = (
            set(tables["vehicles"]["vehicle_id"])
            if "vehicles" in tables
            else set(deliveries["vehicle_id"])
        )
        previous = maintenance.loc[
            maintenance["completed_at"].notna()
            & (maintenance["completed_at"] < observation_start)
            & maintenance["maintenance_status"].eq("completed"),
            "vehicle_id",
        ]
        missing_ids = sorted(active_ids - set(previous))
        if missing_ids:
            result.issues.append(
                QualityIssue(
                    check_id,
                    Severity.ERROR,
                    "maintenance",
                    "completed_at",
                    "vehicle_id",
                    "missing_preperiod_maintenance",
                    "Active vehicles lack completed pre-period maintenance.",
                    len(missing_ids),
                    [str(value) for value in missing_ids[:max_samples]],
                    "Restore the starting maintenance state before "
                    "reliability analysis.",
                )
            )


def _overlap_rows(
    intervals: pd.DataFrame,
    resource: str,
) -> list[tuple[object, object, object]]:
    offenders: list[tuple[object, object, object]] = []
    for resource_id, group in intervals.groupby(resource):
        ordered = group.sort_values(["actual_departure_at", "interval_end"])
        prior_end: pd.Timestamp | None = None
        prior_delivery: object = None
        for row in ordered.itertuples(index=False):
            if prior_end is not None and row.actual_departure_at < prior_end:
                offenders.append((resource_id, prior_delivery, row.delivery_id))
            if prior_end is None or row.interval_end > prior_end:
                prior_end = row.interval_end
                prior_delivery = row.delivery_id
    return offenders


def _check_resource_overlaps(
    tables: dict[str, pd.DataFrame],
    max_samples: int,
    result: CheckResult,
) -> None:
    if "deliveries" not in tables:
        return
    intervals = _delivery_intervals(tables["deliveries"])
    for resource in ("vehicle_id", "driver_id"):
        if resource not in intervals:
            continue
        check_id = f"business.delivery_overlap.{resource}"
        result.checks.add(check_id)
        offenders = _overlap_rows(intervals, resource)
        if offenders:
            result.issues.append(
                QualityIssue(
                    check_id,
                    Severity.WARNING,
                    "deliveries",
                    resource,
                    "delivery_id",
                    "resource_delivery_overlap",
                    f"{resource} has overlapping delivery intervals; availability "
                    "calendar is not present in the first-release model.",
                    len(offenders),
                    [" | ".join(map(str, row)) for row in offenders[:max_samples]],
                    "Review assignments; add an availability calendar before blocking.",
                )
            )


def _check_breakdown_repairs(
    tables: dict[str, pd.DataFrame],
    max_samples: int,
    result: CheckResult,
) -> None:
    if not {"route_events", "deliveries", "maintenance"} <= set(tables):
        return
    events = tables["route_events"]
    breakdowns = events.loc[events["event_type"].eq("breakdown")].merge(
        tables["deliveries"][["delivery_id", "vehicle_id"]],
        on="delivery_id",
        how="left",
    )
    repairs = tables["maintenance"].loc[
        tables["maintenance"]["maintenance_type"].eq("repair")
    ]
    check_id = "business.breakdown_repair_link"
    result.checks.add(check_id)
    missing: list[object] = []
    for event in breakdowns.itertuples(index=False):
        same_vehicle = repairs.loc[repairs["vehicle_id"] == event.vehicle_id]
        linked = same_vehicle["started_at"].ge(event.event_at).any()
        if not linked:
            missing.append(event.event_id)
    if missing:
        result.issues.append(
            QualityIssue(
                check_id,
                Severity.WARNING,
                "route_events",
                "event_type",
                "event_id",
                "breakdown_without_repair",
                "Breakdown event has no later repair for the same vehicle.",
                len(missing),
                [str(value) for value in missing[:max_samples]],
                "Review repair linkage; an explicit incident key is not in v1 schema.",
            )
        )
