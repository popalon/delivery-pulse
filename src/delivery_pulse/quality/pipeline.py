"""Orchestrate independent data-quality validation and reporting."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from delivery_pulse import __version__
from delivery_pulse.quality.business_checks import run_business_checks
from delivery_pulse.quality.integrity_checks import (
    calculate_completeness,
    run_integrity_checks,
)
from delivery_pulse.quality.loader import QualityLoadError, load_dataset
from delivery_pulse.quality.models import (
    CheckResult,
    QualityIssue,
    QualityReport,
    QualityStatus,
    Severity,
)
from delivery_pulse.quality.profiling import profile_tables
from delivery_pulse.quality.reporting import write_reports
from delivery_pulse.quality.schema_checks import validate_and_coerce


class QualityRunError(RuntimeError):
    """Raised when a quality run cannot start or persist reports."""


def _sort_issues(issues: list[QualityIssue]) -> list[QualityIssue]:
    severity_order = {
        Severity.CRITICAL: 0,
        Severity.ERROR: 1,
        Severity.WARNING: 2,
        Severity.INFO: 3,
    }
    return sorted(
        issues,
        key=lambda issue: (
            severity_order[issue.severity],
            issue.table_name,
            issue.check_id,
            issue.column_name or "",
            issue.row_identifier or "",
            issue.sample_values,
        ),
    )


def _status(issues: list[QualityIssue]) -> QualityStatus:
    severities = {issue.severity for issue in issues}
    if Severity.CRITICAL in severities or Severity.ERROR in severities:
        return QualityStatus.FAILED
    if Severity.WARNING in severities:
        return QualityStatus.PASSED_WITH_WARNINGS
    return QualityStatus.PASSED


def run_quality(
    input_dir: Path,
    output_dir: Path | None = None,
    *,
    max_samples: int = 5,
    profile_format: str = "csv",
) -> tuple[QualityReport, pd.DataFrame, dict[str, Path]]:
    """Validate one raw dataset and optionally persist deterministic reports."""
    if max_samples <= 0:
        raise QualityRunError("max_samples must be a positive integer")
    if profile_format not in {"csv", "json"}:
        raise QualityRunError("profile_format must be 'csv' or 'json'")
    try:
        loaded = load_dataset(input_dir)
    except QualityLoadError as error:
        raise QualityRunError(str(error)) from error
    tables, schema_result = validate_and_coerce(loaded, max_samples)
    combined = CheckResult()
    combined.extend(schema_result)
    combined.extend(run_integrity_checks(tables, max_samples))
    combined.extend(run_business_checks(tables, max_samples))
    issues = _sort_issues(combined.issues)
    counts = {
        severity: sum(issue.severity == severity for issue in issues)
        for severity in Severity
    }
    report = QualityReport(
        checked_at=datetime.now(UTC).isoformat(),
        input_dir=input_dir.resolve(),
        discovered_tables=sorted(loaded.tables),
        row_counts={name: len(loaded.tables[name]) for name in sorted(loaded.tables)},
        checks_run=len(combined.checks),
        critical_count=counts[Severity.CRITICAL],
        error_count=counts[Severity.ERROR],
        warning_count=counts[Severity.WARNING],
        info_count=counts[Severity.INFO],
        status=_status(issues),
        completeness_metrics=calculate_completeness(tables),
        issues=issues,
        project_version=__version__,
    )
    profiles = profile_tables(tables)
    paths: dict[str, Path] = {}
    if output_dir is not None:
        try:
            paths = write_reports(report, profiles, output_dir, profile_format)
        except OSError as error:
            raise QualityRunError(f"cannot write quality reports: {error}") from error
    return report, profiles, paths


def should_fail(report: QualityReport, fail_on: str) -> bool:
    """Return whether a report crosses the configured CLI failure threshold."""
    if fail_on == "warning":
        return bool(report.warning_count + report.error_count + report.critical_count)
    if fail_on == "error":
        return bool(report.error_count + report.critical_count)
    if fail_on == "critical":
        return bool(report.critical_count)
    raise QualityRunError("fail_on must be critical, error, or warning")
