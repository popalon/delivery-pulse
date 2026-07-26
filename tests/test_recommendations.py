"""Tests for evidence-gated recommendations without full generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from delivery_pulse.__main__ import main
from delivery_pulse.recommendations.catalog import build_recommendations
from delivery_pulse.recommendations.evidence import (
    evidence_level,
    validate_hypothesis_results,
)
from delivery_pulse.recommendations.models import RecommendationRunResult
from delivery_pulse.recommendations.prioritization import (
    priority_category,
    priority_score,
)
from delivery_pulse.recommendations.reporting import (
    build_figures,
    write_outputs,
)
from delivery_pulse.recommendations.scenarios import (
    DEFAULT_SCENARIOS,
    calculate_scenarios,
    load_scenario_assumptions,
)


def _results() -> pd.DataFrame:
    rows = []
    statuses = {
        "H1": "not_supported",
        "H2": "supported",
        "H3": "supported",
        "H4": "inconclusive",
        "H5": "supported",
        "H6": "inconclusive",
    }
    for hypothesis_id, status in statuses.items():
        rows.append(
            {
                "hypothesis_id": hypothesis_id,
                "status": status,
                "observations": 1000,
                "events": 100,
                "adjusted_effect": 1.2,
                "adjusted_ci_low": 1.1,
                "adjusted_ci_high": 1.3,
                "p_value_adjusted": 0.01,
                "practically_significant": status == "supported",
                "notes": "observational",
            }
        )
    return pd.DataFrame(rows)


def test_evidence_mapping_and_action_gates() -> None:
    validated = validate_hypothesis_results(_results())
    cards = build_recommendations(validated)
    by_id = {item.recommendation_id: item for item in cards}

    assert evidence_level("H2") == "strong_observational_evidence"
    assert evidence_level("H1") == "moderate_or_secondary_evidence"
    assert by_id["R1"].action_type == "pilot"
    assert by_id["R4"].action_type != "implement"
    assert by_id["R5"].action_type == "collect_more_data"
    assert "интервалы ТО" in by_id["R5"].recommended_action
    assert by_id["R6"].action_type == "do_not_act_yet"
    assert "Сохранить ограничения безопасности" in by_id["R6"].recommended_action
    assert by_id["R3"].priority == "P2"
    assert all(item.action_type != "implement" for item in cards)


def test_supported_does_not_automatically_become_p1() -> None:
    score = priority_score(
        business_impact=2,
        evidence="strong_observational_evidence",
        confidence=3,
        urgency=2,
        reversibility=3,
        implementation_effort=5,
        operational_risk=5,
    )
    assert priority_category(score, "strong_observational_evidence", "pilot") != "P1"
    assert priority_category(99, "insufficient_evidence", "do_not_act_yet") == "HOLD"


def test_scenario_calculator_is_editable_and_not_or_based(tmp_path: Path) -> None:
    assumptions = load_scenario_assumptions(None)
    assert "odds_ratio" not in assumptions.columns
    scenarios = calculate_scenarios(assumptions)
    assert set(scenarios["scenario_label"]) == {"illustrative_scenario_not_forecast"}
    first = scenarios.iloc[0]
    expected = (
        first["baseline_cases"]
        * first["coverage_share"]
        * first["assumed_reduction_share"]
    )
    assert first["prevented_cases"] == pytest.approx(expected)
    for _, group in scenarios.groupby("recommendation_id"):
        ordered = group.set_index("scenario").loc[
            ["conservative", "base", "optimistic"]
        ]
        assert ordered["net_effect_rub"].is_monotonic_increasing

    payload = {
        "scenarios": [
            {
                "recommendation_id": "R1",
                "scenario": "zero",
                "baseline_cases": 100,
                "coverage_share": 0,
                "assumed_reduction_share": 0,
                "average_value_per_prevented_case_rub": 10,
                "program_cost_rub": 0,
                "evaluation_period_months": 3,
            }
        ]
    }
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    zero = calculate_scenarios(load_scenario_assumptions(path)).iloc[0]
    assert zero["prevented_cases"] == 0
    assert zero["net_effect_rub"] == 0

    negative = assumptions.head(1).copy()
    negative["assumed_reduction_share"] = -0.1
    with pytest.raises(ValueError):
        calculate_scenarios(negative)


def test_outputs_are_deterministic_and_stay_in_tmp_path(tmp_path: Path) -> None:
    cards = build_recommendations(validate_hypothesis_results(_results()))
    scenarios = calculate_scenarios(
        pd.DataFrame(
            DEFAULT_SCENARIOS,
            columns=[
                "recommendation_id",
                "scenario",
                "baseline_cases",
                "coverage_share",
                "assumed_reduction_share",
                "average_value_per_prevented_case_rub",
                "program_cost_rub",
                "evaluation_period_months",
            ],
        )
    )
    output = tmp_path / "recommendations"
    figures = build_figures(cards, scenarios, output / "figures")
    paths = write_outputs(output, cards, scenarios, figures, protocol_hash="test")

    assert all(
        path.is_relative_to(tmp_path) for path in [*paths.values(), *figures.values()]
    )
    assert set(path.name for path in paths.values()) == {
        "recommendations.json",
        "recommendation_scores.csv",
        "scenario_analysis.csv",
        "pilot_plan.csv",
        "decision_register.csv",
        "recommendations_report.md",
    }
    assert len(figures) == 5
    report = paths["report"].read_text(encoding="utf-8")
    assert "quality_issues_manifest" not in report
    assert "не финансовый прогноз" in report
    before = hashlib.sha256(paths["scores"].read_bytes()).hexdigest()
    paths["scores"].unlink()
    write_outputs(output, cards, scenarios, figures, protocol_hash="test")
    after = hashlib.sha256(paths["scores"].read_bytes()).hexdigest()
    assert before == after


def test_protocol_status_change_is_rejected() -> None:
    frame = _results()
    frame.loc[frame["hypothesis_id"] == "H4", "status"] = "supported"
    with pytest.raises(ValueError, match="status changed"):
        validate_hypothesis_results(frame)


def test_cli_codes_for_info_and_insufficient_report(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    cards = build_recommendations(validate_hypothesis_results(_results()))
    fake = RecommendationRunResult(cards, {"report": tmp_path / "report.md"}, 0.1, True)

    def fake_run(_config: object) -> RecommendationRunResult:
        return fake

    monkeypatch.setattr(
        "delivery_pulse.recommendations.run_recommendations",
        fake_run,
    )
    assert main(["recommendations", "info"]) == 0
    assert (
        main(
            [
                "recommendations",
                "build",
                "--database",
                str(tmp_path / "warehouse.duckdb"),
                "--hypothesis-results-dir",
                str(tmp_path / "hypotheses"),
                "--output-dir",
                str(tmp_path / "recommendations"),
            ]
        )
        == 1
    )
