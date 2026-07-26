"""H5: customer profit effects after route-mix adjustment."""

from __future__ import annotations

import numpy as np
import pandas as pd
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
from delivery_pulse.hypotheses.multiple_testing import benjamini_hochberg

FORMULA = """
delivery_profit ~ C(customer_id) + distance_planned_1000km
    + C(route_id) + C(priority) + C(cargo_type) + C(vehicle_type)
    + C(calendar_month) + has_loading_delay + has_traffic + has_weather
    + has_breakdown + has_route_deviation
"""


def run_h5(
    frame: pd.DataFrame,
    feasibility: FeasibilityResult,
    *,
    min_group_size: int,
    alpha: float,
) -> ModelOutput:
    """Fit robust customer fixed effects and their joint test."""
    if not feasibility.feasible:
        return ModelOutput(
            HypothesisResult(
                "H5",
                "Customer profit effects after route-mix adjustment",
                feasibility.observations,
                0,
                feasibility.exposed,
                feasibility.unexposed,
                feasibility.missing_rate,
                "unadjusted_customer_profit_range",
                None,
                None,
                None,
                "adjusted_customer_effect_range",
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
                "OLS customer fixed effects with HC3",
                feasibility.reason,
            ),
            pd.DataFrame(),
            pd.DataFrame(),
        )
    financial = frame.loc[frame["financial_data_complete"] == 1].copy()
    counts = financial.groupby("customer_id").size()
    eligible = counts.loc[counts >= min_group_size].index
    modeling = financial.loc[financial["customer_id"].isin(eligible)].copy()
    crude = modeling.groupby("customer_id")["delivery_profit"].mean()
    model, warnings_seen = capture_model_fit(
        lambda: smf.ols(FORMULA, data=modeling).fit(cov_type="HC3")
    )
    lower, upper = modeling["delivery_profit"].quantile([0.01, 0.99])
    central = modeling.loc[modeling["delivery_profit"].between(lower, upper)].copy()
    sensitivity_model, sensitivity_warnings = capture_model_fit(
        lambda: smf.ols(FORMULA, data=central).fit(cov_type="HC3")
    )
    customer_terms = [
        term for term in model.params.index if term.startswith("C(customer_id)")
    ]
    restriction = np.zeros((len(customer_terms), len(model.params)))
    term_positions = {term: index for index, term in enumerate(model.params.index)}
    for row, term in enumerate(customer_terms):
        restriction[row, term_positions[term]] = 1
    joint = model.f_test(restriction)
    joint_p = float(np.asarray(joint.pvalue).item())
    coefficients = coefficient_rows(model, "H5", "customer_fixed_effects_hc3")
    sensitivity_coefficients = coefficient_rows(
        sensitivity_model,
        "H5",
        "customer_p1_p99_fixed_effects_hc3",
    )
    customer_coefficients = coefficients.loc[
        coefficients["term"].str.startswith("C(customer_id)")
    ].copy()
    customer_coefficients["p_value_adjusted_within_h5"] = benjamini_hochberg(
        customer_coefficients["p_value"].astype(float).tolist()
    )
    coefficients = coefficients.merge(
        customer_coefficients[["term", "p_value_adjusted_within_h5"]],
        on="term",
        how="left",
    )
    coefficients = pd.concat(
        [coefficients, sensitivity_coefficients],
        ignore_index=True,
    )
    adjusted_range = float(
        customer_coefficients["estimate"].max()
        - customer_coefficients["estimate"].min()
    )
    large_significant = bool(
        (
            (customer_coefficients["p_value_adjusted_within_h5"] < alpha)
            & (customer_coefficients["estimate"].abs() >= 5_000)
        ).any()
    )
    practical = adjusted_range >= 5_000 and large_significant
    diagnostics = model_diagnostic_rows(
        model,
        "H5",
        "customer_fixed_effects_hc3",
        warnings_seen=warnings_seen,
    )
    diagnostics = pd.concat(
        [
            diagnostics,
            model_diagnostic_rows(
                sensitivity_model,
                "H5",
                "customer_p1_p99_fixed_effects_hc3",
                warnings_seen=sensitivity_warnings,
            ),
        ],
        ignore_index=True,
    )
    stable = bool(
        diagnostics.loc[
            diagnostics["diagnostic"].isin(["converged", "captured_warnings"]),
            "passed",
        ].all()
    )
    return ModelOutput(
        HypothesisResult(
            "H5",
            "Customer profit effects after route-mix adjustment",
            len(modeling),
            0,
            len(eligible),
            int((counts < min_group_size).sum()),
            feasibility.missing_rate,
            "unadjusted_customer_profit_range",
            float(crude.max() - crude.min()),
            None,
            None,
            "adjusted_customer_effect_range",
            adjusted_range,
            float(customer_coefficients["ci_low"].min()),
            float(customer_coefficients["ci_high"].max()),
            None,
            None,
            None,
            joint_p,
            None,
            practical,
            "not_supported" if stable else "inconclusive",
            "OLS customer fixed effects with HC3 and joint F-test",
            (
                f"{len(eligible)} customers passed the volume threshold; "
                "client coefficients use a separate BH family. "
                "No hierarchical shrinkage is applied."
            ),
        ),
        coefficients,
        diagnostics,
    )
