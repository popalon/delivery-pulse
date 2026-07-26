"""H3: breakdown association with loss risk and delivery profit."""

from __future__ import annotations

import pandas as pd
import statsmodels.formula.api as smf

from delivery_pulse.hypotheses._binary import fit_binary_hypothesis
from delivery_pulse.hypotheses.diagnostics import (
    capture_model_fit,
    coefficient_rows,
    model_diagnostic_rows,
)
from delivery_pulse.hypotheses.models import FeasibilityResult, ModelOutput

FORMULA = """
is_loss_making ~ has_breakdown + distance_planned_1000km
    + C(route_id) + C(priority) + C(vehicle_type) + C(customer_segment)
    + C(calendar_month) + operational_overload + has_loading_delay
"""
PROFIT_FORMULA = FORMULA.replace("is_loss_making", "delivery_profit")


def run_h3(frame: pd.DataFrame, feasibility: FeasibilityResult) -> ModelOutput:
    """Fit H3 loss GLM and robust profit sensitivity model."""
    financial = frame.loc[frame["financial_data_complete"] == 1].copy()
    output = fit_binary_hypothesis(
        financial,
        feasibility,
        hypothesis_id="H3",
        title="Breakdown and loss-making delivery risk",
        formula=FORMULA,
        outcome="is_loss_making",
        exposure="has_breakdown",
        practical_threshold=0.02,
        alternative=lambda effect: effect > 0,
    )
    if output.result.status == "inconclusive" and output.coefficients.empty:
        return output
    profit_model, warnings_seen = capture_model_fit(
        lambda: smf.ols(PROFIT_FORMULA, data=financial).fit(cov_type="HC3")
    )
    profit_coefficients = coefficient_rows(
        profit_model,
        "H3",
        "profit_ols_hc3",
    )
    profit_diagnostics = model_diagnostic_rows(
        profit_model,
        "H3",
        "profit_ols_hc3",
        warnings_seen=warnings_seen,
    )
    lower, upper = financial["delivery_profit"].quantile([0.01, 0.99])
    central = financial.loc[financial["delivery_profit"].between(lower, upper)].copy()
    trimmed_model, trimmed_warnings = capture_model_fit(
        lambda: smf.ols(PROFIT_FORMULA, data=central).fit(cov_type="HC3")
    )
    trimmed_coefficients = coefficient_rows(
        trimmed_model,
        "H3",
        "profit_p1_p99_ols_hc3",
    )
    trimmed_diagnostics = model_diagnostic_rows(
        trimmed_model,
        "H3",
        "profit_p1_p99_ols_hc3",
        warnings_seen=trimmed_warnings,
    )
    breakdown_profit = float(profit_model.params["has_breakdown"])
    trimmed_profit = float(trimmed_model.params["has_breakdown"])
    practical = output.result.practically_significant or breakdown_profit <= -5_000
    output.result.practically_significant = practical
    output.result.notes += (
        f" Adjusted breakdown profit difference: {breakdown_profit:.2f} RUB. "
        f"Pre-specified p1–p99 sensitivity: {trimmed_profit:.2f} RUB."
    )
    return ModelOutput(
        output.result,
        pd.concat(
            [
                output.coefficients,
                profit_coefficients,
                trimmed_coefficients,
            ],
            ignore_index=True,
        ),
        pd.concat(
            [
                output.diagnostics,
                profit_diagnostics,
                trimmed_diagnostics,
            ],
            ignore_index=True,
        ),
    )
