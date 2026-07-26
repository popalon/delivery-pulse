"""H2: express versus standard late-delivery risk."""

from __future__ import annotations

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
is_late ~ is_express + distance_planned_1000km
    + C(route_id) + C(cargo_type) + C(vehicle_type) + C(customer_segment)
    + C(calendar_month) + has_loading_delay + has_traffic + has_weather
"""
NO_EVENT_FORMULA = FORMULA.replace(
    " + has_loading_delay + has_traffic + has_weather", ""
)


def run_h2(frame: pd.DataFrame, feasibility: FeasibilityResult) -> ModelOutput:
    """Fit the pre-specified H2 model."""
    delivered = frame.loc[frame["delivery_status"] == "delivered"].copy()
    delivered["is_express"] = (delivered["priority"] == "express").astype(int)
    output = fit_binary_hypothesis(
        delivered,
        feasibility,
        hypothesis_id="H2",
        title="Express versus standard late-delivery risk",
        formula=FORMULA,
        outcome="is_late",
        exposure="is_express",
        practical_threshold=0.005,
        alternative=lambda effect: True,
    )
    if output.coefficients.empty:
        return output
    sensitivity_model, warnings_seen = capture_model_fit(
        lambda: smf.glm(
            NO_EVENT_FORMULA,
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
                    sensitivity_model,
                    "H2",
                    "no_event_sensitivity_logit",
                    exponentiate=True,
                ),
            ],
            ignore_index=True,
        ),
        pd.concat(
            [
                output.diagnostics,
                model_diagnostic_rows(
                    sensitivity_model,
                    "H2",
                    "no_event_sensitivity_logit",
                    warnings_seen=warnings_seen,
                    events=int(delivered["is_late"].sum()),
                ),
            ],
            ignore_index=True,
        ),
    )
