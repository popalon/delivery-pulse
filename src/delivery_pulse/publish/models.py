"""Typed models for publication and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from delivery_pulse.publish.config import PostgresConfig

PublishMode = Literal["create", "replace"]


@dataclass(frozen=True, slots=True)
class PublishConfig:
    """One PostgreSQL publication request."""

    database: Path
    postgres: PostgresConfig
    mode: PublishMode = "create"
    force: bool = False
    validate_only: bool = False


@dataclass(frozen=True, slots=True)
class ValidationCheck:
    """One human-readable publish reconciliation check."""

    check_id: str
    passed: bool
    source_value: str
    target_value: str
    message: str


@dataclass(frozen=True, slots=True)
class PublishValidationReport:
    """Deterministic DuckDB/PostgreSQL reconciliation result."""

    checks: tuple[ValidationCheck, ...]

    @property
    def passed(self) -> bool:
        """Return whether every reconciliation check passed."""
        return all(check.passed for check in self.checks)


@dataclass(frozen=True, slots=True)
class PublishResult:
    """Publication outcome safe for CLI display."""

    schema: str
    mode: PublishMode
    table_counts: dict[str, int]
    validation: PublishValidationReport
    elapsed_seconds: float
    validate_only: bool
