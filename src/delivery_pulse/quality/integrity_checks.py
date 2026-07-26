"""Key, completeness, category, and relationship checks."""

from __future__ import annotations

from typing import cast

import numpy as np
import pandas as pd

from delivery_pulse.quality.contracts import (
    ALLOWED_CATEGORIES,
    BUSINESS_KEYS,
    FOREIGN_KEYS,
    NULLABLE_COLUMNS,
    PRIMARY_KEYS,
)
from delivery_pulse.quality.models import CheckResult, QualityIssue, Severity


def _samples(
    frame: pd.DataFrame,
    mask: pd.Series,
    columns: list[str],
    limit: int,
) -> list[str]:
    return cast(
        list[str],
        frame.loc[mask, columns]
        .head(limit)
        .astype(str)
        .agg(" | ".join, axis=1)
        .tolist(),
    )


def _issue(
    check_id: str,
    severity: Severity,
    table: str,
    column: str | None,
    row_identifier: str | None,
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
        row_identifier,
        issue_type,
        message,
        affected,
        samples,
        hint,
    )


def run_integrity_checks(
    tables: dict[str, pd.DataFrame],
    max_samples: int,
) -> CheckResult:
    """Run primary/foreign key, required-value, and category checks."""
    result = CheckResult()
    for table_name, frame in tables.items():
        primary_key = PRIMARY_KEYS[table_name]
        if primary_key not in frame:
            continue
        _check_primary_key(table_name, frame, primary_key, max_samples, result)
        _check_required(table_name, frame, primary_key, max_samples, result)
        _check_business_keys(table_name, frame, primary_key, max_samples, result)

    for foreign_key in FOREIGN_KEYS:
        check_id = (
            f"integrity.foreign_key.{foreign_key.child_table}."
            f"{foreign_key.child_column}"
        )
        result.checks.add(check_id)
        if (
            foreign_key.child_table not in tables
            or foreign_key.parent_table not in tables
            or foreign_key.child_column not in tables[foreign_key.child_table]
            or foreign_key.parent_column not in tables[foreign_key.parent_table]
        ):
            continue
        child = tables[foreign_key.child_table]
        values = child[foreign_key.child_column]
        valid = set(
            tables[foreign_key.parent_table][foreign_key.parent_column].dropna()
        )
        invalid = values.notna() & ~values.isin(valid)
        if invalid.any():
            pk = PRIMARY_KEYS[foreign_key.child_table]
            result.issues.append(
                _issue(
                    check_id,
                    Severity.ERROR,
                    foreign_key.child_table,
                    foreign_key.child_column,
                    pk,
                    "broken_foreign_key",
                    f"{int(invalid.sum())} references do not exist in "
                    f"{foreign_key.parent_table}.",
                    int(invalid.sum()),
                    _samples(
                        child,
                        invalid,
                        [pk, foreign_key.child_column],
                        max_samples,
                    ),
                    "Quarantine orphan rows and restore the parent reference.",
                )
            )

    for (table_name, column), allowed in ALLOWED_CATEGORIES.items():
        check_id = f"integrity.category.{table_name}.{column}"
        result.checks.add(check_id)
        if table_name not in tables or column not in tables[table_name]:
            continue
        frame = tables[table_name]
        invalid = frame[column].notna() & ~frame[column].isin(allowed)
        if invalid.any():
            pk = PRIMARY_KEYS[table_name]
            result.issues.append(
                _issue(
                    check_id,
                    Severity.ERROR,
                    table_name,
                    column,
                    pk,
                    "unknown_category",
                    f"{int(invalid.sum())} values are outside the "
                    "accepted category set.",
                    int(invalid.sum()),
                    _samples(frame, invalid, [pk, column], max_samples),
                    "Map only after source confirmation; otherwise quarantine rows.",
                )
            )
    return result


def _check_primary_key(
    table_name: str,
    frame: pd.DataFrame,
    primary_key: str,
    max_samples: int,
    result: CheckResult,
) -> None:
    check_id = f"integrity.primary_key.{table_name}"
    result.checks.add(check_id)
    missing = frame[primary_key].isna()
    if missing.any():
        result.issues.append(
            _issue(
                check_id,
                Severity.CRITICAL,
                table_name,
                primary_key,
                primary_key,
                "missing_primary_key",
                "Primary key contains NULL values.",
                int(missing.sum()),
                [],
                "Quarantine rows without stable identifiers.",
            )
        )
    duplicate = frame[primary_key].notna() & frame[primary_key].duplicated(keep=False)
    if duplicate.any():
        ratio = float(duplicate.mean())
        severity = Severity.CRITICAL if ratio >= 0.05 else Severity.ERROR
        result.issues.append(
            _issue(
                check_id,
                severity,
                table_name,
                primary_key,
                primary_key,
                "duplicate_primary_key",
                f"Primary key is duplicated in {int(duplicate.sum())} rows.",
                int(duplicate.sum()),
                _samples(frame, duplicate, [primary_key], max_samples),
                "Quarantine duplicate keys and reconcile them upstream.",
            )
        )
    non_positive = frame[primary_key].notna() & (frame[primary_key] <= 0)
    if non_positive.any():
        result.issues.append(
            _issue(
                check_id,
                Severity.ERROR,
                table_name,
                primary_key,
                primary_key,
                "non_positive_primary_key",
                "Primary keys must be positive integers.",
                int(non_positive.sum()),
                _samples(frame, non_positive, [primary_key], max_samples),
                "Regenerate stable positive identifiers.",
            )
        )


def _check_required(
    table_name: str,
    frame: pd.DataFrame,
    primary_key: str,
    max_samples: int,
    result: CheckResult,
) -> None:
    for column in frame.columns:
        if column in NULLABLE_COLUMNS[table_name]:
            continue
        check_id = f"integrity.required.{table_name}.{column}"
        result.checks.add(check_id)
        missing = frame[column].isna()
        if pd.api.types.is_string_dtype(frame[column].dtype):
            missing |= frame[column].astype("string").str.strip().eq("").fillna(False)
        if missing.any():
            result.issues.append(
                _issue(
                    check_id,
                    Severity.ERROR,
                    table_name,
                    column,
                    primary_key,
                    "missing_required_value",
                    f"Required column contains {int(missing.sum())} missing values.",
                    int(missing.sum()),
                    _samples(frame, missing, [primary_key], max_samples),
                    "Quarantine incomplete rows or restore the source value.",
                )
            )


def _check_business_keys(
    table_name: str,
    frame: pd.DataFrame,
    primary_key: str,
    max_samples: int,
    result: CheckResult,
) -> None:
    for columns in BUSINESS_KEYS.get(table_name, ()):
        if not set(columns) <= set(frame.columns):
            continue
        suffix = "_".join(columns)
        check_id = f"integrity.business_duplicate.{table_name}.{suffix}"
        result.checks.add(check_id)
        complete = frame[list(columns)].notna().all(axis=1)
        duplicate = complete & frame.duplicated(list(columns), keep=False)
        if duplicate.any():
            result.issues.append(
                _issue(
                    check_id,
                    Severity.ERROR,
                    table_name,
                    ",".join(columns),
                    primary_key,
                    "business_duplicate",
                    f"Business key {columns} is duplicated.",
                    int(duplicate.sum()),
                    _samples(
                        frame,
                        duplicate,
                        [primary_key, *columns],
                        max_samples,
                    ),
                    "Reconcile duplicate business entities before analysis.",
                )
            )


def calculate_completeness(
    tables: dict[str, pd.DataFrame],
) -> dict[str, float]:
    """Calculate required-field completeness by table and key field groups."""
    metrics: dict[str, float] = {}
    for table_name, frame in tables.items():
        required = [
            column
            for column in frame.columns
            if column not in NULLABLE_COLUMNS[table_name]
        ]
        expected = len(frame) * len(required)
        present = int(frame[required].notna().to_numpy().sum()) if expected else 0
        metrics[f"table.{table_name}"] = (
            round(present / expected, 6) if expected else 1.0
        )

    if "deliveries" in tables:
        deliveries = tables["deliveries"]
        delivered = deliveries["delivery_status"].eq("delivered")
        fields = [
            "actual_departure_at",
            "actual_delivery_at",
            "distance_actual_km",
            "fuel_cost",
            "driver_cost",
            "toll_cost",
            "maintenance_allocated_cost",
            "other_cost",
            "penalty_amount",
        ]
        expected = int(delivered.sum()) * len(fields)
        present = int(deliveries.loc[delivered, fields].notna().to_numpy().sum())
        metrics["group.delivered_required"] = (
            round(present / expected, 6) if expected else 1.0
        )
    values = [value for key, value in metrics.items() if key.startswith("table.")]
    metrics["overall"] = round(float(np.mean(values)), 6) if values else 0.0
    return dict(sorted(metrics.items()))
