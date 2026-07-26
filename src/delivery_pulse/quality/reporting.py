"""Persist machine-readable and human-readable quality reports."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd

from delivery_pulse.config import CONFIG
from delivery_pulse.quality.models import QualityIssue, QualityReport

ISSUE_COLUMNS = [
    "check_id",
    "severity",
    "table_name",
    "column_name",
    "row_identifier",
    "issue_type",
    "message",
    "affected_rows",
    "sample_values",
    "remediation_hint",
]


def _issue_rows(issues: list[QualityIssue]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for issue in issues:
        row = issue.to_dict()
        row["sample_values"] = json.dumps(
            row["sample_values"], ensure_ascii=False, sort_keys=True
        )
        rows.append(row)
    return rows


def _markdown(report: QualityReport) -> str:
    lines = [
        "# DeliveryPulse data quality report",
        "",
        f"- Status: **{report.status.value}**",
        f"- Checked at: `{report.checked_at}`",
        f"- Input: `{report.input_dir}`",
        f"- Checks executed: {report.checks_run}",
        (
            f"- Findings: critical {report.critical_count}, error "
            f"{report.error_count}, warning {report.warning_count}, "
            f"info {report.info_count}"
        ),
        "",
        "## Row counts",
        "",
        "| Table | Rows |",
        "|---|---:|",
    ]
    lines.extend(f"| {table} | {count} |" for table, count in report.row_counts.items())
    lines.extend(
        [
            "",
            "## Completeness",
            "",
            "| Scope | Rate |",
            "|---|---:|",
        ]
    )
    lines.extend(
        f"| {scope} | {rate:.2%} |"
        for scope, rate in report.completeness_metrics.items()
    )
    lines.extend(["", "## Findings by severity", ""])
    for severity in ("critical", "error", "warning", "info"):
        count = sum(issue.severity.value == severity for issue in report.issues)
        lines.append(f"- {severity}: {count}")
    lines.extend(["", "## Findings by table", ""])
    if report.issues:
        by_table: dict[str, int] = {}
        for issue in report.issues:
            by_table[issue.table_name] = by_table.get(issue.table_name, 0) + 1
        lines.extend(f"- {table}: {count}" for table, count in sorted(by_table.items()))
    else:
        lines.append("No violations were detected.")
    lines.extend(["", "## Examples and recommendations", ""])
    for issue in report.issues[:20]:
        examples = ", ".join(issue.sample_values) or "no row sample"
        lines.extend(
            [
                f"### {issue.severity.value}: {issue.issue_type}",
                "",
                f"{issue.message} Affected rows: {issue.affected_rows}.",
                "",
                f"Examples: `{examples}`",
                "",
                f"Recommendation: {issue.remediation_hint}",
                "",
            ]
        )
    lines.extend(
        [
            "## Limitations",
            "",
            "- The validator does not read `quality_issues_manifest.csv`.",
            "- Statistical rarity alone is not treated as proof of an error.",
            "- Raw CSV files are never corrected or overwritten.",
            "- Driver and vehicle overlap findings are warnings because the first "
            "release has no availability calendar.",
            "",
        ]
    )
    return "\n".join(lines)


def write_reports(
    report: QualityReport,
    profiles: pd.DataFrame,
    output_dir: Path,
    profile_format: str = "csv",
) -> dict[str, Path]:
    """Write canonical reports without touching the input directory."""
    destination = output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    summary_path = destination / "quality_summary.json"
    issues_path = destination / "quality_issues.csv"
    markdown_path = destination / "quality_report.md"
    profiles_path = destination / "table_profiles.csv"
    summary_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding=CONFIG.encoding,
    )
    with issues_path.open("w", encoding=CONFIG.encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ISSUE_COLUMNS)
        writer.writeheader()
        writer.writerows(_issue_rows(report.issues))
    markdown_path.write_text(_markdown(report), encoding=CONFIG.encoding)
    profiles.to_csv(
        profiles_path,
        index=False,
        encoding=CONFIG.encoding,
        lineterminator="\n",
    )
    paths = {
        "summary": summary_path,
        "issues": issues_path,
        "markdown": markdown_path,
        "profiles": profiles_path,
    }
    if profile_format == "json":
        json_path = destination / "table_profiles.json"
        json_path.write_text(
            profiles.to_json(orient="records", force_ascii=False, indent=2) + "\n",
            encoding=CONFIG.encoding,
        )
        paths["profiles_json"] = json_path
    return paths
