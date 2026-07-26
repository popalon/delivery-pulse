"""DuckDB connection helpers."""

from __future__ import annotations

from pathlib import Path

import duckdb


def connect_database(
    database: Path,
    *,
    read_only: bool = False,
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB database at an explicitly resolved path."""
    return duckdb.connect(str(database.resolve()), read_only=read_only)
