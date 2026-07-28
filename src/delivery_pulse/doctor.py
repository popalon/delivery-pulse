"""Read-only environment diagnostics for DeliveryPulse."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from delivery_pulse.config import CONFIG
from delivery_pulse.paths import get_project_paths
from delivery_pulse.warehouse import WarehouseError, validate_warehouse


@dataclass(frozen=True, slots=True)
class DoctorCheck:
    """One non-mutating diagnostic result."""

    check_id: str
    status: str
    message: str


def run_doctor(
    *,
    database: Path | None = None,
    check_postgres: bool = False,
    postgres_config: Any = None,
) -> tuple[DoctorCheck, ...]:
    """Inspect local readiness without printing secrets or changing state."""
    paths = get_project_paths()
    checks = [
        DoctorCheck(
            "python.version",
            "pass" if sys.version_info >= (3, 11) else "fail",
            f"Python {sys.version.split()[0]} (requires 3.11+)",
        )
    ]
    core_config_valid = (
        CONFIG.currency_code == "RUB"
        and CONFIG.business_timezone == "Europe/Moscow"
        and CONFIG.encoding.lower().replace("-", "") == "utf8"
    )
    checks.append(
        DoctorCheck(
            "configuration.core",
            "pass" if core_config_valid else "fail",
            "Core configuration: RUB, Europe/Moscow, UTF-8",
        )
    )
    for dependency in ("duckdb", "pandas", "numpy", "matplotlib"):
        available = importlib.util.find_spec(dependency) is not None
        checks.append(
            DoctorCheck(
                f"dependency.{dependency}",
                "pass" if available else "fail",
                f"{dependency}: {'available' if available else 'missing'}",
            )
        )
    for directory in paths.local_directories():
        checks.append(
            DoctorCheck(
                f"directory.{directory.name}",
                "pass" if directory.is_dir() else "warning",
                f"{directory}: {'available' if directory.is_dir() else 'missing'}",
            )
        )
    target = database or paths.data_processed / "delivery_pulse.duckdb"
    if target.is_file():
        try:
            report = validate_warehouse(target)
            passed = report.passed
            checks.append(
                DoctorCheck(
                    "warehouse.validation",
                    "pass" if passed else "fail",
                    f"warehouse validation: {'passed' if passed else 'failed'}",
                )
            )
        except WarehouseError as error:
            checks.append(DoctorCheck("warehouse.validation", "fail", str(error)))
    else:
        checks.append(
            DoctorCheck("warehouse.validation", "warning", "DuckDB is not present")
        )
    docker = shutil.which("docker")
    checks.append(
        DoctorCheck(
            "docker.cli",
            "pass" if docker else "warning",
            "Docker CLI available" if docker else "Docker CLI not found",
        )
    )
    compose = False
    if docker:
        completed = subprocess.run(
            [docker, "compose", "version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        compose = completed.returncode == 0
    checks.append(
        DoctorCheck(
            "docker.compose",
            "pass" if compose else "warning",
            "Docker Compose available" if compose else "Docker Compose not found",
        )
    )
    if check_postgres:
        if postgres_config is None:
            checks.append(
                DoctorCheck(
                    "postgres.connection", "fail", "PostgreSQL config is missing"
                )
            )
        else:
            try:
                from delivery_pulse.publish.connection import connect_postgres

                connection = connect_postgres(postgres_config)
                connection.close()
                checks.append(
                    DoctorCheck(
                        "postgres.connection", "pass", "PostgreSQL connection passed"
                    )
                )
            except Exception as error:
                checks.append(
                    DoctorCheck(
                        "postgres.connection",
                        "fail",
                        f"PostgreSQL connection failed: {type(error).__name__}",
                    )
                )
    return tuple(checks)
