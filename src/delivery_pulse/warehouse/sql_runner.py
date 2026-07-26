"""Deterministic execution of versioned SQL files."""

from __future__ import annotations

from pathlib import Path

import duckdb

from delivery_pulse.config import CONFIG


class SqlExecutionError(RuntimeError):
    """Raised when a versioned SQL file cannot be executed."""


def sql_files(directory: Path) -> tuple[Path, ...]:
    """Return SQL files in deterministic lexical order."""
    if not directory.is_dir():
        raise SqlExecutionError(f"SQL directory does not exist: {directory}")
    files = tuple(sorted(directory.glob("*.sql")))
    if not files:
        raise SqlExecutionError(f"no SQL files found in: {directory}")
    return files


def execute_sql_file(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
) -> None:
    """Execute one UTF-8 SQL file."""
    try:
        statement = path.read_text(encoding=CONFIG.encoding)
        connection.execute(statement)
    except (OSError, duckdb.Error) as error:
        raise SqlExecutionError(f"failed to execute {path.name}: {error}") from error


def execute_sql_directory(
    connection: duckdb.DuckDBPyConnection,
    directory: Path,
) -> None:
    """Execute every SQL file in a directory in lexical order."""
    for path in sql_files(directory):
        execute_sql_file(connection, path)


def query_sql_file(
    connection: duckdb.DuckDBPyConnection,
    path: Path,
) -> dict[str, object]:
    """Execute a single-row query and return a column mapping."""
    try:
        cursor = connection.execute(path.read_text(encoding=CONFIG.encoding))
        row = cursor.fetchone()
    except (OSError, duckdb.Error) as error:
        raise SqlExecutionError(f"failed to query {path.name}: {error}") from error
    if row is None:
        raise SqlExecutionError(f"query returned no rows: {path.name}")
    columns = [description[0] for description in cursor.description]
    return dict(zip(columns, row, strict=True))
