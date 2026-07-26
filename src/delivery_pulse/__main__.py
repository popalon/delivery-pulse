"""Command-line entry point for DeliveryPulse."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import cast

from delivery_pulse import PROJECT_NAME, __version__
from delivery_pulse.config import CONFIG
from delivery_pulse.generation import GenerationConfig, generate_dataset
from delivery_pulse.generation.pipeline import ExistingDataError
from delivery_pulse.paths import (
    ProjectPaths,
    create_local_directories,
    get_project_paths,
)
from delivery_pulse.quality import QualityRunError, run_quality
from delivery_pulse.quality.pipeline import should_fail
from delivery_pulse.warehouse import (
    BuildConfig,
    WarehouseError,
    build_warehouse,
    get_baseline_metrics,
    get_warehouse_info,
    validate_warehouse,
)


def _add_root_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Project root override (defaults to the detected repository root).",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="delivery_pulse")
    subparsers = parser.add_subparsers(dest="command", required=True)

    info_parser = subparsers.add_parser("info", help="Show project information.")
    _add_root_argument(info_parser)

    init_parser = subparsers.add_parser(
        "init",
        help="Create local working directories without overwriting their contents.",
    )
    _add_root_argument(init_parser)

    generate_parser = subparsers.add_parser(
        "generate",
        help="Generate deterministic synthetic logistics CSV files.",
    )
    generate_parser.add_argument("--orders", type=int, default=None)
    generate_parser.add_argument("--seed", type=int, default=CONFIG.default_seed)
    generate_parser.add_argument(
        "--start-date",
        type=date.fromisoformat,
        default=date(2024, 1, 1),
        metavar="YYYY-MM-DD",
    )
    generate_parser.add_argument("--months", type=int, default=12)
    generate_parser.add_argument("--output-dir", type=Path, default=None)
    generate_parser.add_argument(
        "--profile",
        choices=["test", "demo", "full"],
        default="full",
    )
    generate_parser.add_argument(
        "--inject-quality-issues",
        action="store_true",
    )
    generate_parser.add_argument("--force", action="store_true")

    quality_parser = subparsers.add_parser(
        "quality",
        help="Validate raw CSV files and create quality reports.",
    )
    quality_parser.add_argument("--input-dir", type=Path, default=None)
    quality_parser.add_argument("--output-dir", type=Path, default=None)
    quality_parser.add_argument(
        "--format",
        dest="profile_format",
        choices=["csv", "json"],
        default="csv",
        help="Table profile format; canonical reports are always created.",
    )
    quality_parser.add_argument(
        "--fail-on",
        choices=["critical", "error", "warning"],
        default="error",
    )
    quality_parser.add_argument("--max-samples", type=int, default=5)

    warehouse_parser = subparsers.add_parser(
        "warehouse",
        help="Build, validate, and inspect the local DuckDB warehouse.",
    )
    warehouse_actions = warehouse_parser.add_subparsers(
        dest="warehouse_action",
        required=True,
    )
    build_parser = warehouse_actions.add_parser("build")
    build_parser.add_argument("--input-dir", type=Path, default=None)
    build_parser.add_argument("--database", type=Path, default=None)
    build_parser.add_argument("--force", action="store_true")
    build_parser.add_argument("--skip-quality-check", action="store_true")
    build_parser.add_argument("--allow-warnings", action="store_true")
    for action in ("validate", "info", "baseline"):
        action_parser = warehouse_actions.add_parser(action)
        action_parser.add_argument("--database", type=Path, default=None)

    eda_parser = subparsers.add_parser(
        "eda",
        help="Run reproducible descriptive analysis on a validated warehouse.",
    )
    eda_parser.add_argument("--database", type=Path, default=None)
    eda_parser.add_argument("--output-dir", type=Path, default=None)
    eda_parser.add_argument("--top-n", type=int, default=10)
    eda_parser.add_argument("--min-group-size", type=int, default=30)
    eda_parser.add_argument(
        "--format",
        dest="report_format",
        choices=["markdown"],
        default="markdown",
    )

    hypotheses_parser = subparsers.add_parser(
        "hypotheses",
        help="Run the pre-registered formal hypothesis protocol.",
    )
    hypothesis_actions = hypotheses_parser.add_subparsers(
        dest="hypotheses_action",
        required=True,
    )
    hypothesis_actions.add_parser("info")
    run_parser = hypothesis_actions.add_parser("run")
    run_parser.add_argument("--database", type=Path, default=None)
    run_parser.add_argument("--output-dir", type=Path, default=None)
    run_parser.add_argument("--alpha", type=float, default=0.05)
    run_parser.add_argument("--seed", type=int, default=CONFIG.default_seed)
    run_parser.add_argument("--min-group-size", type=int, default=90)
    run_parser.add_argument(
        "--hypotheses",
        nargs="+",
        default=["H1", "H2", "H3", "H4", "H5", "H6"],
    )
    run_parser.add_argument("--force", action="store_true")
    return parser


def _print_info(paths: ProjectPaths) -> None:
    print(f"Project: {PROJECT_NAME}")
    print(f"Version: {__version__}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Project root: {paths.root}")
    print(f"Business timezone: {CONFIG.business_timezone}")
    print(f"Currency: {CONFIG.currency_code}")
    print("Directories:")
    for directory in paths.local_directories():
        status = "available" if directory.is_dir() else "missing"
        print(f"  {directory.relative_to(paths.root)}: {status}")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the DeliveryPulse command-line interface."""
    args = _build_parser().parse_args(argv)

    if args.command == "info":
        _print_info(get_project_paths(args.root))
        return 0

    if args.command == "init":
        paths = create_local_directories(args.root)
        print(f"Local directories are ready under: {paths.root}")
        return 0

    if args.command == "generate":
        config = GenerationConfig(
            profile=args.profile,
            orders=args.orders,
            seed=args.seed,
            start_date=args.start_date,
            months=args.months,
            output_dir=args.output_dir,
            inject_quality_issues=args.inject_quality_issues,
            force=args.force,
        )
        try:
            result = generate_dataset(config)
        except (ExistingDataError, ValueError) as error:
            print(f"Generation failed: {error}", file=sys.stderr)
            return 2
        print(f"Generated data: {result.output_dir}")
        print(f"Metadata: {result.metadata_dir / 'metadata.json'}")
        row_counts = cast(dict[str, int], result.metadata["row_counts"])
        for table_name, row_count in row_counts.items():
            print(f"  {table_name}: {row_count}")
        return 0

    if args.command == "quality":
        project_paths = get_project_paths()
        input_dir = args.input_dir or project_paths.data_raw
        output_dir = args.output_dir or project_paths.reports_quality
        try:
            report, _, report_paths = run_quality(
                input_dir,
                output_dir,
                max_samples=args.max_samples,
                profile_format=args.profile_format,
            )
            failed = should_fail(report, args.fail_on)
        except QualityRunError as error:
            print(f"Quality run failed to start: {error}", file=sys.stderr)
            return 2
        print(f"Quality status: {report.status.value}")
        print(
            "Findings: "
            f"critical={report.critical_count}, "
            f"error={report.error_count}, "
            f"warning={report.warning_count}, "
            f"info={report.info_count}"
        )
        print(f"Report: {report_paths['markdown']}")
        return 1 if failed else 0

    if args.command == "warehouse":
        project_paths = get_project_paths()
        default_database = project_paths.data_processed / "delivery_pulse.duckdb"
        database = args.database or default_database
        try:
            if args.warehouse_action == "build":
                input_dir = args.input_dir or project_paths.data_raw
                warehouse_result = build_warehouse(
                    BuildConfig(
                        input_dir=input_dir,
                        database=database,
                        force=args.force,
                        skip_quality_check=args.skip_quality_check,
                        allow_warnings=args.allow_warnings,
                    )
                )
                print(f"Warehouse built: {warehouse_result.database}")
                print(f"Quality status: {warehouse_result.quality_status}")
                if (
                    warehouse_result.quality_status == "passed_with_warnings"
                    and not args.allow_warnings
                ):
                    print(
                        "Warning: build continued because warnings are "
                        "non-blocking; review the quality report."
                    )
                validation_label = (
                    "passed" if warehouse_result.validation.passed else "failed"
                )
                print(f"Validation: {validation_label}")
                print(f"Build time: {warehouse_result.elapsed_seconds:.3f} seconds")
                return 0
            if args.warehouse_action == "validate":
                warehouse_report = validate_warehouse(database)
                for check in warehouse_report.checks:
                    label = "PASS" if check.passed else "FAIL"
                    print(f"[{label}] {check.check_id}: {check.message}")
                return 0 if warehouse_report.passed else 1
            if args.warehouse_action == "info":
                print(
                    json.dumps(
                        get_warehouse_info(database),
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
                )
                return 0
            if args.warehouse_action == "baseline":
                print(
                    json.dumps(
                        get_baseline_metrics(database),
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    )
                )
                return 0
        except WarehouseError as error:
            print(f"Warehouse command failed: {error}", file=sys.stderr)
            if "quality" in str(error).lower() or args.warehouse_action == "validate":
                return 1
            return 2

    if args.command == "eda":
        from delivery_pulse.analysis import AnalysisError, run_eda

        project_paths = get_project_paths()
        database = (
            args.database or project_paths.data_processed / "delivery_pulse.duckdb"
        )
        output_dir = args.output_dir or project_paths.root / "reports"
        try:
            eda_result = run_eda(
                database,
                output_dir,
                top_n=args.top_n,
                min_group_size=args.min_group_size,
                report_format=args.report_format,
            )
        except AnalysisError as error:
            print(f"EDA failed: {error}", file=sys.stderr)
            return 2
        print(f"EDA report: {eda_result.report_path}")
        print(f"Figures: {len(eda_result.figures)}")
        print(f"Elapsed: {eda_result.elapsed_seconds:.3f} seconds")
        return 0

    if args.command == "hypotheses":
        if args.hypotheses_action == "info":
            print("Protocol: docs/hypothesis_protocol.md")
            print("Primary hypotheses: H1 H2 H3 H4 H5 H6")
            print("Alpha: 0.05; confidence level: 95%; correction: BH")
            return 0
        from delivery_pulse.hypotheses import (
            HypothesisConfig,
            HypothesisError,
            run_hypotheses,
        )

        project_paths = get_project_paths()
        database = (
            args.database or project_paths.data_processed / "delivery_pulse.duckdb"
        )
        output_dir = args.output_dir or project_paths.root / "reports" / "hypotheses"
        try:
            hypothesis_result = run_hypotheses(
                HypothesisConfig(
                    database=database,
                    output_dir=output_dir,
                    alpha=args.alpha,
                    seed=args.seed,
                    min_group_size=args.min_group_size,
                    hypotheses=tuple(
                        hypothesis_id.upper() for hypothesis_id in args.hypotheses
                    ),
                    force=args.force,
                )
            )
        except HypothesisError as error:
            print(f"Hypothesis run failed: {error}", file=sys.stderr)
            return 2
        for hypothesis in hypothesis_result.results:
            print(
                f"{hypothesis.hypothesis_id}: {hypothesis.status}; "
                f"n={hypothesis.observations}; events={hypothesis.events}; "
                f"BH p={hypothesis.p_value_adjusted}"
            )
        print(f"Report: {hypothesis_result.output_paths['report']}")
        print(f"Elapsed: {hypothesis_result.elapsed_seconds:.3f} seconds")
        return 1 if hypothesis_result.has_inconclusive else 0

    raise AssertionError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
