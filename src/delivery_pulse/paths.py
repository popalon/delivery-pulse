"""Cross-platform project path definitions."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    """Paths used by DeliveryPulse within one project root."""

    root: Path
    data_raw: Path
    data_processed: Path
    data_marts: Path
    data_metadata: Path
    notebooks: Path
    reports_figures: Path
    sql: Path

    def local_directories(self) -> tuple[Path, ...]:
        """Return directories that the local workflow expects to exist."""
        return (
            self.data_raw,
            self.data_processed,
            self.data_marts,
            self.data_metadata,
            self.notebooks,
            self.reports_figures,
            self.sql,
        )


def get_project_root() -> Path:
    """Return the project root inferred from the src-layout package location."""
    return Path(__file__).resolve().parents[2]


def get_project_paths(project_root: Path | None = None) -> ProjectPaths:
    """Build project paths without creating directories."""
    root = (project_root if project_root is not None else get_project_root()).resolve()
    data = root / "data"
    return ProjectPaths(
        root=root,
        data_raw=data / "raw",
        data_processed=data / "processed",
        data_marts=data / "marts",
        data_metadata=data / "metadata",
        notebooks=root / "notebooks",
        reports_figures=root / "reports" / "figures",
        sql=root / "sql",
    )


def create_local_directories(project_root: Path | None = None) -> ProjectPaths:
    """Create local working directories safely and return their paths."""
    paths = get_project_paths(project_root)
    for directory in paths.local_directories():
        directory.mkdir(parents=True, exist_ok=True)
    return paths
