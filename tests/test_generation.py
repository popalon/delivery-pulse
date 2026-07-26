"""Contract tests for deterministic synthetic data generation."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from delivery_pulse.generation import GenerationConfig, generate_dataset
from delivery_pulse.generation.maintenance import _next_idle_interval
from delivery_pulse.generation.pipeline import ExistingDataError, GenerationResult
from delivery_pulse.generation.schemas import PRIMARY_KEYS, TABLE_COLUMNS


def _config(
    tmp_path: Path,
    *,
    seed: int = 42,
    force: bool = False,
    inject_quality_issues: bool = False,
) -> GenerationConfig:
    return GenerationConfig(
        profile="test",
        orders=40,
        seed=seed,
        start_date=date(2024, 1, 1),
        months=2,
        output_dir=tmp_path / "raw",
        inject_quality_issues=inject_quality_issues,
        force=force,
    )


def _hash_files(result: GenerationResult) -> dict[str, str]:
    paths = sorted(result.output_dir.glob("*.csv"))
    paths.append(result.metadata_dir / "metadata.json")
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def test_same_seed_is_byte_reproducible(tmp_path: Path) -> None:
    first = generate_dataset(_config(tmp_path / "first"))
    second = generate_dataset(_config(tmp_path / "second"))

    assert _hash_files(first) == _hash_files(second)
    for table_name in TABLE_COLUMNS:
        pd.testing.assert_frame_equal(
            first.tables[table_name],
            second.tables[table_name],
        )


def test_different_seed_changes_orders(tmp_path: Path) -> None:
    first = generate_dataset(_config(tmp_path / "first", seed=42))
    second = generate_dataset(_config(tmp_path / "second", seed=43))

    assert not first.tables["orders"].equals(second.tables["orders"])


def test_tables_counts_schemas_and_primary_keys(tmp_path: Path) -> None:
    result = generate_dataset(_config(tmp_path))

    assert set(result.tables) == set(TABLE_COLUMNS)
    assert len(result.tables["orders"]) == 40
    assert result.metadata["requested_orders"] == 40
    for table_name, expected_columns in TABLE_COLUMNS.items():
        table = result.tables[table_name]
        assert table.columns.tolist() == expected_columns
        assert table[PRIMARY_KEYS[table_name]].is_unique
        assert (result.output_dir / f"{table_name}.csv").is_file()


def test_foreign_keys_and_first_release_relationship(tmp_path: Path) -> None:
    tables = generate_dataset(_config(tmp_path)).tables

    assert set(tables["orders"]["customer_id"]) <= set(
        tables["customers"]["customer_id"]
    )
    assert set(tables["orders"]["route_id"]) <= set(tables["routes"]["route_id"])
    assert set(tables["deliveries"]["order_id"]) == set(tables["orders"]["order_id"])
    assert tables["deliveries"]["order_id"].is_unique
    assert set(tables["deliveries"]["driver_id"]) <= set(tables["drivers"]["driver_id"])
    assert set(tables["deliveries"]["vehicle_id"]) <= set(
        tables["vehicles"]["vehicle_id"]
    )
    assert set(tables["route_events"]["delivery_id"]) <= set(
        tables["deliveries"]["delivery_id"]
    )
    assert set(tables["maintenance"]["vehicle_id"]) <= set(
        tables["vehicles"]["vehicle_id"]
    )


def test_statuses_and_timestamps_are_consistent(tmp_path: Path) -> None:
    tables = generate_dataset(_config(tmp_path)).tables
    orders = tables["orders"].set_index("order_id")
    deliveries = tables["deliveries"].set_index("order_id")

    assert (orders["created_at"] <= orders["requested_pickup_at"]).all()
    assert (orders["requested_pickup_at"] < orders["promised_delivery_at"]).all()
    pairs = set(
        zip(
            orders.loc[deliveries.index, "order_status"],
            deliveries["delivery_status"],
            strict=True,
        )
    )
    assert pairs <= {
        ("completed", "delivered"),
        ("completed", "failed"),
        ("cancelled", "cancelled"),
    }
    delivered = deliveries["delivery_status"] == "delivered"
    unfinished = ~delivered
    assert deliveries.loc[delivered, "actual_departure_at"].notna().all()
    assert deliveries.loc[delivered, "actual_delivery_at"].notna().all()
    assert (
        deliveries.loc[delivered, "actual_delivery_at"]
        > deliveries.loc[delivered, "actual_departure_at"]
    ).all()
    assert deliveries.loc[unfinished, "actual_delivery_at"].isna().all()
    assert not (
        (orders["order_status"] == "cancelled")
        & (deliveries["delivery_status"] == "delivered")
    ).any()
    failed_ids = set(
        tables["deliveries"].loc[
            tables["deliveries"]["delivery_status"] == "failed",
            "delivery_id",
        ]
    )
    documented_ids = set(tables["route_events"]["delivery_id"])
    assert failed_ids <= documented_ids


def test_events_maintenance_and_numeric_ranges(tmp_path: Path) -> None:
    tables = generate_dataset(_config(tmp_path)).tables
    events = tables["route_events"]
    deliveries = tables["deliveries"].set_index("delivery_id")
    maintenance = tables["maintenance"]

    assert (events["event_end_at"] >= events["event_at"]).all()
    delivered_events = events.join(
        deliveries[["delivery_status", "actual_delivery_at"]],
        on="delivery_id",
    )
    delivered_events = delivered_events.loc[
        delivered_events["delivery_status"] == "delivered"
    ]
    assert (
        delivered_events["event_end_at"] <= delivered_events["actual_delivery_at"]
    ).all()
    assert (maintenance["completed_at"] >= maintenance["started_at"]).all()
    assert (
        maintenance.sort_values(["vehicle_id", "started_at"])
        .groupby("vehicle_id")["odometer_km"]
        .apply(lambda values: values.is_monotonic_increasing)
        .all()
    )
    start = pd.Timestamp("2024-01-01", tz="UTC")
    first_service = (
        maintenance.sort_values("completed_at").groupby("vehicle_id").head(1)
    )
    assert (first_service["completed_at"] < start).all()

    for field in [
        "fuel_cost",
        "driver_cost",
        "toll_cost",
        "maintenance_allocated_cost",
        "other_cost",
        "penalty_amount",
    ]:
        assert (tables["deliveries"][field] >= 0).all()
    assert (tables["orders"]["cargo_weight_kg"] > 0).all()
    assert (tables["orders"]["distance_planned_km"] > 0).all()
    assert (events["delay_minutes"] >= 0).all()
    assert (events["extra_cost"] >= 0).all()

    active_maintenance = maintenance.loc[maintenance["started_at"] >= start]
    busy_deliveries = tables["deliveries"].dropna(subset=["actual_departure_at"])
    busy_deliveries = busy_deliveries.assign(
        busy_end=busy_deliveries["actual_delivery_at"].fillna(
            busy_deliveries["actual_departure_at"] + pd.Timedelta(hours=12)
        )
    )
    for service in active_maintenance.itertuples(index=False):
        assigned = busy_deliveries.loc[
            busy_deliveries["vehicle_id"] == service.vehicle_id
        ]
        overlap = (assigned["actual_departure_at"] < service.completed_at) & (
            assigned["busy_end"] > service.started_at
        )
        assert not overlap.any()


def test_output_stays_in_tmp_and_overwrite_requires_force(tmp_path: Path) -> None:
    config = _config(tmp_path, seed=42)
    first = generate_dataset(config)
    before = (first.output_dir / "orders.csv").read_bytes()

    assert first.output_dir.is_relative_to(tmp_path)
    assert first.metadata_dir.is_relative_to(tmp_path)
    with pytest.raises(ExistingDataError):
        generate_dataset(config)
    assert (first.output_dir / "orders.csv").read_bytes() == before

    forced = generate_dataset(_config(tmp_path, seed=43, force=True))
    assert (forced.output_dir / "orders.csv").read_bytes() != before


def test_quality_issue_manifest_matches_injected_defects(tmp_path: Path) -> None:
    result = generate_dataset(_config(tmp_path, inject_quality_issues=True))
    manifest = result.quality_manifest

    assert manifest is not None
    assert (result.metadata_dir / "quality_issues_manifest.csv").is_file()
    assert {
        "missing_required_value",
        "duplicate_primary_key",
        "broken_foreign_key",
        "unknown_category",
        "chronology_violation",
        "cost_outlier",
        "artificial_overload",
    } == set(manifest["issue_type"])
    assert result.tables["customers"]["customer_name"].isna().any()
    assert not result.tables["routes"]["route_id"].is_unique
    assert not set(result.tables["orders"]["customer_id"]) <= set(
        result.tables["customers"]["customer_id"]
    )
    assert "unknown_class" in set(result.tables["drivers"]["license_class"])
    assert (
        result.tables["orders"]["promised_delivery_at"]
        < result.tables["orders"]["requested_pickup_at"]
    ).any()
    assert result.tables["deliveries"]["fuel_cost"].max() == 99_999_999.99

    overload = manifest.loc[manifest["issue_type"] == "artificial_overload"].iloc[0]
    order = (
        result.tables["orders"]
        .loc[result.tables["orders"]["order_id"] == overload["record_id"]]
        .iloc[0]
    )
    delivery = (
        result.tables["deliveries"]
        .loc[result.tables["deliveries"]["order_id"] == overload["record_id"]]
        .iloc[0]
    )
    capacity = (
        result.tables["vehicles"]
        .loc[
            result.tables["vehicles"]["vehicle_id"] == delivery["vehicle_id"],
            "capacity_kg",
        ]
        .iloc[0]
    )
    assert order["cargo_weight_kg"] > capacity * 1.5


def test_cli_test_profile_succeeds_in_tmp_path(tmp_path: Path) -> None:
    output_dir = tmp_path / "raw"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "delivery_pulse",
            "generate",
            "--profile",
            "test",
            "--orders",
            "25",
            "--months",
            "1",
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "orders: 25" in result.stdout
    assert (output_dir / "orders.csv").is_file()
    assert (tmp_path / "metadata" / "metadata.json").is_file()


def test_idle_interval_search_handles_more_than_thirty_busy_days() -> None:
    candidate = pd.Timestamp("2024-01-01", tz="UTC")
    busy = [
        (
            candidate + pd.Timedelta(days=day),
            candidate + pd.Timedelta(days=day + 1),
        )
        for day in range(45)
    ]

    start, end = _next_idle_interval(candidate, busy, duration_hours=10)

    assert start == candidate + pd.Timedelta(days=45)
    assert end == start + pd.Timedelta(hours=10)
