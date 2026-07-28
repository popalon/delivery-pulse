"""Transactional staging publication to PostgreSQL."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from delivery_pulse import __version__
from delivery_pulse.publish.mappings import (
    EXCLUDED_COLUMNS,
    PUBLISHED_TABLES,
    postgres_type,
)


def database_sha256(path: Path) -> str:
    """Hash the immutable source database in bounded chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def schema_exists(connection: Any, schema: str) -> bool:
    """Check schema existence without mutating PostgreSQL."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.schemata "
            "WHERE schema_name = %s)",
            (schema,),
        )
        return bool(cursor.fetchone()[0])


def _columns(
    source: duckdb.DuckDBPyConnection, table: str
) -> list[tuple[str, str, bool]]:
    rows = source.execute(f'DESCRIBE "{table}"').fetchall()
    excluded = EXCLUDED_COLUMNS.get(table, frozenset())
    return [
        (str(row[0]), postgres_type(str(row[1])), str(row[2]).upper() == "YES")
        for row in rows
        if str(row[0]) not in excluded
    ]


def create_and_load_table(
    source: duckdb.DuckDBPyConnection,
    target: Any,
    schema: str,
    table: str,
) -> int:
    """Create one explicitly typed target table and bulk-copy rows."""
    columns = _columns(source, table)
    definitions = ", ".join(
        f'"{name}" {data_type}{" NULL" if nullable else " NOT NULL"}'
        for name, data_type, nullable in columns
    )
    names = ", ".join(f'"{name}"' for name, _, _ in columns)
    with target.cursor() as cursor:
        cursor.execute(f'CREATE TABLE "{schema}"."{table}" ({definitions})')
        copy_sql = f'COPY "{schema}"."{table}" ({names}) FROM STDIN'
        with cursor.copy(copy_sql) as copy:
            result = source.execute(f'SELECT {names} FROM "{table}"')
            count = 0
            while rows := result.fetchmany(10_000):
                for row in rows:
                    copy.write_row(row)
                    count += 1
    return count


def create_publish_metadata(
    target: Any,
    schema: str,
    *,
    target_schema: str,
    source_database_hash: str,
    table_counts: dict[str, int],
    publish_mode: str,
    warehouse_schema_version: str,
) -> None:
    """Create a single diagnostic publication metadata row."""
    with target.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE TABLE "{schema}".publish_metadata (
                project_version TEXT NOT NULL,
                warehouse_schema_version TEXT NOT NULL,
                published_at TIMESTAMPTZ NOT NULL,
                source_database_hash TEXT NOT NULL,
                row_counts JSONB NOT NULL,
                publish_mode TEXT NOT NULL,
                target_schema TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            f'INSERT INTO "{schema}".publish_metadata VALUES '
            "(%s, %s, %s, %s, %s::jsonb, %s, %s)",
            (
                __version__,
                warehouse_schema_version,
                datetime.now(UTC),
                source_database_hash,
                json.dumps(table_counts, sort_keys=True),
                publish_mode,
                target_schema,
            ),
        )


def load_staging_schema(
    source: duckdb.DuckDBPyConnection,
    target: Any,
    staging_schema: str,
) -> dict[str, int]:
    """Create and load every approved table in deterministic order."""
    with target.cursor() as cursor:
        cursor.execute(f'CREATE SCHEMA "{staging_schema}"')
    return {
        table: create_and_load_table(source, target, staging_schema, table)
        for table in PUBLISHED_TABLES
    }
