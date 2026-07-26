"""Smoke tests for the package and command-line interface."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import delivery_pulse


def test_package_imports() -> None:
    assert delivery_pulse.PROJECT_NAME == "DeliveryPulse"
    assert delivery_pulse.__version__


def test_cli_info_succeeds() -> None:
    project_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "delivery_pulse", "info"],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Project: DeliveryPulse" in result.stdout
    assert "Business timezone: Europe/Moscow" in result.stdout
    assert "Currency: RUB" in result.stdout
