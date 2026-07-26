"""Translate pre-registered hypothesis outcomes into action constraints."""

from __future__ import annotations

import pandas as pd

from delivery_pulse.recommendations.models import EvidenceLevel

EXPECTED_STATUSES = {
    "H1": "not_supported",
    "H2": "supported",
    "H3": "supported",
    "H4": "inconclusive",
    "H5": "supported",
    "H6": "inconclusive",
}


def validate_hypothesis_results(results: pd.DataFrame) -> dict[str, dict[str, object]]:
    """Validate all frozen H1–H6 statuses without refitting any model."""
    required = {
        "hypothesis_id",
        "status",
        "observations",
        "events",
        "adjusted_effect",
        "adjusted_ci_low",
        "adjusted_ci_high",
        "p_value_adjusted",
        "practically_significant",
        "notes",
    }
    missing = required - set(results.columns)
    if missing:
        raise ValueError(f"hypothesis results missing columns: {sorted(missing)}")
    if results["hypothesis_id"].duplicated().any():
        raise ValueError("hypothesis IDs must be unique")
    indexed = results.set_index("hypothesis_id")
    if set(indexed.index) != set(EXPECTED_STATUSES):
        raise ValueError("hypothesis results must contain exactly H1–H6")
    for hypothesis_id, expected in EXPECTED_STATUSES.items():
        actual = str(indexed.at[hypothesis_id, "status"])
        if actual != expected:
            raise ValueError(
                f"{hypothesis_id} status changed: expected {expected}, got {actual}"
            )
    return {
        hypothesis_id: indexed.loc[hypothesis_id].to_dict()
        for hypothesis_id in sorted(EXPECTED_STATUSES)
    }


def evidence_level(hypothesis_id: str) -> EvidenceLevel:
    """Return the pre-specified evidence interpretation."""
    if hypothesis_id in {"H2", "H3", "H5"}:
        return "strong_observational_evidence"
    if hypothesis_id == "H1":
        return "moderate_or_secondary_evidence"
    return "insufficient_evidence"
