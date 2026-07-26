"""Explicitly typed loading of expected raw CSV files into DuckDB."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import duckdb

from delivery_pulse import __version__
from delivery_pulse.contracts import DUCKDB_COLUMN_TYPES, TABLE_COLUMNS
from delivery_pulse.quality.loader import LoadedDataset, QualityLoadError, load_dataset

WAREHOUSE_SCHEMA_VERSION = "1"


class WarehouseLoadError(RuntimeError):
    """Raised when raw data cannot be loaded safely."""


def read_source_metadata(input_dir: Path) -> LoadedDataset:
    """Load expected file metadata without accessing the quality manifest."""
    try:
        loaded = load_dataset(input_dir)
    except QualityLoadError as error:
        raise WarehouseLoadError(str(error)) from error
    if loaded.metadata is None:
        raise WarehouseLoadError("metadata.json is required for warehouse loading")
    missing = [name for name in TABLE_COLUMNS if name not in loaded.tables]
    if missing:
        raise WarehouseLoadError(
            "required CSV files are missing: " + ", ".join(missing)
        )
    return loaded


def load_source_tables(
    connection: duckdb.DuckDBPyConnection,
    input_dir: Path,
    loaded: LoadedDataset,
) -> dict[str, int]:
    """Load eight expected CSV files using explicit DuckDB column types."""
    metadata_counts = loaded.metadata.get("row_counts") if loaded.metadata else None
    if not isinstance(metadata_counts, dict):
        raise WarehouseLoadError("metadata row_counts is missing or invalid")
    row_counts: dict[str, int] = {}
    for table_name in TABLE_COLUMNS:
        path = input_dir.resolve() / f"{table_name}.csv"
        try:
            relation = connection.read_csv(
                str(path),
                columns=DUCKDB_COLUMN_TYPES[table_name],
                header=True,
                strict_mode=True,
            )
            relation.insert_into(table_name)
            count = int(
                connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            )
        except (duckdb.Error, OSError, TypeError) as error:
            raise WarehouseLoadError(
                f"failed to load {table_name}.csv: {error}"
            ) from error
        expected = metadata_counts.get(table_name)
        if expected != count:
            raise WarehouseLoadError(
                f"row count mismatch for {table_name}: "
                f"metadata={expected!r}, loaded={count}"
            )
        row_counts[table_name] = count
    return row_counts


def insert_warehouse_metadata(
    connection: duckdb.DuckDBPyConnection,
    input_dir: Path,
    loaded: LoadedDataset,
    row_counts: dict[str, int],
) -> None:
    """Persist one diagnostic metadata row for the completed source load."""
    metadata = cast(dict[str, Any], loaded.metadata)
    parameters = metadata.get("parameters")
    if not isinstance(parameters, dict):
        raise WarehouseLoadError("metadata parameters is missing or invalid")
    values = (
        __version__,
        str(parameters.get("generator_version", "")),
        int(metadata["seed"]),
        str(metadata["profile"]),
        str(metadata["start_date"]),
        int(metadata["months"]),
        datetime.now(UTC).replace(tzinfo=None),
        str(input_dir.resolve()),
        json.dumps(row_counts, sort_keys=True),
        WAREHOUSE_SCHEMA_VERSION,
    )
    try:
        connection.execute(
            """
            INSERT INTO warehouse_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
    except (duckdb.Error, KeyError, TypeError, ValueError) as error:
        raise WarehouseLoadError(f"invalid generation metadata: {error}") from error
