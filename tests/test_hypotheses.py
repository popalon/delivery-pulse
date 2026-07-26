"""Tests for the pre-registered observational hypothesis pipeline."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
import statsmodels.formula.api as smf

from delivery_pulse.generation import GenerationConfig, generate_dataset
from delivery_pulse.hypotheses._binary import fit_binary_hypothesis
from delivery_pulse.hypotheses.diagnostics import (
    binary_risk_difference,
    standardized_risk_difference,
)
from delivery_pulse.hypotheses.feasibility import assess_feasibility
from delivery_pulse.hypotheses.models import FeasibilityResult, HypothesisConfig
from delivery_pulse.hypotheses.multiple_testing import (
    benjamini_hochberg,
    deterministic_bootstrap_mean_difference,
)
from delivery_pulse.hypotheses.pipeline import run_hypotheses
from delivery_pulse.warehouse import BuildConfig, build_warehouse


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_crude_and_adjusted_binary_effects() -> None:
    frame = pd.DataFrame(
        {
            "outcome": [0, 0, 1, 1, 0, 1, 1, 1] * 20,
            "exposure": [0, 0, 0, 0, 1, 1, 1, 1] * 20,
            "control": [0, 1, 0, 1, 0, 1, 0, 1] * 20,
        }
    )
    crude, low, high = binary_risk_difference(frame, "outcome", "exposure")
    fitted = smf.glm(
        "outcome ~ exposure + control",
        data=frame,
        family=sm.families.Binomial(),
    ).fit(cov_type="HC3")
    adjusted, adjusted_low, adjusted_high = standardized_risk_difference(
        fitted, frame, "exposure"
    )

    assert crude == pytest.approx(0.25)
    assert low < crude < high
    assert np.exp(fitted.params["exposure"]) > 1
    assert adjusted_low < adjusted < adjusted_high


def test_poisson_offset_recovers_rate_ratio() -> None:
    frame = pd.DataFrame(
        {
            "events": [1, 2, 2, 4, 2, 5, 3, 8],
            "exposed": [0, 0, 0, 0, 1, 1, 1, 1],
            "exposure": [100, 200, 200, 400, 100, 200, 200, 400],
        }
    )
    model = smf.glm(
        "events ~ exposed",
        data=frame,
        family=sm.families.Poisson(),
        offset=np.log(frame["exposure"]),
    ).fit()

    assert np.exp(model.params["exposed"]) == pytest.approx(2.0, rel=0.05)


def test_bh_and_bootstrap_are_deterministic() -> None:
    adjusted = benjamini_hochberg([0.01, 0.04, None, 0.03])
    first = deterministic_bootstrap_mean_difference(
        np.array([3.0, 4.0, 5.0]),
        np.array([1.0, 2.0, 3.0]),
        seed=42,
        iterations=100,
    )
    second = deterministic_bootstrap_mean_difference(
        np.array([3.0, 4.0, 5.0]),
        np.array([1.0, 2.0, 3.0]),
        seed=42,
        iterations=100,
    )

    assert adjusted == pytest.approx([0.03, 0.04, None, 0.04])
    assert first == second


def test_insufficient_sample_and_perfect_separation_are_inconclusive() -> None:
    feasibility = FeasibilityResult(
        "HX",
        True,
        40,
        20,
        20,
        20,
        20,
        0,
        1,
        20,
        "synthetic test",
    )
    frame = pd.DataFrame(
        {
            "outcome": [0] * 20 + [1] * 20,
            "exposure": [0] * 20 + [1] * 20,
            "distance_planned_1000km": [1.0] * 40,
        }
    )
    result = fit_binary_hypothesis(
        frame,
        feasibility,
        hypothesis_id="HX",
        title="separation",
        formula="outcome ~ exposure",
        outcome="outcome",
        exposure="exposure",
        practical_threshold=0.01,
        alternative=lambda effect: effect > 0,
    )

    assert result.result.status == "inconclusive"


def test_feasibility_keeps_h6_inconclusive() -> None:
    delivery = pd.DataFrame(
        {
            "delivery_status": ["delivered"] * 1_000,
            "is_late": [0] * 950 + [1] * 50,
            "has_loading_delay": [0, 1] * 500,
            "priority": ["standard", "express"] * 500,
            "financial_data_complete": [1] * 1_000,
            "is_loss_making": [0] * 970 + [1] * 30,
            "has_breakdown": [0] * 900 + [1] * 100,
            "customer_id": np.repeat(np.arange(10), 100),
            "operational_overload": [0] * 990 + [1] * 10,
            "vehicle_type": ["truck"] * 1_000,
        }
    )
    vehicle = pd.DataFrame(
        {
            "actual_distance_km": [100.0] * 600,
            "trip_hours": [2.0] * 600,
            "breakdown_count": [1] * 120 + [0] * 480,
            "had_scheduled_maintenance_previous_month": [0, 1] * 300,
        }
    )

    results = assess_feasibility(delivery, vehicle, min_group_size=90)

    assert {item.hypothesis_id: item.feasible for item in results}["H6"] is False


@pytest.fixture
def small_warehouse(tmp_path: Path) -> tuple[Path, Path]:
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


def test_pipeline_is_read_only_creates_reports_and_ignores_manifest(
    small_warehouse: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    raw, database = small_warehouse
    (raw / "quality_issues_manifest.csv").write_text(
        "forbidden,content\n", encoding="utf-8"
    )
    before = _hash(database)
    output = tmp_path / "hypotheses"
    result = run_hypotheses(HypothesisConfig(database, output, min_group_size=10))

    assert result.has_inconclusive
    assert _hash(database) == before
    assert len(result.results) == 6
    assert all(path.is_relative_to(tmp_path) for path in result.output_paths.values())
    assert {
        "hypothesis_summary.json",
        "hypothesis_results.csv",
        "model_coefficients.csv",
        "model_diagnostics.csv",
        "hypothesis_report.md",
    } <= {path.name for path in result.output_paths.values()}
    assert "quality_issues_manifest" not in (output / "hypothesis_report.md").read_text(
        encoding="utf-8"
    )


def test_cli_expected_code_and_sql_paths(
    small_warehouse: tuple[Path, Path],
    tmp_path: Path,
) -> None:
    _, database = small_warehouse
    output = tmp_path / "cli"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "delivery_pulse",
            "hypotheses",
            "run",
            "--database",
            str(database),
            "--output-dir",
            str(output),
            "--min-group-size",
            "10",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    sql_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("sql/hypotheses").glob("*.sql")
    )

    assert completed.returncode == 1, completed.stderr
    assert "/home/" not in sql_text
    assert "popalon" not in sql_text
