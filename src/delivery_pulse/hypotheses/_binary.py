"""Shared implementation for pre-specified binary GLM hypotheses."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from delivery_pulse.hypotheses.diagnostics import (
    PerfectSeparationError,
    binary_risk_difference,
    capture_model_fit,
    coefficient_rows,
    model_diagnostic_rows,
    standardized_risk_difference,
)
from delivery_pulse.hypotheses.models import (
    FeasibilityResult,
    HypothesisResult,
    HypothesisStatus,
    ModelOutput,
)


def fit_binary_hypothesis(
    frame: pd.DataFrame,
    feasibility: FeasibilityResult,
    *,
    hypothesis_id: str,
    title: str,
    formula: str,
    outcome: str,
    exposure: str,
    practical_threshold: float,
    alternative: Callable[[float], bool],
) -> ModelOutput:
    """Fit one robust binomial GLM with crude and standardized effects."""
    empty = pd.DataFrame()
    if not feasibility.feasible:
        return ModelOutput(
            HypothesisResult(
                hypothesis_id,
                title,
                feasibility.observations,
                feasibility.events,
                feasibility.exposed,
                feasibility.unexposed,
                feasibility.missing_rate,
                "risk_difference",
                None,
                None,
                None,
                "odds_ratio",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                False,
                "inconclusive",
                "Binomial GLM with HC3",
                feasibility.reason,
            ),
            empty,
            empty,
        )
    modeling = frame.dropna(
        subset=[outcome, exposure, "distance_planned_1000km"]
    ).copy()
    modeling[outcome] = modeling[outcome].astype(int)
    modeling[exposure] = modeling[exposure].astype(int)
    crude, crude_low, crude_high = binary_risk_difference(modeling, outcome, exposure)
    try:
        fitted, warnings_seen = capture_model_fit(
            lambda: smf.glm(
                formula,
                data=modeling,
                family=sm.families.Binomial(),
            ).fit(cov_type="HC3")
        )
    except (PerfectSeparationError, np.linalg.LinAlgError) as error:
        result = HypothesisResult(
            hypothesis_id,
            title,
            len(modeling),
            int(modeling[outcome].sum()),
            int(modeling[exposure].sum()),
            int((modeling[exposure] == 0).sum()),
            feasibility.missing_rate,
            "risk_difference",
            crude,
            crude_low,
            crude_high,
            "odds_ratio",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            False,
            "inconclusive",
            "Binomial GLM with HC3",
            f"Unstable model: {error}",
        )
        return ModelOutput(result, empty, empty)
    coefficient = float(fitted.params[exposure])
    confidence = fitted.conf_int().loc[exposure]
    odds_ratio = float(np.exp(coefficient))
    odds_low, odds_high = np.exp(confidence)
    adjusted_rd, rd_low, rd_high = standardized_risk_difference(
        fitted, modeling, exposure
    )
    diagnostics = model_diagnostic_rows(
        fitted,
        hypothesis_id,
        "adjusted_logit",
        warnings_seen=warnings_seen,
        events=int(modeling[outcome].sum()),
    )
    stable = bool(diagnostics["passed"].all())
    practical = abs(adjusted_rd) >= practical_threshold and alternative(adjusted_rd)
    status: HypothesisStatus = "not_supported" if stable else "inconclusive"
    result = HypothesisResult(
        hypothesis_id,
        title,
        len(modeling),
        int(modeling[outcome].sum()),
        int(modeling[exposure].sum()),
        int((modeling[exposure] == 0).sum()),
        feasibility.missing_rate,
        "risk_difference",
        crude,
        crude_low,
        crude_high,
        "odds_ratio",
        odds_ratio,
        float(odds_low),
        float(odds_high),
        adjusted_rd,
        rd_low,
        rd_high,
        float(fitted.pvalues[exposure]),
        None,
        practical,
        status,
        "Binomial GLM with HC3",
        "Observational adjusted association; causality is not established.",
    )
    return ModelOutput(
        result,
        coefficient_rows(
            fitted,
            hypothesis_id,
            "adjusted_logit",
            exponentiate=True,
        ),
        diagnostics,
    )
