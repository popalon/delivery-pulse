"""Read-only warehouse access and pre-analysis validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from delivery_pulse.warehouse import (
    WarehouseError,
    get_baseline_metrics,
    validate_warehouse,
)
from delivery_pulse.warehouse.connection import connect_database
from delivery_pulse.warehouse.validation import MARTS

ALLOWED_ANALYSIS_TABLES = frozenset(
    {
        *MARTS,
        "customers",
        "routes",
        "vehicles",
        "warehouse_metadata",
        # Point-detail exception: event flags and per-type extra costs only.
        "route_events",
    }
)


class AnalysisLoadError(RuntimeError):
    """Raised when a warehouse cannot be safely analyzed."""


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Validated read-only warehouse metadata and baseline."""

    database: Path
    baseline: dict[str, Any]
    metadata: dict[str, Any]
    row_counts: dict[str, int]


def open_read_only(database: Path) -> duckdb.DuckDBPyConnection:
    """Open the analysis database without write access."""
    target = database.resolve()
    if not target.is_file():
        raise AnalysisLoadError(f"database does not exist: {target}")
    try:
        return connect_database(target, read_only=True)
    except duckdb.Error as error:
        raise AnalysisLoadError(f"cannot open warehouse read-only: {error}") from error


def query_frame(
    connection: duckdb.DuckDBPyConnection,
    query: str,
    parameters: list[object] | None = None,
) -> pd.DataFrame:
    """Execute a bounded analytical query and return a DataFrame."""
    try:
        cursor = connection.execute(query, parameters or [])
        return cursor.fetchdf()
    except duckdb.Error as error:
        raise AnalysisLoadError(f"analysis query failed: {error}") from error


def load_context(database: Path) -> AnalysisContext:
    """Validate the warehouse and load baseline, metadata, and mart counts."""
    target = database.resolve()
    try:
        validation = validate_warehouse(target)
    except WarehouseError as error:
        raise AnalysisLoadError(str(error)) from error
    if not validation.passed:
        failures = "; ".join(check.message for check in validation.failures)
        raise AnalysisLoadError(f"warehouse validation failed: {failures}")
    try:
        baseline = get_baseline_metrics(target)
    except WarehouseError as error:
        raise AnalysisLoadError(str(error)) from error
    connection = open_read_only(target)
    try:
        metadata_row = connection.execute(
            """
            SELECT project_version, generator_version, seed, profile,
                   start_date, months, loaded_at, warehouse_schema_version
            FROM warehouse_metadata
            """
        ).fetchone()
        if metadata_row is None:
            raise AnalysisLoadError("warehouse_metadata is empty")
        columns = [
            "project_version",
            "generator_version",
            "seed",
            "profile",
            "start_date",
            "months",
            "loaded_at",
            "warehouse_schema_version",
        ]
        metadata = dict(zip(columns, metadata_row, strict=True))
        row_counts = {
            mart: int(
                connection.execute(f'SELECT COUNT(*) FROM "{mart}"').fetchone()[0]
            )
            for mart in MARTS
        }
    finally:
        connection.close()
    return AnalysisContext(target, baseline, metadata, row_counts)
