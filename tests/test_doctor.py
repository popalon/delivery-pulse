"""Tests for non-mutating doctor diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest

from delivery_pulse.__main__ import main
from delivery_pulse.doctor import run_doctor


def test_doctor_reports_missing_optional_tools_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("delivery_pulse.doctor.shutil.which", lambda _name: None)
    database = tmp_path / "missing.duckdb"
    before = set(tmp_path.iterdir())

    checks = run_doctor(database=database)

    assert set(tmp_path.iterdir()) == before
    assert {check.check_id: check.status for check in checks}["docker.cli"] == (
        "warning"
    )
    assert {check.check_id: check.status for check in checks}[
        "warehouse.validation"
    ] == "warning"
    assert all("password" not in check.message.lower() for check in checks)


def test_doctor_cli_succeeds_with_warnings(tmp_path: Path) -> None:
    assert main(["doctor", "--database", str(tmp_path / "missing.duckdb")]) == 0
