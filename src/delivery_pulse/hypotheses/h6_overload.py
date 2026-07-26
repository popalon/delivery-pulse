"""H6: operational overload feasibility and Fisher sensitivity."""

from __future__ import annotations

import pandas as pd
from scipy.stats import fisher_exact

from delivery_pulse.hypotheses.diagnostics import binary_risk_difference
from delivery_pulse.hypotheses.models import (
    FeasibilityResult,
    HypothesisResult,
    ModelOutput,
)


def run_h6(frame: pd.DataFrame, feasibility: FeasibilityResult) -> ModelOutput:
    """Return the pre-specified inconclusive result and Fisher sensitivity."""
    financial = frame.loc[frame["financial_data_complete"] == 1].copy()
    crude, low, high = binary_risk_difference(
        financial,
        "is_loss_making",
        "operational_overload",
    )
    table = pd.crosstab(
        financial["operational_overload"],
        financial["is_loss_making"],
    ).reindex(index=[0, 1], columns=[0, 1], fill_value=0)
    fisher = fisher_exact(table.to_numpy(), alternative="two-sided")
    diagnostics = pd.DataFrame(
        [
            {
                "hypothesis_id": "H6",
                "model_name": "fisher_sensitivity",
                "diagnostic": "overload_interaction_feasibility",
                "value": feasibility.exposed_events,
                "passed": feasibility.feasible,
                "message": feasibility.reason,
            }
        ]
    )
    coefficients = pd.DataFrame(
        [
            {
                "hypothesis_id": "H6",
                "model_name": "fisher_sensitivity",
                "term": "operational_overload",
                "estimate": float(fisher.statistic),
                "ci_low": None,
                "ci_high": None,
                "p_value": float(fisher.pvalue),
            }
        ]
    )
    return ModelOutput(
        HypothesisResult(
            "H6",
            "Operational overload and segment-specific loss risk",
            feasibility.observations,
            feasibility.events,
            feasibility.exposed,
            feasibility.unexposed,
            feasibility.missing_rate,
            "risk_difference",
            crude,
            low,
            high,
            "odds_ratio",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            abs(crude) >= 0.02,
            "inconclusive",
            "Feasibility gate with pre-specified Fisher sensitivity",
            (
                "Interaction model was not estimated because overload-loss cells "
                "failed the protocol. Fisher sensitivity does not override status."
            ),
        ),
        coefficients,
        diagnostics,
    )
