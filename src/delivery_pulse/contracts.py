"""Shared raw-data contracts for generation and quality validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ColumnKind = Literal["boolean", "date", "datetime", "integer", "number", "string"]


@dataclass(frozen=True, slots=True)
class ForeignKey:
    """A child-to-parent relationship in the raw data model."""

    child_table: str
    child_column: str
    parent_table: str
    parent_column: str


TABLE_COLUMNS: dict[str, list[str]] = {
    "customers": [
        "customer_id",
        "customer_name",
        "customer_segment",
        "industry",
        "contract_start_date",
        "contract_end_date",
        "default_sla_hours",
        "payment_terms_days",
        "is_active",
    ],
    "routes": [
        "route_id",
        "route_code",
        "origin_region",
        "destination_region",
        "standard_distance_km",
        "standard_transit_hours",
        "route_class",
        "is_active",
    ],
    "drivers": [
        "driver_id",
        "driver_code",
        "hire_date",
        "experience_years",
        "license_class",
        "home_region",
        "employment_status",
    ],
    "vehicles": [
        "vehicle_id",
        "vehicle_code",
        "vehicle_type",
        "capacity_kg",
        "manufacture_year",
        "fuel_type",
        "fuel_consumption_l_100km",
        "odometer_at_observation_start_km",
        "home_region",
        "service_status",
    ],
    "orders": [
        "order_id",
        "customer_id",
        "route_id",
        "created_at",
        "requested_pickup_at",
        "promised_delivery_at",
        "cargo_type",
        "cargo_weight_kg",
        "distance_planned_km",
        "quoted_revenue",
        "priority",
        "order_status",
    ],
    "deliveries": [
        "delivery_id",
        "order_id",
        "driver_id",
        "vehicle_id",
        "planned_departure_at",
        "actual_departure_at",
        "actual_delivery_at",
        "distance_actual_km",
        "delivery_status",
        "fuel_cost",
        "driver_cost",
        "toll_cost",
        "maintenance_allocated_cost",
        "other_cost",
        "penalty_amount",
    ],
    "route_events": [
        "event_id",
        "delivery_id",
        "event_at",
        "event_end_at",
        "event_type",
        "severity",
        "delay_minutes",
        "extra_cost",
        "region",
        "notes_code",
    ],
    "maintenance": [
        "maintenance_id",
        "vehicle_id",
        "maintenance_type",
        "started_at",
        "completed_at",
        "odometer_km",
        "cost_amount",
        "downtime_hours",
        "issue_category",
        "maintenance_status",
    ],
}

PRIMARY_KEYS = {table: columns[0] for table, columns in TABLE_COLUMNS.items()}

FOREIGN_KEYS = (
    ForeignKey("orders", "customer_id", "customers", "customer_id"),
    ForeignKey("orders", "route_id", "routes", "route_id"),
    ForeignKey("deliveries", "order_id", "orders", "order_id"),
    ForeignKey("deliveries", "driver_id", "drivers", "driver_id"),
    ForeignKey("deliveries", "vehicle_id", "vehicles", "vehicle_id"),
    ForeignKey("route_events", "delivery_id", "deliveries", "delivery_id"),
    ForeignKey("maintenance", "vehicle_id", "vehicles", "vehicle_id"),
)

NULLABLE_COLUMNS: dict[str, set[str]] = {
    "customers": {"contract_end_date"},
    "routes": set(),
    "drivers": set(),
    "vehicles": set(),
    "orders": set(),
    "deliveries": {
        "actual_departure_at",
        "actual_delivery_at",
        "distance_actual_km",
        "fuel_cost",
        "driver_cost",
        "toll_cost",
        "maintenance_allocated_cost",
        "other_cost",
        "penalty_amount",
    },
    "route_events": {"event_end_at", "notes_code"},
    "maintenance": {
        "completed_at",
        "downtime_hours",
        "issue_category",
    },
}

INTEGER_COLUMNS = {
    "customer_id",
    "default_sla_hours",
    "payment_terms_days",
    "route_id",
    "driver_id",
    "vehicle_id",
    "manufacture_year",
    "order_id",
    "delivery_id",
    "event_id",
    "delay_minutes",
    "maintenance_id",
}
NUMBER_COLUMNS = {
    "standard_distance_km",
    "standard_transit_hours",
    "experience_years",
    "capacity_kg",
    "fuel_consumption_l_100km",
    "odometer_at_observation_start_km",
    "cargo_weight_kg",
    "distance_planned_km",
    "quoted_revenue",
    "distance_actual_km",
    "fuel_cost",
    "driver_cost",
    "toll_cost",
    "maintenance_allocated_cost",
    "other_cost",
    "penalty_amount",
    "extra_cost",
    "odometer_km",
    "cost_amount",
    "downtime_hours",
}
DATE_COLUMNS = {"contract_start_date", "contract_end_date", "hire_date"}
DATETIME_COLUMNS = {
    "created_at",
    "requested_pickup_at",
    "promised_delivery_at",
    "planned_departure_at",
    "actual_departure_at",
    "actual_delivery_at",
    "event_at",
    "event_end_at",
    "started_at",
    "completed_at",
}
BOOLEAN_COLUMNS = {"is_active"}


def _kind(column: str) -> ColumnKind:
    if column in BOOLEAN_COLUMNS:
        return "boolean"
    if column in DATE_COLUMNS:
        return "date"
    if column in DATETIME_COLUMNS:
        return "datetime"
    if column in INTEGER_COLUMNS:
        return "integer"
    if column in NUMBER_COLUMNS:
        return "number"
    return "string"


COLUMN_TYPES: dict[str, dict[str, ColumnKind]] = {
    table: {column: _kind(column) for column in columns}
    for table, columns in TABLE_COLUMNS.items()
}

ALLOWED_CATEGORIES: dict[tuple[str, str], frozenset[str]] = {
    ("customers", "customer_segment"): frozenset({"small", "medium", "enterprise"}),
    ("routes", "route_class"): frozenset({"regional", "interregional", "long_haul"}),
    ("drivers", "license_class"): frozenset({"b", "c", "ce"}),
    ("drivers", "employment_status"): frozenset({"active", "leave", "terminated"}),
    ("vehicles", "vehicle_type"): frozenset({"van", "truck", "refrigerated_truck"}),
    ("vehicles", "fuel_type"): frozenset({"diesel", "petrol", "electric", "hybrid"}),
    ("vehicles", "service_status"): frozenset({"active", "maintenance", "retired"}),
    ("orders", "cargo_type"): frozenset({"general", "fragile", "refrigerated"}),
    ("orders", "priority"): frozenset({"standard", "express"}),
    ("orders", "order_status"): frozenset(
        {"created", "assigned", "completed", "cancelled"}
    ),
    ("deliveries", "delivery_status"): frozenset(
        {"planned", "in_transit", "delivered", "failed", "cancelled"}
    ),
    ("route_events", "event_type"): frozenset(
        {
            "traffic",
            "weather",
            "loading_delay",
            "unloading_delay",
            "breakdown",
            "route_deviation",
        }
    ),
    ("route_events", "severity"): frozenset({"low", "medium", "high"}),
    ("maintenance", "maintenance_type"): frozenset(
        {"scheduled", "repair", "inspection"}
    ),
    ("maintenance", "maintenance_status"): frozenset(
        {"scheduled", "in_progress", "completed", "cancelled"}
    ),
}

BUSINESS_KEYS: dict[str, tuple[tuple[str, ...], ...]] = {
    "customers": (("customer_name",),),
    "routes": (
        ("route_code",),
        ("origin_region", "destination_region", "route_class"),
    ),
    "drivers": (("driver_code",),),
    "vehicles": (("vehicle_code",),),
    "deliveries": (("order_id",),),
    "route_events": (("delivery_id", "event_at", "event_type"),),
}

FINANCIAL_MARGIN_COLUMNS: tuple[tuple[str, str], ...] = (
    ("orders", "quoted_revenue"),
    ("deliveries", "penalty_amount"),
    ("deliveries", "fuel_cost"),
    ("deliveries", "driver_cost"),
    ("deliveries", "toll_cost"),
    ("deliveries", "maintenance_allocated_cost"),
    ("deliveries", "other_cost"),
)

MAX_OPERATIONAL_OVERLOAD_RATIO = 1.05

# Wide sanity ceilings distinguish impossible/implausible values from ordinary tails.
UPPER_BOUNDS: dict[tuple[str, str], float] = {
    ("routes", "standard_distance_km"): 15_000,
    ("routes", "standard_transit_hours"): 500,
    ("vehicles", "capacity_kg"): 100_000,
    ("vehicles", "fuel_consumption_l_100km"): 200,
    ("vehicles", "odometer_at_observation_start_km"): 5_000_000,
    ("orders", "cargo_weight_kg"): 100_000,
    ("orders", "distance_planned_km"): 15_000,
    ("orders", "quoted_revenue"): 10_000_000,
    ("deliveries", "distance_actual_km"): 20_000,
    ("deliveries", "fuel_cost"): 5_000_000,
    ("deliveries", "driver_cost"): 5_000_000,
    ("deliveries", "toll_cost"): 5_000_000,
    ("deliveries", "maintenance_allocated_cost"): 5_000_000,
    ("deliveries", "other_cost"): 5_000_000,
    ("deliveries", "penalty_amount"): 10_000_000,
    ("route_events", "delay_minutes"): 30 * 24 * 60,
    ("route_events", "extra_cost"): 5_000_000,
    ("maintenance", "odometer_km"): 5_000_000,
    ("maintenance", "cost_amount"): 10_000_000,
    ("maintenance", "downtime_hours"): 10_000,
}

DUCKDB_COLUMN_TYPES: dict[str, dict[str, str]] = {
    "customers": {
        "customer_id": "BIGINT",
        "customer_name": "VARCHAR",
        "customer_segment": "VARCHAR",
        "industry": "VARCHAR",
        "contract_start_date": "DATE",
        "contract_end_date": "DATE",
        "default_sla_hours": "SMALLINT",
        "payment_terms_days": "SMALLINT",
        "is_active": "BOOLEAN",
    },
    "routes": {
        "route_id": "BIGINT",
        "route_code": "VARCHAR",
        "origin_region": "VARCHAR",
        "destination_region": "VARCHAR",
        "standard_distance_km": "DECIMAL(10, 2)",
        "standard_transit_hours": "DECIMAL(8, 2)",
        "route_class": "VARCHAR",
        "is_active": "BOOLEAN",
    },
    "drivers": {
        "driver_id": "BIGINT",
        "driver_code": "VARCHAR",
        "hire_date": "DATE",
        "experience_years": "DECIMAL(4, 1)",
        "license_class": "VARCHAR",
        "home_region": "VARCHAR",
        "employment_status": "VARCHAR",
    },
    "vehicles": {
        "vehicle_id": "BIGINT",
        "vehicle_code": "VARCHAR",
        "vehicle_type": "VARCHAR",
        "capacity_kg": "DECIMAL(10, 2)",
        "manufacture_year": "SMALLINT",
        "fuel_type": "VARCHAR",
        "fuel_consumption_l_100km": "DECIMAL(6, 2)",
        "odometer_at_observation_start_km": "DECIMAL(12, 2)",
        "home_region": "VARCHAR",
        "service_status": "VARCHAR",
    },
    "orders": {
        "order_id": "BIGINT",
        "customer_id": "BIGINT",
        "route_id": "BIGINT",
        "created_at": "TIMESTAMP",
        "requested_pickup_at": "TIMESTAMP",
        "promised_delivery_at": "TIMESTAMP",
        "cargo_type": "VARCHAR",
        "cargo_weight_kg": "DECIMAL(10, 2)",
        "distance_planned_km": "DECIMAL(10, 2)",
        "quoted_revenue": "DECIMAL(14, 2)",
        "priority": "VARCHAR",
        "order_status": "VARCHAR",
    },
    "deliveries": {
        "delivery_id": "BIGINT",
        "order_id": "BIGINT",
        "driver_id": "BIGINT",
        "vehicle_id": "BIGINT",
        "planned_departure_at": "TIMESTAMP",
        "actual_departure_at": "TIMESTAMP",
        "actual_delivery_at": "TIMESTAMP",
        "distance_actual_km": "DECIMAL(10, 2)",
        "delivery_status": "VARCHAR",
        "fuel_cost": "DECIMAL(14, 2)",
        "driver_cost": "DECIMAL(14, 2)",
        "toll_cost": "DECIMAL(14, 2)",
        "maintenance_allocated_cost": "DECIMAL(14, 2)",
        "other_cost": "DECIMAL(14, 2)",
        "penalty_amount": "DECIMAL(14, 2)",
    },
    "route_events": {
        "event_id": "BIGINT",
        "delivery_id": "BIGINT",
        "event_at": "TIMESTAMP",
        "event_end_at": "TIMESTAMP",
        "event_type": "VARCHAR",
        "severity": "VARCHAR",
        "delay_minutes": "INTEGER",
        "extra_cost": "DECIMAL(14, 2)",
        "region": "VARCHAR",
        "notes_code": "VARCHAR",
    },
    "maintenance": {
        "maintenance_id": "BIGINT",
        "vehicle_id": "BIGINT",
        "maintenance_type": "VARCHAR",
        "started_at": "TIMESTAMP",
        "completed_at": "TIMESTAMP",
        "odometer_km": "DECIMAL(12, 2)",
        "cost_amount": "DECIMAL(14, 2)",
        "downtime_hours": "DECIMAL(10, 2)",
        "issue_category": "VARCHAR",
        "maintenance_status": "VARCHAR",
    },
}
