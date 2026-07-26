"""Presence, schema, parsing, and metadata checks."""

from __future__ import annotations

import pandas as pd

from delivery_pulse.config import CONFIG
from delivery_pulse.quality.contracts import COLUMN_TYPES, TABLE_COLUMNS
from delivery_pulse.quality.loader import LoadedDataset
from delivery_pulse.quality.models import CheckResult, QualityIssue, Severity


def _issue(
    check_id: str,
    severity: Severity,
    table: str,
    column: str | None,
    issue_type: str,
    message: str,
    affected: int,
    samples: list[str],
    hint: str,
) -> QualityIssue:
    return QualityIssue(
        check_id,
        severity,
        table,
        column,
        None,
        issue_type,
        message,
        affected,
        samples,
        hint,
    )


def _coerce_boolean(values: pd.Series) -> tuple[pd.Series, pd.Series]:
    normalized = values.astype("string").str.lower()
    mapping = {"true": True, "false": False, "1": True, "0": False}
    converted = normalized.map(mapping).astype("boolean")
    invalid = values.notna() & converted.isna()
    return converted, invalid


def _coerce_column(values: pd.Series, kind: str) -> tuple[pd.Series, pd.Series]:
    if kind == "integer":
        numeric = pd.to_numeric(values, errors="coerce")
        invalid = values.notna() & (
            numeric.isna() | ((numeric % 1 != 0) & numeric.notna())
        )
        return numeric.astype("Int64"), invalid
    if kind == "number":
        converted = pd.to_numeric(values, errors="coerce")
    elif kind == "date":
        converted = pd.to_datetime(values, errors="coerce").dt.date
    elif kind == "datetime":
        converted = pd.to_datetime(values, errors="coerce", utc=True)
    elif kind == "boolean":
        return _coerce_boolean(values)
    else:
        converted = values.astype("string")
    invalid = values.notna() & pd.isna(converted)
    return converted, invalid


def validate_and_coerce(
    loaded: LoadedDataset,
    max_samples: int,
) -> tuple[dict[str, pd.DataFrame], CheckResult]:
    """Validate file schemas and return typed copies for business checks."""
    result = CheckResult()
    typed: dict[str, pd.DataFrame] = {}
    for table_name, expected in TABLE_COLUMNS.items():
        presence_id = f"schema.table_present.{table_name}"
        result.checks.add(presence_id)
        if table_name not in loaded.tables:
            result.issues.append(
                _issue(
                    presence_id,
                    Severity.CRITICAL,
                    table_name,
                    None,
                    "missing_table",
                    f"Required table {table_name}.csv is absent.",
                    1,
                    [],
                    "Regenerate or restore the required raw table.",
                )
            )
            continue
        raw = loaded.tables[table_name]
        result.checks.add(f"schema.non_empty.{table_name}")
        if raw.empty:
            result.issues.append(
                _issue(
                    f"schema.non_empty.{table_name}",
                    Severity.CRITICAL,
                    table_name,
                    None,
                    "empty_table",
                    "Required table contains no rows.",
                    0,
                    [],
                    "Regenerate the dataset and investigate upstream filtering.",
                )
            )
        missing = [column for column in expected if column not in raw.columns]
        extra = [column for column in raw.columns if column not in expected]
        result.checks.add(f"schema.columns.{table_name}")
        for column in missing:
            result.issues.append(
                _issue(
                    f"schema.columns.{table_name}",
                    Severity.CRITICAL,
                    table_name,
                    column,
                    "missing_column",
                    f"Required column {column} is absent.",
                    len(raw),
                    [],
                    "Restore the documented schema before analysis.",
                )
            )
        if extra:
            result.issues.append(
                _issue(
                    f"schema.columns.{table_name}",
                    Severity.WARNING,
                    table_name,
                    None,
                    "unknown_columns",
                    "Columns outside the current contract were found.",
                    len(raw),
                    extra[:max_samples],
                    "Confirm schema evolution and update the contract explicitly.",
                )
            )
        frame = raw.copy()
        for column in expected:
            if column not in frame:
                continue
            check_id = f"schema.parse.{table_name}.{column}"
            result.checks.add(check_id)
            converted, invalid = _coerce_column(
                frame[column], COLUMN_TYPES[table_name][column]
            )
            if invalid.any():
                samples = (
                    frame.loc[invalid, column].astype(str).head(max_samples).tolist()
                )
                result.issues.append(
                    _issue(
                        check_id,
                        Severity.ERROR,
                        table_name,
                        column,
                        "type_parse_error",
                        f"{int(invalid.sum())} values cannot be parsed as "
                        f"{COLUMN_TYPES[table_name][column]}.",
                        int(invalid.sum()),
                        samples,
                        "Quarantine malformed rows and correct the upstream export.",
                    )
                )
            frame[column] = converted
        typed[table_name] = frame

    _check_metadata(loaded, result, max_samples)
    return typed, result


def _check_metadata(
    loaded: LoadedDataset,
    result: CheckResult,
    max_samples: int,
) -> None:
    check_id = "schema.metadata"
    result.checks.add(check_id)
    if loaded.metadata is None:
        result.issues.append(
            _issue(
                check_id,
                Severity.ERROR,
                "metadata",
                None,
                "missing_metadata",
                "metadata.json was not found next to the raw dataset.",
                1,
                [],
                "Restore generation metadata before certifying the dataset.",
            )
        )
        return
    row_counts = loaded.metadata.get("row_counts")
    if not isinstance(row_counts, dict):
        result.issues.append(
            _issue(
                check_id,
                Severity.ERROR,
                "metadata",
                "row_counts",
                "invalid_metadata",
                "metadata row_counts is missing or invalid.",
                1,
                [],
                "Regenerate metadata from the same dataset.",
            )
        )
    else:
        mismatches = [
            f"{name}: metadata={row_counts.get(name)!r}, actual={len(table)}"
            for name, table in loaded.tables.items()
            if row_counts.get(name) != len(table)
        ]
        if mismatches:
            result.issues.append(
                _issue(
                    check_id,
                    Severity.ERROR,
                    "metadata",
                    "row_counts",
                    "metadata_row_count_mismatch",
                    "Metadata row counts do not match CSV files.",
                    len(mismatches),
                    mismatches[:max_samples],
                    "Regenerate metadata; do not edit raw CSV files in place.",
                )
            )
    parameters = loaded.metadata.get("parameters")
    currency = parameters.get("currency_code") if isinstance(parameters, dict) else None
    if currency != CONFIG.currency_code:
        result.issues.append(
            _issue(
                check_id,
                Severity.ERROR,
                "metadata",
                "currency_code",
                "unknown_category",
                f"First-release currency must be {CONFIG.currency_code}.",
                1,
                [str(currency)],
                "Use a dataset generated with the documented RUB contract.",
            )
        )
