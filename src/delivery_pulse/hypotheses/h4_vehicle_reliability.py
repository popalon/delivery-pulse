"""H4: lagged maintenance and breakdown incidence."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from delivery_pulse.hypotheses.diagnostics import (
    capture_model_fit,
    coefficient_rows,
    model_diagnostic_rows,
)
from delivery_pulse.hypotheses.models import (
    FeasibilityResult,
    HypothesisResult,
    ModelOutput,
)

FORMULA = """
breakdown_count ~ had_scheduled_maintenance_previous_month
    + vehicle_age_years + C(vehicle_type) + C(calendar_month)
"""


def _fit_count(frame: pd.DataFrame, exposure: str) -> tuple[Any, str, float, list[str]]:
    offset = np.log(frame[exposure].astype(float))
    poisson, poisson_warnings = capture_model_fit(
        lambda: smf.glm(
            FORMULA,
            data=frame,
            family=sm.families.Poisson(),
            offset=offset,
        ).fit(cov_type="HC3")
    )
    dispersion = float(np.sum(np.square(poisson.resid_pearson)) / poisson.df_resid)
    if dispersion <= 1.5:
        return poisson, "poisson", dispersion, poisson_warnings
    negative_binomial, nb_warnings = capture_model_fit(
        lambda: smf.negativebinomial(
            FORMULA,
            data=frame,
            offset=offset,
        ).fit(disp=False, cov_type="HC3")
    )
    return negative_binomial, "negative_binomial", dispersion, nb_warnings


def run_h4(frame: pd.DataFrame, feasibility: FeasibilityResult) -> ModelOutput:
    """Fit exposure-offset count models for kilometers and trip hours."""
    if not feasibility.feasible:
        return ModelOutput(
            HypothesisResult(
                "H4",
                "Lagged maintenance and breakdown incidence",
                feasibility.observations,
                feasibility.events,
                feasibility.exposed,
                feasibility.unexposed,
                feasibility.missing_rate,
                "crude_rate_ratio",
                None,
                None,
                None,
                "incidence_rate_ratio",
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
                "Poisson/Negative Binomial with exposure offset",
                feasibility.reason,
            ),
            pd.DataFrame(),
            pd.DataFrame(),
        )
    modeling = frame.loc[
        (frame["actual_distance_km"] > 0) & (frame["trip_hours"] > 0)
    ].copy()
    factor = "had_scheduled_maintenance_previous_month"
    grouped = modeling.groupby(factor, observed=True).agg(
        breakdowns=("breakdown_count", "sum"),
        distance=("actual_distance_km", "sum"),
    )
    crude_ratio = float(
        (grouped.loc[1, "breakdowns"] / grouped.loc[1, "distance"])
        / (grouped.loc[0, "breakdowns"] / grouped.loc[0, "distance"])
    )
    km_model, family, dispersion, km_warnings = _fit_count(
        modeling, "actual_distance_km"
    )
    hour_model, hour_family, hour_dispersion, hour_warnings = _fit_count(
        modeling, "trip_hours"
    )
    estimate = float(np.exp(km_model.params[factor]))
    confidence = np.exp(km_model.conf_int().loc[factor])
    practical = abs(estimate - 1) >= 0.20
    coefficient_stable = bool(
        np.isfinite(estimate)
        and np.isfinite(confidence).all()
        and float(np.log(confidence.iloc[1]) - np.log(confidence.iloc[0])) < 10
    )
    coefficients = pd.concat(
        [
            coefficient_rows(km_model, "H4", f"{family}_km_offset", exponentiate=True),
            coefficient_rows(
                hour_model,
                "H4",
                f"{hour_family}_hour_offset",
                exponentiate=True,
            ),
        ],
        ignore_index=True,
    )
    diagnostics = pd.concat(
        [
            model_diagnostic_rows(
                km_model,
                "H4",
                f"{family}_km_offset",
                warnings_seen=km_warnings,
                events=int(modeling["breakdown_count"].sum()),
            ),
            model_diagnostic_rows(
                hour_model,
                "H4",
                f"{hour_family}_hour_offset",
                warnings_seen=hour_warnings,
                events=int(modeling["breakdown_count"].sum()),
            ),
            pd.DataFrame(
                [
                    {
                        "hypothesis_id": "H4",
                        "model_name": f"{family}_km_offset",
                        "diagnostic": "poisson_overdispersion",
                        "value": dispersion,
                        "passed": True,
                        "message": "NB selected when Pearson dispersion exceeds 1.5.",
                    },
                    {
                        "hypothesis_id": "H4",
                        "model_name": f"{hour_family}_hour_offset",
                        "diagnostic": "poisson_overdispersion",
                        "value": hour_dispersion,
                        "passed": True,
                        "message": "Hour-exposure sensitivity diagnostic.",
                    },
                    {
                        "hypothesis_id": "H4",
                        "model_name": f"{family}_km_offset",
                        "diagnostic": "primary_coefficient_stability",
                        "value": float(
                            np.log(confidence.iloc[1]) - np.log(confidence.iloc[0])
                        ),
                        "passed": coefficient_stable,
                        "message": (
                            "Finite log-scale CI width must be below 10; "
                            "otherwise the primary estimate is unstable."
                        ),
                    },
                ]
            ),
        ],
        ignore_index=True,
    )
    stable = coefficient_stable and bool(
        diagnostics.loc[
            diagnostics["diagnostic"].isin(
                ["converged", "events_per_parameter", "captured_warnings"]
            ),
            "passed",
        ].all()
    )
    return ModelOutput(
        HypothesisResult(
            "H4",
            "Lagged maintenance and breakdown incidence",
            len(modeling),
            int(modeling["breakdown_count"].sum()),
            int(modeling[factor].sum()),
            int((modeling[factor] == 0).sum()),
            feasibility.missing_rate,
            "crude_rate_ratio",
            crude_ratio,
            None,
            None,
            "incidence_rate_ratio",
            estimate,
            float(confidence.iloc[0]),
            float(confidence.iloc[1]),
            None,
            None,
            None,
            float(km_model.pvalues[factor]),
            None,
            practical,
            "not_supported" if stable else "inconclusive",
            f"{family} count model with log(km) offset and robust errors",
            (
                f"Poisson dispersion={dispersion:.3f}; {family} selected. "
                "Repair events are not treated as preventive exposure."
            ),
        ),
        coefficients,
        diagnostics,
    )
