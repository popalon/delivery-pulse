"""Reproducible injection of known data quality defects."""

from __future__ import annotations

import pandas as pd

from delivery_pulse.generation.random_state import RandomState

MANIFEST_COLUMNS = [
    "table_name",
    "record_id",
    "field_name",
    "issue_type",
    "expected_detection",
    "description",
]


def inject_quality_issues(
    tables: dict[str, pd.DataFrame],
    rng: RandomState,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    """Inject a bounded defect set and return copies plus a test-only manifest."""
    damaged = {name: table.copy(deep=True) for name, table in tables.items()}
    issues: list[dict[str, object]] = []

    customer_index = int(rng.integers(0, len(damaged["customers"])))
    customer_id = int(damaged["customers"].iloc[customer_index]["customer_id"])
    damaged["customers"].loc[customer_index, "customer_name"] = pd.NA
    issues.append(
        _issue(
            "customers",
            customer_id,
            "customer_name",
            "missing_required_value",
            "not_null",
            "Required synthetic customer name is missing.",
        )
    )

    duplicate_index = int(rng.integers(0, len(damaged["routes"])))
    duplicate = damaged["routes"].iloc[[duplicate_index]].copy()
    route_id = int(duplicate.iloc[0]["route_id"])
    damaged["routes"] = pd.concat([damaged["routes"], duplicate], ignore_index=True)
    issues.append(
        _issue(
            "routes",
            route_id,
            "route_id",
            "duplicate_primary_key",
            "unique_primary_key",
            "A complete route row is duplicated.",
        )
    )

    order_indices = rng.choice(len(damaged["orders"]), size=3, replace=False)
    broken_fk_index, chronology_index, overload_index = map(int, order_indices)

    broken_order_id = int(damaged["orders"].iloc[broken_fk_index]["order_id"])
    damaged["orders"].loc[broken_fk_index, "customer_id"] = 9_999_999
    issues.append(
        _issue(
            "orders",
            broken_order_id,
            "customer_id",
            "broken_foreign_key",
            "foreign_key",
            "Customer reference does not exist.",
        )
    )

    chronology_order_id = int(damaged["orders"].iloc[chronology_index]["order_id"])
    pickup = damaged["orders"].iloc[chronology_index]["requested_pickup_at"]
    damaged["orders"].loc[chronology_index, "promised_delivery_at"] = (
        pickup - pd.Timedelta(hours=1)
    )
    issues.append(
        _issue(
            "orders",
            chronology_order_id,
            "promised_delivery_at",
            "chronology_violation",
            "timestamp_order",
            "Promised delivery precedes requested pickup.",
        )
    )

    driver_index = int(rng.integers(0, len(damaged["drivers"])))
    driver_id = int(damaged["drivers"].iloc[driver_index]["driver_id"])
    damaged["drivers"].loc[driver_index, "license_class"] = "unknown_class"
    issues.append(
        _issue(
            "drivers",
            driver_id,
            "license_class",
            "unknown_category",
            "accepted_values",
            "License class is outside the documented category set.",
        )
    )

    delivery_index = int(rng.integers(0, len(damaged["deliveries"])))
    delivery_id = int(damaged["deliveries"].iloc[delivery_index]["delivery_id"])
    damaged["deliveries"].loc[delivery_index, "fuel_cost"] = 99_999_999.99
    issues.append(
        _issue(
            "deliveries",
            delivery_id,
            "fuel_cost",
            "cost_outlier",
            "reasonable_range",
            "Fuel cost is an artificial extreme outlier.",
        )
    )

    overload_order_id = int(damaged["orders"].iloc[overload_index]["order_id"])
    delivery = (
        damaged["deliveries"]
        .loc[damaged["deliveries"]["order_id"] == overload_order_id]
        .iloc[0]
    )
    vehicle_id = int(delivery["vehicle_id"])
    capacity = float(
        damaged["vehicles"]
        .loc[damaged["vehicles"]["vehicle_id"] == vehicle_id, "capacity_kg"]
        .iloc[0]
    )
    damaged["orders"].loc[overload_index, "cargo_weight_kg"] = round(capacity * 1.8, 2)
    issues.append(
        _issue(
            "orders",
            overload_order_id,
            "cargo_weight_kg",
            "artificial_overload",
            "capacity_constraint",
            "Artificial overload is distinct from operational overloads.",
        )
    )

    return damaged, pd.DataFrame(issues, columns=MANIFEST_COLUMNS)


def _issue(
    table_name: str,
    record_id: int,
    field_name: str,
    issue_type: str,
    expected_detection: str,
    description: str,
) -> dict[str, object]:
    return {
        "table_name": table_name,
        "record_id": record_id,
        "field_name": field_name,
        "issue_type": issue_type,
        "expected_detection": expected_detection,
        "description": description,
    }
