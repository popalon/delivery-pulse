"""Statistical diagnostics and reusable effect calculations."""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd
import patsy
from scipy.special import expit
from statsmodels.tools.sm_exceptions import (
    ConvergenceWarning,
    PerfectSeparationError,
    PerfectSeparationWarning,
)


def binary_risk_difference(
    frame: pd.DataFrame,
    outcome: str,
    exposure: str,
) -> tuple[float, float, float]:
    """Calculate a crude risk difference and normal 95% interval."""
    exposed = frame.loc[frame[exposure] == 1, outcome].astype(float)
    unexposed = frame.loc[frame[exposure] == 0, outcome].astype(float)
    if exposed.empty or unexposed.empty:
        return float("nan"), float("nan"), float("nan")
    difference = float(exposed.mean() - unexposed.mean())
    standard_error = np.sqrt(
        exposed.mean() * (1 - exposed.mean()) / len(exposed)
        + unexposed.mean() * (1 - unexposed.mean()) / len(unexposed)
    )
    return (
        difference,
        float(difference - 1.96 * standard_error),
        float(difference + 1.96 * standard_error),
    )


def standardized_risk_difference(
    result: Any,
    frame: pd.DataFrame,
    exposure: str,
) -> tuple[float, float, float]:
    """Calculate standardized risk difference and delta-method interval."""
    design_info = result.model.data.design_info
    exposed = frame.copy()
    unexposed = frame.copy()
    exposed[exposure] = 1
    unexposed[exposure] = 0
    design_exposed = np.asarray(patsy.build_design_matrices([design_info], exposed)[0])
    design_unexposed = np.asarray(
        patsy.build_design_matrices([design_info], unexposed)[0]
    )
    parameters = np.asarray(result.params)
    probability_exposed = expit(design_exposed @ parameters)
    probability_unexposed = expit(design_unexposed @ parameters)
    difference = float(np.mean(probability_exposed - probability_unexposed))
    gradient = np.mean(
        probability_exposed[:, None]
        * (1 - probability_exposed[:, None])
        * design_exposed
        - probability_unexposed[:, None]
        * (1 - probability_unexposed[:, None])
        * design_unexposed,
        axis=0,
    )
    variance = float(gradient @ np.asarray(result.cov_params()) @ gradient)
    standard_error = np.sqrt(max(variance, 0))
    return (
        difference,
        float(difference - 1.96 * standard_error),
        float(difference + 1.96 * standard_error),
    )


def coefficient_rows(
    result: Any,
    hypothesis_id: str,
    model_name: str,
    *,
    exponentiate: bool = False,
) -> pd.DataFrame:
    """Return deterministic tidy model coefficients."""
    confidence = result.conf_int()
    rows = pd.DataFrame(
        {
            "hypothesis_id": hypothesis_id,
            "model_name": model_name,
            "term": result.params.index,
            "estimate": result.params.to_numpy(),
            "ci_low": confidence.iloc[:, 0].to_numpy(),
            "ci_high": confidence.iloc[:, 1].to_numpy(),
            "p_value": result.pvalues.to_numpy(),
        }
    )
    if exponentiate:
        rows[["estimate", "ci_low", "ci_high"]] = np.exp(
            rows[["estimate", "ci_low", "ci_high"]]
        )
    return rows.sort_values("term", ignore_index=True)


def model_diagnostic_rows(
    result: Any,
    hypothesis_id: str,
    model_name: str,
    *,
    warnings_seen: list[str],
    events: int | None = None,
) -> pd.DataFrame:
    """Return convergence, conditioning, EPV, and warning diagnostics."""
    parameters = len(result.params)
    converged = bool(getattr(result, "converged", True))
    condition_number = float(np.linalg.cond(result.model.exog))
    epv = events / parameters if events is not None and parameters else None
    return pd.DataFrame(
        [
            {
                "hypothesis_id": hypothesis_id,
                "model_name": model_name,
                "diagnostic": "converged",
                "value": str(converged).lower(),
                "passed": converged,
                "message": "Model convergence flag.",
            },
            {
                "hypothesis_id": hypothesis_id,
                "model_name": model_name,
                "diagnostic": "condition_number",
                "value": condition_number,
                "passed": condition_number < 1_000,
                "message": "Design-matrix multicollinearity diagnostic.",
            },
            {
                "hypothesis_id": hypothesis_id,
                "model_name": model_name,
                "diagnostic": "events_per_parameter",
                "value": epv,
                "passed": epv is None or epv >= 10,
                "message": "Target events divided by fitted parameters.",
            },
            {
                "hypothesis_id": hypothesis_id,
                "model_name": model_name,
                "diagnostic": "captured_warnings",
                "value": " | ".join(warnings_seen),
                "passed": not warnings_seen,
                "message": "Statsmodels warnings are retained, not hidden.",
            },
        ]
    )


def capture_model_fit(callback: Any) -> tuple[Any, list[str]]:
    """Fit a model while retaining convergence and separation warnings."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = callback()
    relevant = [
        str(item.message)
        for item in caught
        if issubclass(
            item.category,
            (ConvergenceWarning, PerfectSeparationWarning, RuntimeWarning),
        )
    ]
    return result, relevant


__all__ = [
    "PerfectSeparationError",
    "binary_risk_difference",
    "capture_model_fit",
    "coefficient_rows",
    "model_diagnostic_rows",
    "standardized_risk_difference",
]
