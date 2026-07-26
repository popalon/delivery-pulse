"""Atomic DuckDB warehouse orchestration."""

from __future__ import annotations

import os
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import duckdb

from delivery_pulse.paths import get_project_paths
from delivery_pulse.quality import QualityRunError, run_quality
from delivery_pulse.quality.models import QualityStatus
from delivery_pulse.warehouse.connection import connect_database
from delivery_pulse.warehouse.loader import (
    WarehouseLoadError,
    insert_warehouse_metadata,
    load_source_tables,
    read_source_metadata,
)
from delivery_pulse.warehouse.models import (
    BuildConfig,
    BuildResult,
    ValidationReport,
    WarehouseInfo,
)
from delivery_pulse.warehouse.sql_runner import (
    SqlExecutionError,
    execute_sql_directory,
    query_sql_file,
)
from delivery_pulse.warehouse.validation import MARTS, validate_connection


class WarehouseError(RuntimeError):
    """Base error for warehouse commands."""


class ExistingWarehouseError(WarehouseError):
    """Raised when a build would overwrite an existing database."""


class WarehouseQualityError(WarehouseError):
    """Raised when source data fails the mandatory quality gate."""


class WarehouseValidationError(WarehouseError):
    """Raised when a newly built warehouse fails validation."""


def _cleanup_build_files(path: Path) -> None:
    for candidate in (path, Path(f"{path}.wal")):
        if candidate.is_file():
            candidate.unlink()


def _mart_counts(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    return {
        mart: int(connection.execute(f'SELECT COUNT(*) FROM "{mart}"').fetchone()[0])
        for mart in MARTS
    }


def build_warehouse(config: BuildConfig) -> BuildResult:
    """Build and validate a warehouse atomically at the requested path."""
    started = time.perf_counter()
    input_dir = config.input_dir.resolve()
    database = config.database.resolve()
    if database.exists() and not config.force:
        raise ExistingWarehouseError(
            f"database already exists: {database}; use --force to replace it"
        )
    if input_dir == database or database.is_dir():
        raise WarehouseError("database must be a file path outside the input directory")

    quality_status = "skipped"
    if not config.skip_quality_check:
        try:
            quality_report, _, _ = run_quality(input_dir)
        except QualityRunError as error:
            raise WarehouseError(f"quality check could not start: {error}") from error
        quality_status = quality_report.status.value
        if quality_report.status is QualityStatus.FAILED:
            raise WarehouseQualityError(
                "source data failed quality checks: "
                f"critical={quality_report.critical_count}, "
                f"error={quality_report.error_count}"
            )

    loaded = read_source_metadata(input_dir)
    sql_root = (config.sql_dir or get_project_paths().sql).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    temporary = database.with_name(f".{database.name}.building")
    _cleanup_build_files(temporary)
    connection: duckdb.DuckDBPyConnection | None = None
    try:
        connection = connect_database(temporary)
        connection.execute("BEGIN TRANSACTION")
        execute_sql_directory(connection, sql_root / "ddl")
        source_counts = load_source_tables(connection, input_dir, loaded)
        execute_sql_directory(connection, sql_root / "marts")
        insert_warehouse_metadata(connection, input_dir, loaded, source_counts)
        validation = validate_connection(connection, temporary)
        if not validation.passed:
            messages = "; ".join(check.message for check in validation.failures)
            raise WarehouseValidationError(messages)
        mart_counts = _mart_counts(connection)
        connection.execute("COMMIT")
        connection.close()
        connection = None
        os.replace(temporary, database)
    except (
        duckdb.Error,
        OSError,
        SqlExecutionError,
        WarehouseLoadError,
        WarehouseValidationError,
    ) as error:
        if connection is not None:
            with suppress(duckdb.Error):
                connection.execute("ROLLBACK")
            connection.close()
        _cleanup_build_files(temporary)
        if isinstance(error, WarehouseError):
            raise
        raise WarehouseError(f"warehouse build failed: {error}") from error
    return BuildResult(
        database=database,
        source_row_counts=source_counts,
        mart_row_counts=mart_counts,
        quality_status=quality_status,
        validation=ValidationReport(database, validation.checks),
        elapsed_seconds=time.perf_counter() - started,
    )


def validate_warehouse(database: Path) -> ValidationReport:
    """Validate an existing warehouse read-only."""
    target = database.resolve()
    if not target.is_file():
        raise WarehouseError(f"database does not exist: {target}")
    try:
        connection = connect_database(target, read_only=True)
        report = validate_connection(connection, target)
        connection.close()
        return report
    except duckdb.Error as error:
        raise WarehouseError(f"warehouse validation failed to run: {error}") from error


def get_warehouse_info(database: Path) -> WarehouseInfo:
    """Return object counts and metadata for an existing warehouse."""
    target = database.resolve()
    if not target.is_file():
        raise WarehouseError(f"database does not exist: {target}")
    try:
        connection = connect_database(target, read_only=True)
        counts = {
            str(name): int(count)
            for name, count in connection.execute(
                """
                SELECT table_name, estimated_size
                FROM duckdb_tables()
                WHERE schema_name = 'main'
                ORDER BY table_name
                """
            ).fetchall()
        }
        metadata = connection.execute(
            """
            SELECT project_version, generator_version, profile,
                   warehouse_schema_version, loaded_at
            FROM warehouse_metadata
            """
        ).fetchone()
        connection.close()
    except duckdb.Error as error:
        raise WarehouseError(f"warehouse info failed: {error}") from error
    return {
        "database": str(target),
        "size_bytes": target.stat().st_size,
        "table_row_counts": counts,
        "project_version": metadata[0],
        "generator_version": metadata[1],
        "profile": metadata[2],
        "warehouse_schema_version": metadata[3],
        "loaded_at": str(metadata[4]),
    }


def get_baseline_metrics(database: Path, sql_dir: Path | None = None) -> dict[str, Any]:
    """Execute the versioned baseline query against an existing warehouse."""
    target = database.resolve()
    if not target.is_file():
        raise WarehouseError(f"database does not exist: {target}")
    sql_root = (sql_dir or get_project_paths().sql).resolve()
    connection = connect_database(target, read_only=True)
    try:
        return query_sql_file(
            connection,
            sql_root / "analysis" / "001_baseline_metrics.sql",
        )
    except (duckdb.Error, SqlExecutionError) as error:
        raise WarehouseError(f"baseline query failed: {error}") from error
    finally:
        connection.close()
