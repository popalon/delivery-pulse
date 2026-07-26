"""Read-only orchestration for evidence-gated recommendations."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from time import perf_counter

import pandas as pd

from delivery_pulse.analysis.loader import AnalysisLoadError, load_context
from delivery_pulse.recommendations.catalog import build_recommendations
from delivery_pulse.recommendations.evidence import validate_hypothesis_results
from delivery_pulse.recommendations.models import (
    RecommendationConfig,
    RecommendationRunResult,
)
from delivery_pulse.recommendations.reporting import build_figures, write_outputs
from delivery_pulse.recommendations.scenarios import (
    calculate_scenarios,
    load_scenario_assumptions,
)

EXPECTED_PROTOCOL_HASH = (
    "81c2883a8589966d1a7f2412dbfc052bdd70626969155bc1b4b0b263d9dfaedf"
)
EXPECTED_OUTPUTS = (
    "recommendations.json",
    "recommendation_scores.csv",
    "scenario_analysis.csv",
    "pilot_plan.csv",
    "decision_register.csv",
    "recommendations_report.md",
)


class RecommendationError(RuntimeError):
    """Raised when recommendation inputs cannot be trusted."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _find_protocol(database: Path) -> Path:
    """Find repository protocol without encoding a machine path."""
    candidates = (
        Path.cwd() / "docs" / "hypothesis_protocol.md",
        database.parent.parent.parent / "docs" / "hypothesis_protocol.md",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RecommendationError("hypothesis protocol file is unavailable")


def run_recommendations(config: RecommendationConfig) -> RecommendationRunResult:
    """Validate immutable inputs, build cards, scenarios, reports, and figures."""
    started = perf_counter()
    if config.top_n <= 0:
        raise RecommendationError("top_n must be positive")
    existing = [
        config.output_dir / name
        for name in EXPECTED_OUTPUTS
        if (config.output_dir / name).exists()
    ]
    if existing and not config.force:
        raise RecommendationError("output artifacts already exist; pass --force")
    summary_path = config.hypothesis_results_dir / "hypothesis_summary.json"
    results_path = config.hypothesis_results_dir / "hypothesis_results.csv"
    if not summary_path.is_file() or not results_path.is_file():
        raise RecommendationError(
            "hypothesis_summary.json and hypothesis_results.csv are required"
        )
    try:
        context = load_context(config.database)
    except AnalysisLoadError as error:
        raise RecommendationError(str(error)) from error
    if context.metadata.get("profile") != "full":
        raise RecommendationError("recommendations require a validated full warehouse")
    protocol = _find_protocol(config.database)
    if _sha256(protocol) != EXPECTED_PROTOCOL_HASH:
        raise RecommendationError(
            "hypothesis protocol hash does not match the frozen protocol"
        )
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        results = pd.read_csv(results_path)
        metadata = summary["metadata"]
        if metadata.get("profile") != "full" or int(metadata.get("seed")) != 42:
            raise RecommendationError(
                "hypothesis results must use full profile and seed 42"
            )
        hypotheses = validate_hypothesis_results(results)
        items = build_recommendations(hypotheses)
        scenarios = calculate_scenarios(
            load_scenario_assumptions(config.scenario_config)
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        if isinstance(error, RecommendationError):
            raise
        raise RecommendationError(f"invalid recommendation input: {error}") from error
    figures = build_figures(items, scenarios, config.output_dir / "figures")
    paths = write_outputs(
        config.output_dir,
        items[: config.top_n],
        scenarios,
        figures,
        protocol_hash=EXPECTED_PROTOCOL_HASH,
    )
    paths.update({f"figure_{name}": path for name, path in figures.items()})
    return RecommendationRunResult(
        items[: config.top_n],
        paths,
        perf_counter() - started,
        any(item.evidence_level == "insufficient_evidence" for item in items),
    )
