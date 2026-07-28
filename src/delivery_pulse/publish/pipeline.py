"""Validated, transactional DuckDB-to-PostgreSQL publication pipeline."""

from __future__ import annotations

from contextlib import suppress
from time import perf_counter

import duckdb

from delivery_pulse.analysis.loader import AnalysisLoadError, load_context
from delivery_pulse.publish.connection import connect_postgres
from delivery_pulse.publish.models import (
    PublishConfig,
    PublishResult,
)
from delivery_pulse.publish.postgres import (
    create_publish_metadata,
    database_sha256,
    load_staging_schema,
    schema_exists,
)
from delivery_pulse.publish.validation import validate_publication


class PublishError(RuntimeError):
    """Raised when publication cannot complete atomically."""


def _warehouse_schema_version(source: duckdb.DuckDBPyConnection) -> str:
    row = source.execute(
        "SELECT warehouse_schema_version FROM warehouse_metadata"
    ).fetchone()
    if row is None:
        raise PublishError("warehouse_metadata is empty")
    return str(row[0])


def _validate_mode(config: PublishConfig) -> None:
    if config.mode == "replace" and not config.force:
        raise PublishError("replace mode requires --force")


def publish_postgres(config: PublishConfig) -> PublishResult:
    """Publish an immutable validated warehouse through a staging schema."""
    _validate_mode(config)
    started = perf_counter()
    source_path = config.database.resolve()
    try:
        load_context(source_path)
    except AnalysisLoadError as error:
        raise PublishError(str(error)) from error
    before_hash = database_sha256(source_path)
    source: duckdb.DuckDBPyConnection | None = None
    target = None
    try:
        source = duckdb.connect(str(source_path), read_only=True)
        target = connect_postgres(config.postgres)
    except (duckdb.Error, RuntimeError, OSError) as error:
        if source is not None:
            source.close()
        raise PublishError(f"connection failed: {error}") from error
    schema = config.postgres.schema
    staging = f"{schema}__staging"
    backup = f"{schema}__previous"
    try:
        exists = schema_exists(target, schema)
        if config.validate_only:
            if not exists:
                raise PublishError(f'target schema "{schema}" does not exist')
            report = validate_publication(source, target, schema)
            if not report.passed:
                raise PublishError("published tables failed validation")
            counts = {
                check.check_id.removeprefix("row_count."): int(check.target_value)
                for check in report.checks
                if check.check_id.startswith("row_count.")
            }
            return PublishResult(
                schema, config.mode, counts, report, perf_counter() - started, True
            )
        if config.mode == "create" and exists:
            raise PublishError(
                f'target schema "{schema}" already exists; use replace --force'
            )
        with target.transaction():
            if schema_exists(target, staging) or schema_exists(target, backup):
                raise PublishError("staging or previous schema already exists")
            counts = load_staging_schema(source, target, staging)
            create_publish_metadata(
                target,
                staging,
                target_schema=schema,
                source_database_hash=before_hash,
                table_counts=counts,
                publish_mode=config.mode,
                warehouse_schema_version=_warehouse_schema_version(source),
            )
            report = validate_publication(source, target, staging)
            if not report.passed:
                raise PublishError("staging validation failed")
            if database_sha256(source_path) != before_hash:
                raise PublishError("source DuckDB changed during publication")
            with target.cursor() as cursor:
                if exists:
                    cursor.execute(f'ALTER SCHEMA "{schema}" RENAME TO "{backup}"')
                cursor.execute(f'ALTER SCHEMA "{staging}" RENAME TO "{schema}"')
                if exists:
                    cursor.execute(f'DROP SCHEMA "{backup}" CASCADE')
        return PublishResult(
            schema, config.mode, counts, report, perf_counter() - started, False
        )
    except PublishError:
        with suppress(Exception):
            target.rollback()
        raise
    except Exception as error:
        with suppress(Exception):
            target.rollback()
        raise PublishError(f"publication rolled back: {error}") from error
    finally:
        if source is not None:
            source.close()
        if target is not None:
            target.close()
