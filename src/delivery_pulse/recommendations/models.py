"""Typed models for recommendation artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

EvidenceLevel = Literal[
    "strong_observational_evidence",
    "moderate_or_secondary_evidence",
    "descriptive_only",
    "insufficient_evidence",
]
ActionType = Literal[
    "implement", "pilot", "monitor", "collect_more_data", "do_not_act_yet"
]


@dataclass(frozen=True, slots=True)
class Recommendation:
    """One evidence-gated management recommendation."""

    recommendation_id: str
    title: str
    business_area: str
    problem_statement: str
    evidence_level: EvidenceLevel
    supporting_hypotheses: tuple[str, ...]
    supporting_metrics: tuple[str, ...]
    observed_effect: str
    uncertainty: str
    recommended_action: str
    action_type: ActionType
    expected_direction: str
    expected_benefit: str
    implementation_effort: int
    operational_risk: int
    confidence: int
    priority_score: float
    priority: str
    owner_role: str
    target_kpis: tuple[str, ...]
    guardrail_metrics: tuple[str, ...]
    pilot_design: str
    review_period: str
    stop_conditions: str
    limitations: str

    def to_dict(self) -> dict[str, object]:
        """Return a serializable deterministic row."""
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RecommendationConfig:
    """Inputs and output controls for one recommendation run."""

    database: Path
    hypothesis_results_dir: Path
    output_dir: Path
    scenario_config: Path | None = None
    top_n: int = 6
    force: bool = False


@dataclass(frozen=True, slots=True)
class RecommendationRunResult:
    """Artifacts and status produced by the pipeline."""

    recommendations: tuple[Recommendation, ...]
    output_paths: dict[str, Path]
    elapsed_seconds: float
    has_insufficient_evidence: bool
