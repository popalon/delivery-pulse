"""Tests for cross-platform path handling."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from delivery_pulse.paths import (
    create_local_directories,
    get_project_paths,
    get_project_root,
)


def test_project_root_is_detected_correctly() -> None:
    expected_root = Path(__file__).resolve().parents[1]

    assert get_project_root() == expected_root
    assert (get_project_root() / "pyproject.toml").is_file()


def test_paths_are_inside_project_and_have_no_hardcoded_home() -> None:
    paths = get_project_paths()

    for path in paths.local_directories():
        assert path.is_relative_to(paths.root)

    source = Path(__file__).resolve().parents[1] / "src" / "delivery_pulse" / "paths.py"
    source_text = source.read_text(encoding="utf-8")
    assert "/home/" not in source_text
    assert "popalon" not in source_text.lower()


def test_create_local_directories_is_idempotent(tmp_path: Path) -> None:
    first = create_local_directories(tmp_path)
    marker = first.data_raw / "keep-me.txt"
    marker.write_text("existing data", encoding="utf-8")

    second = create_local_directories(tmp_path)

    assert first == second
    assert marker.read_text(encoding="utf-8") == "existing data"
    assert all(path.is_dir() for path in second.local_directories())


def test_cli_init_creates_directories_in_temporary_root(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "delivery_pulse",
            "init",
            "--root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert all(
        path.is_dir() for path in get_project_paths(tmp_path).local_directories()
    )
