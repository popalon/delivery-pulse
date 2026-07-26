"""Read-only DuckDB dataset preparation from versioned SQL."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from delivery_pulse.analysis.loader import open_read_only
from delivery_pulse.paths import get_project_paths


def _read_sql(name: str) -> str:
    path = get_project_paths().sql / "hypotheses" / name
    return path.read_text(encoding="utf-8")


def load_delivery_dataset(database: Path) -> pd.DataFrame:
    """Load the delivery-level modeling dataset."""
    connection = open_read_only(database)
    try:
        frame = connection.execute(
            _read_sql("001_delivery_level_dataset.sql")
        ).fetchdf()
    finally:
        connection.close()
    frame["calendar_month"] = frame["calendar_month"].astype(str)
    frame["distance_planned_1000km"] = frame["distance_planned_km"] / 1000
    for column in (
        "is_late",
        "has_loading_delay",
        "has_traffic",
        "has_weather",
        "has_breakdown",
        "has_route_deviation",
        "operational_overload",
        "is_loss_making",
    ):
        frame[column] = frame[column].astype("Int64")
    return frame


def load_vehicle_month_dataset(database: Path) -> pd.DataFrame:
    """Load the vehicle-month count modeling dataset."""
    connection = open_read_only(database)
    try:
        frame = connection.execute(_read_sql("002_vehicle_month_dataset.sql")).fetchdf()
    finally:
        connection.close()
    frame["calendar_month"] = frame["calendar_month"].astype(str)
    return frame
