"""Configuration contract for synthetic data generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from delivery_pulse.config import CONFIG
from delivery_pulse.generation.profiles import get_profile


@dataclass(frozen=True, slots=True)
class GenerationConfig:
    """Validated parameters that fully determine a generated dataset."""

    profile: str = "full"
    orders: int | None = None
    seed: int = CONFIG.default_seed
    start_date: date = date(2024, 1, 1)
    months: int = 12
    output_dir: Path | None = None
    inject_quality_issues: bool = False
    force: bool = False

    def resolved_orders(self) -> int:
        """Return the explicit order count or the selected profile default."""
        return (
            self.orders if self.orders is not None else get_profile(self.profile).orders
        )

    def validate(self) -> None:
        """Raise ValueError when generation parameters are invalid."""
        get_profile(self.profile)
        if self.resolved_orders() <= 0:
            raise ValueError("orders must be a positive integer")
        if self.months <= 0:
            raise ValueError("months must be a positive integer")
