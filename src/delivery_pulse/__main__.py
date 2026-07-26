"""Command-line entry point for DeliveryPulse."""

from __future__ import annotations

import argparse
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

    raise AssertionError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
