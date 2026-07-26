"""Acceptance tests for the DuckDB warehouse and SQL marts."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from delivery_pulse.generation import GenerationConfig, generate_dataset
from delivery_pulse.warehouse import (
    BuildConfig,
    ExistingWarehouseError,
    WarehouseQualityError,
    build_warehouse,
    get_baseline_metrics,
    validate_warehouse,
)
from delivery_pulse.warehouse.formulas import (
    delay_minutes,
    delivery_profit,
    group_margin_pct,
    margin_pct,
    net_revenue,
    total_delivery_cost,
)
from delivery_pulse.warehouse.validation import MARTS


def _generate(tmp_path: Path, *, defects: bool = False) -> Path:
    return generate_dataset(
        GenerationConfig(
            profile="test",
            orders=60,
            seed=42,
            start_date=date(2024, 1, 1),
            months=2,
            output_dir=tmp_path / "raw",
            inject_quality_issues=defects,
        )
    ).output_dir


def _hash_raw(input_dir: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(input_dir.glob("*.csv"))
    }


@pytest.fixture
def built_warehouse(tmp_path: Path) -> tuple[Path, Path]:
    input_dir = _generate(tmp_path)
    database = tmp_path / "warehouse.duckdb"
    build_warehouse(BuildConfig(input_dir, database))
    return input_dir, database


def test_clean_build_preserves_raw_and_stays_in_tmp_path(tmp_path: Path) -> None:
    input_dir = _generate(tmp_path)
    before = _hash_raw(input_dir)
    database = tmp_path / "nested" / "warehouse.duckdb"

    result = build_warehouse(BuildConfig(input_dir, database))

    assert result.database.is_relative_to(tmp_path)
    assert result.database.is_file()
    assert result.quality_status in {"passed", "passed_with_warnings"}
    assert result.validation.passed
    assert result.source_row_counts["orders"] == 60
    assert result.mart_row_counts["delivery_performance_mart"] == 60
    assert _hash_raw(input_dir) == before


def test_overwrite_requires_force(tmp_path: Path) -> None:
    input_dir = _generate(tmp_path)
    database = tmp_path / "warehouse.duckdb"
    first = build_warehouse(BuildConfig(input_dir, database))
    first_size = first.database.stat().st_size

    with pytest.raises(ExistingWarehouseError):
        build_warehouse(BuildConfig(input_dir, database))

    forced = build_warehouse(BuildConfig(input_dir, database, force=True))
    assert forced.database.stat().st_size == first_size
    assert forced.validation.passed


def test_failed_quality_prevents_database_creation(tmp_path: Path) -> None:
    input_dir = _generate(tmp_path, defects=True)
    database = tmp_path / "warehouse.duckdb"

    with pytest.raises(WarehouseQualityError):
        build_warehouse(BuildConfig(input_dir, database))

    assert not database.exists()


def test_objects_counts_grains_and_no_delivery_multiplication(
    built_warehouse: tuple[Path, Path],
) -> None:
    _, database = built_warehouse
    report = validate_warehouse(database)
    connection = duckdb.connect(str(database), read_only=True)
    objects = {
        row[0]
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main'"
        ).fetchall()
    }
    source_deliveries = connection.execute(
        "SELECT COUNT(*) FROM deliveries"
    ).fetchone()[0]

    assert report.passed
    assert set(MARTS) <= objects
    for mart in ("delivery_performance_mart", "delivery_financial_mart"):
        count, distinct_count = connection.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT delivery_id) FROM {mart}"
        ).fetchone()
        assert count == distinct_count == source_deliveries
    connection.close()


def test_sql_python_financial_parity_and_group_margin(
    built_warehouse: tuple[Path, Path],
) -> None:
    _, database = built_warehouse
    connection = duckdb.connect(str(database), read_only=True)
    row = connection.execute(
        """
        SELECT quoted_revenue, penalty_amount, fuel_cost, driver_cost,
               toll_cost, maintenance_allocated_cost, other_cost,
               event_extra_cost, net_revenue, total_delivery_cost,
               delivery_profit, margin_pct
        FROM delivery_financial_mart
        WHERE financial_data_complete AND net_revenue <> 0
        ORDER BY delivery_id
        LIMIT 1
        """
    ).fetchone()
    quoted, penalty, *values = row
    costs = values[:6]
    sql_net, sql_cost, sql_profit, sql_margin = values[6:]
    reference_net = net_revenue(quoted, penalty)
    reference_cost = total_delivery_cost(*costs)
    reference_profit = delivery_profit(reference_net, reference_cost)
    reference_margin = margin_pct(reference_profit, reference_net)
    totals = connection.execute(
        """
        SELECT list(delivery_profit), list(net_revenue), group_margin_pct
        FROM delivery_financial_mart
        CROSS JOIN (
            SELECT
                SUM(delivery_profit) / nullif(SUM(net_revenue), 0)
                    AS group_margin_pct
            FROM delivery_financial_mart
            WHERE financial_data_complete
        )
        WHERE financial_data_complete
        GROUP BY group_margin_pct
        """
    ).fetchone()
    average_row_margin = connection.execute(
        """
        SELECT AVG(margin_pct)
        FROM delivery_financial_mart
        WHERE financial_data_complete
        """
    ).fetchone()[0]
    connection.close()

    assert reference_net == sql_net
    assert reference_cost == sql_cost
    assert reference_profit == sql_profit
    assert float(reference_margin) == pytest.approx(float(sql_margin))
    assert float(group_margin_pct(totals[0], totals[1])) == pytest.approx(totals[2])
    assert float(totals[2]) != pytest.approx(float(average_row_margin))


def test_sql_python_sla_parity(
    built_warehouse: tuple[Path, Path],
) -> None:
    _, database = built_warehouse
    connection = duckdb.connect(str(database), read_only=True)
    raw_difference, sql_delay = connection.execute(
        """
        SELECT
            date_diff('minute', promised_delivery_at, actual_delivery_at),
            delay_minutes
        FROM delivery_performance_mart
        WHERE delivery_status = 'delivered'
        ORDER BY delivery_id
        LIMIT 1
        """
    ).fetchone()
    connection.close()

    assert delay_minutes(0, raw_difference) == sql_delay


def test_event_and_maintenance_aggregates_are_not_multiplied(
    built_warehouse: tuple[Path, Path],
) -> None:
    _, database = built_warehouse
    connection = duckdb.connect(str(database), read_only=True)
    source_event_cost, mart_event_cost = connection.execute(
        """
        SELECT
            (SELECT SUM(extra_cost) FROM route_events),
            (SELECT SUM(event_extra_cost) FROM delivery_financial_mart)
        """
    ).fetchone()
    source_maintenance, mart_maintenance = connection.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM maintenance),
            (SELECT SUM(maintenance_events) FROM vehicle_reliability_mart)
        """
    ).fetchone()
    penalty_exclusion_errors = connection.execute(
        """
        SELECT COUNT(*)
        FROM delivery_financial_mart
        WHERE total_delivery_cost <> fuel_cost + driver_cost + toll_cost
            + maintenance_allocated_cost + other_cost + event_extra_cost
        """
    ).fetchone()[0]
    connection.close()

    assert source_event_cost == mart_event_cost
    assert source_maintenance == mart_maintenance
    assert penalty_exclusion_errors == 0


def test_baseline_metrics_reconcile_to_marts(
    built_warehouse: tuple[Path, Path],
) -> None:
    _, database = built_warehouse
    baseline = get_baseline_metrics(database)
    connection = duckdb.connect(str(database), read_only=True)
    source_counts = connection.execute(
        """
        SELECT
            COUNT(*),
            count_if(delivery_status = 'delivered'),
            count_if(delivery_status = 'failed'),
            count_if(delivery_status = 'cancelled')
        FROM deliveries
        """
    ).fetchone()
    connection.close()

    assert baseline["deliveries_count"] == source_counts[0]
    assert baseline["delivered_count"] == source_counts[1]
    assert baseline["failed_count"] == source_counts[2]
    assert baseline["cancelled_count"] == source_counts[3]
    assert Decimal(str(baseline["total_delivery_cost"])) >= 0
    assert 0 <= float(baseline["data_completeness_rate"]) <= 1


def test_cli_build_validate_and_validation_failure(tmp_path: Path) -> None:
    input_dir = _generate(tmp_path)
    database = tmp_path / "warehouse.duckdb"
    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "delivery_pulse",
            "warehouse",
            "build",
            "--input-dir",
            str(input_dir),
            "--database",
            str(database),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    valid = subprocess.run(
        [
            sys.executable,
            "-m",
            "delivery_pulse",
            "warehouse",
            "validate",
            "--database",
            str(database),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    connection = duckdb.connect(str(database))
    connection.execute("DROP TABLE delivery_performance_mart")
    connection.close()
    invalid = subprocess.run(
        [
            sys.executable,
            "-m",
            "delivery_pulse",
            "warehouse",
            "validate",
            "--database",
            str(database),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert build.returncode == 0, build.stderr
    assert valid.returncode == 0, valid.stderr
    assert invalid.returncode == 1
    assert "[FAIL]" in invalid.stdout


def test_cli_quality_failure_returns_one(tmp_path: Path) -> None:
    input_dir = _generate(tmp_path, defects=True)
    database = tmp_path / "warehouse.duckdb"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "delivery_pulse",
            "warehouse",
            "build",
            "--input-dir",
            str(input_dir),
            "--database",
            str(database),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert not database.exists()


def test_sql_contains_no_machine_specific_paths() -> None:
    sql_root = Path(__file__).resolve().parents[1] / "sql"
    sql_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(sql_root.rglob("*.sql"))
    ).lower()

    assert "/home/" not in sql_text
    assert "popalon" not in sql_text
    assert "\\users\\" not in sql_text
