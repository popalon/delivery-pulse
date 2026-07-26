"""Command-line entry point for DeliveryPulse."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from delivery_pulse import PROJECT_NAME, __version__
from delivery_pulse.config import CONFIG
from delivery_pulse.paths import (
    ProjectPaths,
    create_local_directories,
    get_project_paths,
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

    raise AssertionError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
