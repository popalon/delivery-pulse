"""Typed warehouse configuration and result models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class BuildConfig:
    """Parameters for one atomic warehouse build."""

    input_dir: Path
    database: Path
    force: bool = False
    skip_quality_check: bool = False
    allow_warnings: bool = False
    sql_dir: Path | None = None


@dataclass(frozen=True, slots=True)
class ValidationCheck:
    """One human-readable warehouse validation result."""

    check_id: str
    passed: bool
    message: str


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Aggregate warehouse validation outcome."""

    database: Path
    checks: tuple[ValidationCheck, ...]

    @property
    def passed(self) -> bool:
        """Return true only when every validation check passed."""
        return all(check.passed for check in self.checks)

    @property
    def failures(self) -> tuple[ValidationCheck, ...]:
        """Return failed checks in deterministic order."""
        return tuple(check for check in self.checks if not check.passed)


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Successful build artifacts and diagnostics."""

    database: Path
    source_row_counts: dict[str, int]
    mart_row_counts: dict[str, int]
    quality_status: str
    validation: ValidationReport
    elapsed_seconds: float


WarehouseInfo = dict[str, Any]
