"""Deterministic descriptive profiles that complement rule checks."""

from __future__ import annotations

import json

import pandas as pd


def profile_tables(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Return one deterministic profile row per table column."""
    rows: list[dict[str, object]] = []
    for table_name in sorted(tables):
        frame = tables[table_name]
        duplicate_rows = int(frame.duplicated().sum())
        memory_bytes = int(frame.memory_usage(deep=True).sum())
        for column in sorted(frame.columns):
            values = frame[column]
            non_null = values.dropna()
            numeric = (
                values
                if pd.api.types.is_numeric_dtype(values.dtype)
                and not pd.api.types.is_bool_dtype(values.dtype)
                else None
            )
            date_like = (
                values if pd.api.types.is_datetime64_any_dtype(values.dtype) else None
            )
            top = values.astype("string").value_counts(dropna=True).head(5)
            row: dict[str, object] = {
                "table_name": table_name,
                "column_name": column,
                "row_count": len(frame),
                "column_count": len(frame.columns),
                "dtype": str(values.dtype),
                "unique_count": int(values.nunique(dropna=True)),
                "null_count": int(values.isna().sum()),
                "null_pct": round(float(values.isna().mean()), 6),
                "min": None,
                "max": None,
                "q01": None,
                "q25": None,
                "q50": None,
                "q75": None,
                "q99": None,
                "date_min": None,
                "date_max": None,
                "top_values": json.dumps(
                    {str(key): int(value) for key, value in top.items()},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "duplicate_rows": duplicate_rows,
                "memory_bytes": memory_bytes,
            }
            if numeric is not None and not non_null.empty:
                quantiles = numeric.quantile([0.01, 0.25, 0.5, 0.75, 0.99])
                row.update(
                    {
                        "min": float(numeric.min()),
                        "max": float(numeric.max()),
                        "q01": float(quantiles.loc[0.01]),
                        "q25": float(quantiles.loc[0.25]),
                        "q50": float(quantiles.loc[0.5]),
                        "q75": float(quantiles.loc[0.75]),
                        "q99": float(quantiles.loc[0.99]),
                    }
                )
            elif date_like is not None and not non_null.empty:
                row["date_min"] = str(date_like.min())
                row["date_max"] = str(date_like.max())
            elif not non_null.empty:
                row["min"] = str(non_null.min())
                row["max"] = str(non_null.max())
            rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["table_name", "column_name"], ignore_index=True
    )
