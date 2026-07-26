"""Orchestration of the pre-registered hypothesis protocol."""

from __future__ import annotations

from dataclasses import replace
from time import perf_counter

import pandas as pd

from delivery_pulse.analysis.loader import AnalysisLoadError, load_context
from delivery_pulse.hypotheses.datasets import (
    load_delivery_dataset,
    load_vehicle_month_dataset,
)
from delivery_pulse.hypotheses.feasibility import assess_feasibility
from delivery_pulse.hypotheses.h1_loading_delay import run_h1
from delivery_pulse.hypotheses.h2_express import run_h2
from delivery_pulse.hypotheses.h3_breakdown_profit import run_h3
from delivery_pulse.hypotheses.h4_vehicle_reliability import run_h4
from delivery_pulse.hypotheses.h5_customer_margin import run_h5
from delivery_pulse.hypotheses.h6_overload import run_h6
from delivery_pulse.hypotheses.models import (
    HypothesisConfig,
    HypothesisResult,
    HypothesisRunResult,
    ModelOutput,
)
from delivery_pulse.hypotheses.multiple_testing import benjamini_hochberg
from delivery_pulse.hypotheses.reporting import build_figures, write_outputs

SUPPORTED_IDS = ("H1", "H2", "H3", "H4", "H5", "H6")
EXPECTED_ARTIFACTS = (
    "hypothesis_summary.json",
    "hypothesis_results.csv",
    "model_coefficients.csv",
    "model_diagnostics.csv",
    "hypothesis_report.md",
)


class HypothesisError(RuntimeError):
    """Raised when the hypothesis pipeline cannot run safely."""


def _validate_config(config: HypothesisConfig) -> None:
    if not 0 < config.alpha < 1:
        raise HypothesisError("alpha must be between 0 and 1")
    if config.min_group_size <= 0:
        raise HypothesisError("min_group_size must be positive")
    unknown = sorted(set(config.hypotheses) - set(SUPPORTED_IDS))
    if unknown:
        raise HypothesisError(f"unknown hypothesis IDs: {', '.join(unknown)}")
    existing = [
        config.output_dir / name
        for name in EXPECTED_ARTIFACTS
        if (config.output_dir / name).exists()
    ]
    if existing and not config.force:
        raise HypothesisError(
            "output artifacts already exist; pass --force to overwrite them"
        )


def _apply_primary_bh(
    results: list[HypothesisResult],
    *,
    alpha: float,
) -> list[HypothesisResult]:
    adjusted = benjamini_hochberg([result.p_value for result in results])
    final: list[HypothesisResult] = []
    for result, corrected in zip(results, adjusted, strict=True):
        status = result.status
        if status != "inconclusive":
            status = (
                "supported"
                if corrected is not None
                and corrected < alpha
                and result.practically_significant
                else "not_supported"
            )
        final.append(
            replace(
                result,
                p_value_adjusted=corrected,
                status=status,
            )
        )
    return final


def run_hypotheses(config: HypothesisConfig) -> HypothesisRunResult:
    """Run feasibility, pre-specified models, BH, figures, and reports."""
    _validate_config(config)
    started = perf_counter()
    try:
        context = load_context(config.database)
        delivery = load_delivery_dataset(context.database)
        vehicle_month = load_vehicle_month_dataset(context.database)
    except AnalysisLoadError as error:
        raise HypothesisError(str(error)) from error
    feasibility = assess_feasibility(
        delivery,
        vehicle_month,
        min_group_size=config.min_group_size,
    )
    feasibility_by_id = {item.hypothesis_id: item for item in feasibility}
    runners = {
        "H1": lambda: run_h1(delivery, feasibility_by_id["H1"]),
        "H2": lambda: run_h2(delivery, feasibility_by_id["H2"]),
        "H3": lambda: run_h3(delivery, feasibility_by_id["H3"]),
        "H4": lambda: run_h4(vehicle_month, feasibility_by_id["H4"]),
        "H5": lambda: run_h5(
            delivery,
            feasibility_by_id["H5"],
            min_group_size=config.min_group_size,
            alpha=config.alpha,
        ),
        "H6": lambda: run_h6(delivery, feasibility_by_id["H6"]),
    }
    outputs: list[ModelOutput] = []
    for hypothesis_id in SUPPORTED_IDS:
        if hypothesis_id in config.hypotheses:
            outputs.append(runners[hypothesis_id]())
    results = _apply_primary_bh(
        [output.result for output in outputs],
        alpha=config.alpha,
    )
    coefficients = pd.concat(
        [output.coefficients for output in outputs if not output.coefficients.empty],
        ignore_index=True,
    )
    diagnostics = pd.concat(
        [output.diagnostics for output in outputs if not output.diagnostics.empty],
        ignore_index=True,
    )
    figure_dir = config.output_dir / "figures"
    figures = build_figures(results, coefficients, diagnostics, figure_dir)
    metadata = {
        "profile": context.metadata["profile"],
        "seed": context.metadata["seed"],
        "start_date": context.metadata["start_date"],
        "months": context.metadata["months"],
        "alpha": config.alpha,
        "analysis_seed": config.seed,
        "min_group_size": config.min_group_size,
    }
    paths = write_outputs(
        config.output_dir,
        results,
        feasibility,
        coefficients,
        diagnostics,
        figures,
        metadata,
    )
    paths.update({f"figure_{name}": path for name, path in figures.items()})
    return HypothesisRunResult(
        tuple(results),
        feasibility,
        coefficients,
        diagnostics,
        paths,
        perf_counter() - started,
        any(result.status == "inconclusive" for result in results),
    )
