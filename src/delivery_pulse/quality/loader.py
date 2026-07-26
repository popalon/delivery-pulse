"""Read raw CSV files without modifying the input dataset."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from delivery_pulse.config import CONFIG
from delivery_pulse.quality.contracts import TABLE_COLUMNS


class QualityLoadError(RuntimeError):
    """Raised when a quality run cannot start safely."""


@dataclass(frozen=True, slots=True)
class LoadedDataset:
    """Raw tables plus optional generation metadata."""

    tables: dict[str, pd.DataFrame]
    metadata: dict[str, Any] | None
    metadata_path: Path | None


def _find_metadata(input_dir: Path) -> Path | None:
    candidates = (
        input_dir / "metadata.json",
        input_dir.parent / "metadata" / "metadata.json",
    )
    return next((path for path in candidates if path.is_file()), None)


def load_dataset(input_dir: Path) -> LoadedDataset:
    """Load all present expected tables and metadata; never read the manifest."""
    source = input_dir.resolve()
    if not source.is_dir():
        raise QualityLoadError(f"input directory does not exist: {source}")

    tables: dict[str, pd.DataFrame] = {}
    for table_name in TABLE_COLUMNS:
        path = source / f"{table_name}.csv"
        if path.is_file():
            try:
                tables[table_name] = pd.read_csv(
                    path,
                    dtype=str,
                    keep_default_na=True,
                    encoding=CONFIG.encoding,
                )
            except (OSError, UnicodeError, pd.errors.ParserError) as error:
                raise QualityLoadError(f"cannot read {path.name}: {error}") from error

    metadata_path = _find_metadata(source)
    metadata: dict[str, Any] | None = None
    if metadata_path is not None:
        try:
            parsed = json.loads(metadata_path.read_text(encoding=CONFIG.encoding))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise QualityLoadError(f"cannot read metadata.json: {error}") from error
        if not isinstance(parsed, dict):
            raise QualityLoadError("metadata.json must contain a JSON object")
        metadata = parsed
    return LoadedDataset(tables, metadata, metadata_path)
