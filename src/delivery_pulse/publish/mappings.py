"""Explicit DuckDB-to-PostgreSQL type mappings and publish table order."""

from __future__ import annotations

PUBLISHED_TABLES = (
    "customers",
    "routes",
    "vehicles",
    "delivery_performance_mart",
    "delivery_financial_mart",
    "route_daily_mart",
    "customer_monthly_mart",
    "vehicle_reliability_mart",
    "warehouse_metadata",
)

DUCKDB_TO_POSTGRES = {
    "BIGINT": "BIGINT",
    "INTEGER": "BIGINT",
    "SMALLINT": "BIGINT",
    "HUGEINT": "NUMERIC",
    "DECIMAL": "NUMERIC",
    "DOUBLE": "DOUBLE PRECISION",
    "FLOAT": "DOUBLE PRECISION",
    "BOOLEAN": "BOOLEAN",
    "DATE": "DATE",
    "TIMESTAMP": "TIMESTAMP",
    "TIMESTAMP WITH TIME ZONE": "TIMESTAMPTZ",
    "VARCHAR": "TEXT",
    "JSON": "JSONB",
}

PRIMARY_KEYS = {
    "customers": ("customer_id",),
    "routes": ("route_id",),
    "vehicles": ("vehicle_id",),
    "delivery_performance_mart": ("delivery_id",),
    "delivery_financial_mart": ("delivery_id",),
    "route_daily_mart": ("route_id", "calendar_date"),
    "customer_monthly_mart": ("customer_id", "calendar_month"),
    "vehicle_reliability_mart": ("vehicle_id", "calendar_month"),
}

# Diagnostic machine paths are deliberately not copied into the BI layer.
EXCLUDED_COLUMNS = {
    "warehouse_metadata": frozenset({"source_directory"}),
}


def postgres_type(duckdb_type: str) -> str:
    """Map a DuckDB type declaration without relying on inference."""
    normalized = duckdb_type.upper()
    if normalized.startswith("DECIMAL("):
        return normalized.replace("DECIMAL", "NUMERIC", 1)
    for prefix, target in DUCKDB_TO_POSTGRES.items():
        if normalized == prefix:
            return target
    raise ValueError(f"unsupported DuckDB type: {duckdb_type}")
