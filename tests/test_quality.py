"""Acceptance tests for the independent data-quality pipeline."""

from __future__ import annotations

import hashlib
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from delivery_pulse.generation import GenerationConfig, generate_dataset
from delivery_pulse.quality import run_quality


def _generate(tmp_path: Path, *, defects: bool = False) -> tuple[Path, Path]:
    result = generate_dataset(
        GenerationConfig(
            profile="test",
            orders=60,
            seed=42,
            start_date=date(2024, 1, 1),
            months=2,
            output_dir=tmp_path / "raw",
            inject_quality_issues=defects,
        )
    )
    return result.output_dir, result.metadata_dir


def _hash_csv(input_dir: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(input_dir.glob("*.csv"))
    }


def _issue_types(report: object) -> set[str]:
    return {issue.issue_type for issue in report.issues}  # type: ignore[attr-defined]


def _rewrite(path: Path, transform: object) -> None:
    frame = pd.read_csv(path)
    updated = transform(frame)  # type: ignore[operator]
    updated.to_csv(path, index=False, lineterminator="\n")


def test_clean_dataset_has_no_error_and_reports_are_created(tmp_path: Path) -> None:
    input_dir, _ = _generate(tmp_path / "data")
    before = _hash_csv(input_dir)

    report, profiles, paths = run_quality(input_dir, tmp_path / "reports")

    assert report.status.value in {"passed", "passed_with_warnings"}
    assert report.critical_count == 0
    assert report.error_count == 0
    assert report.completeness_metrics["overall"] == 1.0
    assert set(paths) == {"summary", "issues", "markdown", "profiles"}
    assert all(path.is_file() for path in paths.values())
    assert not profiles.empty
    assert _hash_csv(input_dir) == before


def test_defect_dataset_fails_and_manifest_is_not_required(tmp_path: Path) -> None:
    input_dir, metadata_dir = _generate(tmp_path / "data", defects=True)
    manifest = metadata_dir / "quality_issues_manifest.csv"
    manifest.unlink()

    report, _, _ = run_quality(input_dir)

    expected = {
        "missing_required_value",
        "duplicate_primary_key",
        "broken_foreign_key",
        "unknown_category",
        "chronology_violation",
        "cost_outlier",
        "artificial_overload",
    }
    assert report.status.value == "failed"
    assert expected <= _issue_types(report)


def test_pipeline_never_reads_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir, metadata_dir = _generate(tmp_path / "data", defects=True)
    manifest = (metadata_dir / "quality_issues_manifest.csv").resolve()
    original = Path.read_text

    def guarded_read(path: Path, *args: object, **kwargs: object) -> str:
        if path.resolve() == manifest:
            raise AssertionError("quality pipeline attempted to read manifest")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded_read)
    report, _, _ = run_quality(input_dir)

    assert report.status.value == "failed"


@pytest.mark.parametrize(
    ("table", "transform", "expected"),
    [
        (
            "customers",
            lambda frame: pd.concat([frame, frame.iloc[[0]]], ignore_index=True),
            "duplicate_primary_key",
        ),
        (
            "orders",
            lambda frame: frame.assign(
                customer_id=frame["customer_id"].mask(frame.index == 0, 9_999_999)
            ),
            "broken_foreign_key",
        ),
        (
            "customers",
            lambda frame: frame.assign(
                customer_name=frame["customer_name"].mask(frame.index == 0)
            ),
            "missing_required_value",
        ),
        (
            "drivers",
            lambda frame: frame.assign(
                license_class=frame["license_class"].mask(frame.index == 0, "invalid")
            ),
            "unknown_category",
        ),
        (
            "orders",
            lambda frame: frame.assign(
                promised_delivery_at=frame["promised_delivery_at"].mask(
                    frame.index == 0, frame.loc[0, "created_at"]
                )
            ),
            "chronology_violation",
        ),
        (
            "deliveries",
            lambda frame: frame.assign(
                fuel_cost=frame["fuel_cost"].mask(frame.index == 0, -1)
            ),
            "invalid_numeric_value",
        ),
        (
            "deliveries",
            lambda frame: frame.assign(
                delivery_status=frame["delivery_status"].mask(
                    frame.index == 0, "planned"
                )
            ),
            "invalid_status_pair",
        ),
    ],
)
def test_core_rule_families_detect_mutations(
    tmp_path: Path,
    table: str,
    transform: object,
    expected: str,
) -> None:
    input_dir, _ = _generate(tmp_path)
    _rewrite(input_dir / f"{table}.csv", transform)

    report, _, _ = run_quality(input_dir)

    assert expected in _issue_types(report)


def test_maintenance_overlap_is_detected(tmp_path: Path) -> None:
    input_dir, _ = _generate(tmp_path)
    deliveries = pd.read_csv(input_dir / "deliveries.csv")
    maintenance = pd.read_csv(input_dir / "maintenance.csv")
    delivery = deliveries.loc[deliveries["actual_departure_at"].notna()].iloc[0]
    row = maintenance.index[0]
    maintenance.loc[row, "vehicle_id"] = delivery["vehicle_id"]
    maintenance.loc[row, "started_at"] = delivery["actual_departure_at"]
    maintenance.loc[row, "completed_at"] = (
        pd.Timestamp(delivery["actual_departure_at"]) + pd.Timedelta(hours=1)
    ).isoformat()
    maintenance.to_csv(input_dir / "maintenance.csv", index=False, lineterminator="\n")

    report, _, _ = run_quality(input_dir)

    assert "maintenance_delivery_overlap" in _issue_types(report)


def test_overload_warning_and_error_are_separate(tmp_path: Path) -> None:
    input_dir, _ = _generate(tmp_path)
    orders = pd.read_csv(input_dir / "orders.csv")
    deliveries = pd.read_csv(input_dir / "deliveries.csv")
    vehicles = pd.read_csv(input_dir / "vehicles.csv")
    for index, ratio in zip((0, 1), (1.02, 1.20), strict=True):
        vehicle_id = deliveries.loc[index, "vehicle_id"]
        capacity = vehicles.loc[
            vehicles["vehicle_id"] == vehicle_id, "capacity_kg"
        ].iloc[0]
        order_id = deliveries.loc[index, "order_id"]
        orders.loc[orders["order_id"] == order_id, "cargo_weight_kg"] = capacity * ratio
    orders.to_csv(input_dir / "orders.csv", index=False, lineterminator="\n")

    report, _, _ = run_quality(input_dir)

    assert {"operational_overload", "artificial_overload"} <= _issue_types(report)


def test_issue_order_is_deterministic(tmp_path: Path) -> None:
    input_dir, _ = _generate(tmp_path / "data", defects=True)

    first, _, _ = run_quality(input_dir)
    second, _, _ = run_quality(input_dir)

    first_order = [(issue.check_id, issue.sample_values) for issue in first.issues]
    second_order = [(issue.check_id, issue.sample_values) for issue in second.issues]
    assert first_order == second_order


def test_cli_returns_zero_for_clean_and_one_for_defects(tmp_path: Path) -> None:
    clean, _ = _generate(tmp_path / "clean")
    defective, _ = _generate(tmp_path / "defective", defects=True)

    clean_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "delivery_pulse",
            "quality",
            "--input-dir",
            str(clean),
            "--output-dir",
            str(tmp_path / "clean-reports"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    defect_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "delivery_pulse",
            "quality",
            "--input-dir",
            str(defective),
            "--output-dir",
            str(tmp_path / "defect-reports"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert clean_run.returncode == 0, clean_run.stderr
    assert defect_run.returncode == 1
    assert "Quality status: failed" in defect_run.stdout
