"""Typed models shared by hypothesis tests and reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

import pandas as pd

HypothesisStatus = Literal["supported", "not_supported", "inconclusive"]


@dataclass(frozen=True, slots=True)
class HypothesisConfig:
    """Configuration fixed for one hypothesis pipeline run."""

    database: Path
    output_dir: Path
    alpha: float = 0.05
    seed: int = 42
    min_group_size: int = 90
    hypotheses: tuple[str, ...] = ("H1", "H2", "H3", "H4", "H5", "H6")
    force: bool = False


@dataclass(slots=True)
class FeasibilityResult:
    """Pre-model sample sufficiency assessment."""

    hypothesis_id: str
    feasible: bool
    observations: int
    events: int
    exposed: int
    unexposed: int
    exposed_events: int
    missing_rate: float
    estimated_parameters: int
    events_per_parameter: float | None
    reason: str


@dataclass(slots=True)
class HypothesisResult:
    """One primary hypothesis result before and after BH correction."""

    hypothesis_id: str
    title: str
    observations: int
    events: int
    exposed: int
    unexposed: int
    missing_rate: float
    unadjusted_effect_name: str
    unadjusted_effect: float | None
    unadjusted_ci_low: float | None
    unadjusted_ci_high: float | None
    adjusted_effect_name: str
    adjusted_effect: float | None
    adjusted_ci_low: float | None
    adjusted_ci_high: float | None
    adjusted_risk_difference: float | None
    risk_difference_ci_low: float | None
    risk_difference_ci_high: float | None
    p_value: float | None
    p_value_adjusted: float | None
    practically_significant: bool
    status: HypothesisStatus
    method: str
    notes: str

    def to_dict(self) -> dict[str, object]:
        """Return a JSON/CSV-safe representation."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ModelOutput:
    """A hypothesis result plus coefficient and diagnostic rows."""

    result: HypothesisResult
    coefficients: pd.DataFrame
    diagnostics: pd.DataFrame


@dataclass(frozen=True, slots=True)
class HypothesisRunResult:
    """All deterministic artifacts created by the pipeline."""

    results: tuple[HypothesisResult, ...]
    feasibility: tuple[FeasibilityResult, ...]
    coefficients: pd.DataFrame
    diagnostics: pd.DataFrame
    output_paths: dict[str, Path]
    elapsed_seconds: float
    has_inconclusive: bool
