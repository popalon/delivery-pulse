"""Acceptance tests for the read-only exploratory analysis layer."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from delivery_pulse.analysis import run_eda
from delivery_pulse.analysis.reporting import hypothesis_candidates
from delivery_pulse.analysis.segmentation import rank_table
from delivery_pulse.analysis.summaries import priority_summary
from delivery_pulse.generation import GenerationConfig, generate_dataset
from delivery_pulse.warehouse import BuildConfig, build_warehouse, get_baseline_metrics


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def analysis_warehouse(tmp_path: Path) -> tuple[Path, Path]:
    raw = generate_dataset(
        GenerationConfig(
            profile="test",
            orders=80,
            seed=42,
            start_date=date(2024, 1, 1),
            months=2,
            output_dir=tmp_path / "raw",
        )
    ).output_dir
    database = tmp_path / "warehouse.duckdb"
    build_warehouse(BuildConfig(raw, database))
    return raw, database


def test_pipeline_reads_marts_preserves_inputs_and_writes_only_to_tmp(
    analysis_warehouse: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    raw, database = analysis_warehouse
    raw_before = {path.name: _hash(path) for path in raw.glob("*.csv")}
    database_before = _hash(database)

    result = run_eda(database, tmp_path / "reports", top_n=5, min_group_size=5)

    assert result.context.baseline == get_baseline_metrics(database)
    assert result.context.row_counts["delivery_performance_mart"] == 80
    assert len(result.figures) == 10
    assert all(
        path.is_file() and path.is_relative_to(tmp_path)
        for path in result.figures.values()
    )
    assert result.report_path.is_file() and result.report_path.is_relative_to(tmp_path)
    assert _hash(database) == database_before
    assert {path.name: _hash(path) for path in raw.glob("*.csv")} == raw_before


def test_rates_have_samples_and_group_margin_is_ratio_of_sums(
    analysis_warehouse: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    _, database = analysis_warehouse
    result = run_eda(database, tmp_path / "eda", top_n=5, min_group_size=5)
    routes = result.tables["routes"]
    priorities = result.tables["priority"]
    connection = duckdb.connect(str(database), read_only=True)
    expected = connection.execute(
        """
        SELECT priority,
               SUM(delivery_profit) / nullif(SUM(net_revenue), 0)
        FROM delivery_financial_mart
        WHERE financial_data_complete
        GROUP BY priority
        ORDER BY priority
        """
    ).fetchall()
    average_margins = dict(
        connection.execute(
            """
            SELECT priority, AVG(margin_pct)
            FROM delivery_financial_mart
            WHERE financial_data_complete
            GROUP BY priority
            """
        ).fetchall()
    )
    connection.close()

    assert {"deliveries_count", "delivered_count", "on_time_delivery_rate"} <= set(
        routes.columns
    )
    for priority, margin in expected:
        actual = priorities.loc[
            priorities["priority"] == priority, "group_margin_pct"
        ].iloc[0]
        assert actual == pytest.approx(margin)
        assert actual != pytest.approx(average_margins[priority])


def test_null_and_zero_denominators_are_safe() -> None:
    connection = duckdb.connect()
    connection.execute(
        """
        CREATE TABLE delivery_performance_mart (
            delivery_id BIGINT, priority VARCHAR, delivery_status VARCHAR,
            is_on_time BOOLEAN, delay_minutes DOUBLE,
            breakdown_event_count BIGINT, loading_delay_minutes DOUBLE
        );
        INSERT INTO delivery_performance_mart VALUES
            (1, 'standard', 'cancelled', NULL, NULL, 0, 0);
        CREATE TABLE delivery_financial_mart (
            delivery_id BIGINT, net_revenue DOUBLE, total_delivery_cost DOUBLE,
            delivery_profit DOUBLE, financial_data_complete BOOLEAN,
            is_loss_making BOOLEAN
        );
        INSERT INTO delivery_financial_mart VALUES
            (1, 0, 0, 0, true, false);
        """
    )
    summary = priority_summary(connection)
    connection.close()

    assert pd.isna(summary.loc[0, "on_time_delivery_rate"])
    assert pd.isna(summary.loc[0, "group_margin_pct"])
    assert summary.loc[0, "deliveries_count"] == 1


def test_rankings_filter_small_groups_and_are_deterministic() -> None:
    frame = pd.DataFrame(
        {
            "route_id": [3, 1, 2],
            "deliveries_count": [4, 10, 10],
            "metric": [0.1, 0.2, 0.2],
        }
    )
    first = rank_table(
        frame,
        "metric",
        top_n=5,
        ascending=True,
        min_group_size=5,
    )
    second = rank_table(
        frame.sample(frac=1, random_state=7),
        "metric",
        top_n=5,
        ascending=True,
        min_group_size=5,
    )

    assert first["route_id"].tolist() == [1, 2]
    pd.testing.assert_frame_equal(first, second)


def test_report_hypotheses_cli_and_manifest_independence(
    analysis_warehouse: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    raw, database = analysis_warehouse
    manifest = raw / "quality_issues_manifest.csv"
    manifest.write_text("forbidden,content\n", encoding="utf-8")
    output = tmp_path / "cli-output"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "delivery_pulse",
            "eda",
            "--database",
            str(database),
            "--output-dir",
            str(output),
            "--top-n",
            "4",
            "--min-group-size",
            "5",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert (output / "eda_summary.md").is_file()
    assert len(hypothesis_candidates()) == 6
    assert "quality_issues_manifest" not in (output / "eda_summary.md").read_text(
        encoding="utf-8"
    )
