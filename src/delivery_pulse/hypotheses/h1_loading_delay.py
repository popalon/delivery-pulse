"""H1: loading delay and late-delivery risk."""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from delivery_pulse.hypotheses._binary import fit_binary_hypothesis
from delivery_pulse.hypotheses.diagnostics import (
    capture_model_fit,
    coefficient_rows,
    model_diagnostic_rows,
)
from delivery_pulse.hypotheses.models import FeasibilityResult, ModelOutput

FORMULA = """
is_late ~ has_loading_delay + distance_planned_1000km
    + C(route_id) + C(priority) + C(cargo_type) + C(vehicle_type)
    + C(customer_segment) + C(calendar_month)
"""
DURATION_FORMULA = FORMULA.replace("has_loading_delay", "log_loading_delay_minutes")


def run_h1(frame: pd.DataFrame, feasibility: FeasibilityResult) -> ModelOutput:
    """Fit the pre-specified H1 model."""
    delivered = frame.loc[frame["delivery_status"] == "delivered"].copy()
    output = fit_binary_hypothesis(
        delivered,
        feasibility,
        hypothesis_id="H1",
        title="Loading delay and late-delivery risk",
        formula=FORMULA,
        outcome="is_late",
        exposure="has_loading_delay",
        practical_threshold=0.01,
        alternative=lambda effect: effect > 0,
    )
    if output.coefficients.empty:
        return output
    delivered["log_loading_delay_minutes"] = np.log1p(
        delivered["loading_delay_minutes"].astype(float)
    )
    duration_model, warnings_seen = capture_model_fit(
        lambda: smf.glm(
            DURATION_FORMULA,
            data=delivered,
            family=sm.families.Binomial(),
        ).fit(cov_type="HC3")
    )
    return ModelOutput(
        output.result,
        pd.concat(
            [
                output.coefficients,
                coefficient_rows(
                    duration_model,
                    "H1",
                    "duration_sensitivity_logit",
                    exponentiate=True,
                ),
            ],
            ignore_index=True,
        ),
        pd.concat(
            [
                output.diagnostics,
                model_diagnostic_rows(
                    duration_model,
                    "H1",
                    "duration_sensitivity_logit",
                    warnings_seen=warnings_seen,
                    events=int(delivered["is_late"].sum()),
                ),
            ],
            ignore_index=True,
        ),
    )
