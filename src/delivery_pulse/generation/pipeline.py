"""End-to-end synthetic dataset generation pipeline."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from delivery_pulse import __version__
from delivery_pulse.config import CONFIG
from delivery_pulse.generation.config import GenerationConfig
from delivery_pulse.generation.customers import generate_customers
from delivery_pulse.generation.deliveries import generate_deliveries
from delivery_pulse.generation.drivers import generate_drivers
from delivery_pulse.generation.events import generate_route_events
from delivery_pulse.generation.maintenance import (
    generate_initial_maintenance,
    generate_period_maintenance,
)
from delivery_pulse.generation.orders import generate_orders
from delivery_pulse.generation.profiles import get_profile
from delivery_pulse.generation.quality_issues import inject_quality_issues
from delivery_pulse.generation.random_state import create_random_state
from delivery_pulse.generation.routes import generate_routes
from delivery_pulse.generation.schemas import TABLE_COLUMNS
from delivery_pulse.generation.vehicles import generate_vehicles
from delivery_pulse.paths import get_project_paths

GENERATOR_VERSION = "1"


class ExistingDataError(FileExistsError):
    """Raised when generation would overwrite an existing artifact."""


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Generated tables and their persisted artifact locations."""

    tables: dict[str, pd.DataFrame]
    output_dir: Path
    metadata_dir: Path
    metadata: dict[str, object]
    quality_manifest: pd.DataFrame | None


def _resolve_directories(config: GenerationConfig) -> tuple[Path, Path]:
    if config.output_dir is None:
        paths = get_project_paths()
        return paths.data_raw, paths.data_metadata
    output_dir = config.output_dir.resolve()
    return output_dir, output_dir.parent / "metadata"


def _artifact_paths(
    output_dir: Path,
    metadata_dir: Path,
    inject_issues: bool,
) -> list[Path]:
    paths = [output_dir / f"{name}.csv" for name in TABLE_COLUMNS]
    paths.append(metadata_dir / "metadata.json")
    if inject_issues:
        paths.append(metadata_dir / "quality_issues_manifest.csv")
    return paths


def _ensure_writable(targets: list[Path], force: bool) -> None:
    existing = [path for path in targets if path.exists()]
    if existing and not force:
        formatted = ", ".join(str(path) for path in existing)
        raise ExistingDataError(
            f"generation would overwrite existing files: {formatted}; use --force"
        )


def _write_csv(table: pd.DataFrame, path: Path) -> None:
    table.to_csv(
        path,
        index=False,
        encoding=CONFIG.encoding,
        lineterminator="\n",
        date_format="%Y-%m-%dT%H:%M:%SZ",
        float_format="%.2f",
    )


def generate_dataset(config: GenerationConfig) -> GenerationResult:
    """Generate, validate structurally, and persist all DeliveryPulse tables."""
    config.validate()
    profile = get_profile(config.profile)
    orders_count = config.resolved_orders()
    output_dir, metadata_dir = _resolve_directories(config)
    targets = _artifact_paths(output_dir, metadata_dir, config.inject_quality_issues)
    _ensure_writable(targets, config.force)
    rng = create_random_state(config.seed)

    customers = generate_customers(profile.customers, config.start_date, rng)
    routes = generate_routes(profile.routes, rng)
    drivers = generate_drivers(profile.drivers, config.start_date, rng)
    vehicles = generate_vehicles(profile.vehicles, config.start_date, rng)
    initial_maintenance = generate_initial_maintenance(vehicles, config.start_date, rng)
    orders = generate_orders(
        orders_count,
        config.start_date,
        config.months,
        customers,
        routes,
        rng,
    )
    deliveries, orders, signals = generate_deliveries(
        orders,
        customers,
        routes,
        drivers,
        vehicles,
        initial_maintenance,
        config.start_date,
        rng,
    )
    route_events = generate_route_events(deliveries, orders, routes, signals, rng)
    maintenance = generate_period_maintenance(
        initial_maintenance,
        vehicles,
        deliveries,
        route_events,
        config.start_date,
        config.months,
        rng,
    )
    tables = {
        "customers": customers,
        "routes": routes,
        "drivers": drivers,
        "vehicles": vehicles,
        "orders": orders,
        "deliveries": deliveries,
        "route_events": route_events,
        "maintenance": maintenance,
    }
    for name, columns in TABLE_COLUMNS.items():
        tables[name] = tables[name].loc[:, columns]

    quality_manifest: pd.DataFrame | None = None
    if config.inject_quality_issues:
        tables, quality_manifest = inject_quality_issues(tables, rng)

    output_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        _write_csv(table, output_dir / f"{name}.csv")
    if quality_manifest is not None:
        _write_csv(
            quality_manifest,
            metadata_dir / "quality_issues_manifest.csv",
        )

    created_files = [f"raw/{name}.csv" for name in TABLE_COLUMNS]
    created_files.append("metadata/metadata.json")
    if quality_manifest is not None:
        created_files.append("metadata/quality_issues_manifest.csv")
    parameters = {
        "business_timezone": CONFIG.business_timezone,
        "currency_code": CONFIG.currency_code,
        "generator_version": GENERATOR_VERSION,
        "inject_quality_issues": config.inject_quality_issues,
    }
    metadata: dict[str, object] = {
        "seed": config.seed,
        "profile": config.profile,
        "start_date": config.start_date.isoformat(),
        "months": config.months,
        "requested_orders": orders_count,
        "row_counts": {name: len(table) for name, table in tables.items()},
        "project_version": __version__,
        "created_files": created_files,
        "parameters": parameters,
    }
    metadata_path = metadata_dir / "metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding=CONFIG.encoding,
    )
    return GenerationResult(
        tables=tables,
        output_dir=output_dir,
        metadata_dir=metadata_dir,
        metadata=metadata,
        quality_manifest=quality_manifest,
    )


def config_as_metadata(config: GenerationConfig) -> dict[str, object]:
    """Return a JSON-compatible view useful for diagnostics."""
    values = asdict(config)
    values["start_date"] = config.start_date.isoformat()
    values["output_dir"] = str(config.output_dir) if config.output_dir else None
    return values
