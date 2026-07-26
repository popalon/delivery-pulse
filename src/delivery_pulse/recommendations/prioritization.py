"""Transparent recommendation scoring with evidence gates."""

from __future__ import annotations

from delivery_pulse.recommendations.models import ActionType, EvidenceLevel

WEIGHTS = {
    "business_impact": 0.25,
    "evidence_strength": 0.20,
    "confidence": 0.15,
    "urgency": 0.15,
    "reversibility": 0.10,
    "implementation_effort_inverse": 0.10,
    "operational_risk_inverse": 0.05,
}
EVIDENCE_SCORES: dict[EvidenceLevel, float] = {
    "strong_observational_evidence": 5.0,
    "moderate_or_secondary_evidence": 3.5,
    "descriptive_only": 2.0,
    "insufficient_evidence": 1.0,
}


def priority_score(
    *,
    business_impact: int,
    evidence: EvidenceLevel,
    confidence: int,
    urgency: int,
    reversibility: int,
    implementation_effort: int,
    operational_risk: int,
) -> float:
    """Calculate the documented 0–100 weighted score."""
    values = (
        business_impact,
        confidence,
        urgency,
        reversibility,
        implementation_effort,
        operational_risk,
    )
    if any(value < 1 or value > 5 for value in values):
        raise ValueError("priority dimensions must be in the range 1..5")
    components = {
        "business_impact": business_impact,
        "evidence_strength": EVIDENCE_SCORES[evidence],
        "confidence": confidence,
        "urgency": urgency,
        "reversibility": reversibility,
        "implementation_effort_inverse": 6 - implementation_effort,
        "operational_risk_inverse": 6 - operational_risk,
    }
    weighted = sum(components[key] * weight for key, weight in WEIGHTS.items())
    return round(weighted * 20, 1)


def priority_category(score: float, evidence: EvidenceLevel, action: ActionType) -> str:
    """Apply evidence/action gates after numerical scoring."""
    if action == "do_not_act_yet":
        return "HOLD"
    if action in {"collect_more_data", "monitor"}:
        return "P3"
    if evidence == "insufficient_evidence":
        return "HOLD"
    if score >= 70:
        return "P1"
    if score >= 55:
        return "P2"
    return "P3"
