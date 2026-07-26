"""Typed result models for data-quality checks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class Severity(StrEnum):
    """Severity of one quality finding."""

    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class QualityStatus(StrEnum):
    """Overall analytical usability status."""

    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class QualityIssue:
    """One detected violation or diagnostic finding."""

    check_id: str
    severity: Severity
    table_name: str
    column_name: str | None
    row_identifier: str | None
    issue_type: str
    message: str
    affected_rows: int
    sample_values: list[str]
    remediation_hint: str

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""
        result = asdict(self)
        result["severity"] = self.severity.value
        return result


@dataclass(slots=True)
class CheckResult:
    """Issues and executed check identifiers returned by one check family."""

    issues: list[QualityIssue] = field(default_factory=list)
    checks: set[str] = field(default_factory=set)

    def extend(self, other: CheckResult) -> None:
        """Merge another check result."""
        self.issues.extend(other.issues)
        self.checks.update(other.checks)


@dataclass(slots=True)
class QualityReport:
    """Complete outcome of one quality run."""

    checked_at: str
    input_dir: Path
    discovered_tables: list[str]
    row_counts: dict[str, int]
    checks_run: int
    critical_count: int
    error_count: int
    warning_count: int
    info_count: int
    status: QualityStatus
    completeness_metrics: dict[str, float]
    issues: list[QualityIssue]
    project_version: str

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-compatible mapping."""
        return {
            "checked_at": self.checked_at,
            "input_dir": str(self.input_dir),
            "discovered_tables": self.discovered_tables,
            "row_counts": self.row_counts,
            "checks_run": self.checks_run,
            "critical_count": self.critical_count,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "status": self.status.value,
            "completeness_metrics": self.completeness_metrics,
            "issues": [issue.to_dict() for issue in self.issues],
            "project_version": self.project_version,
        }
