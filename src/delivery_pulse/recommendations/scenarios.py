"""Editable illustrative scenario calculator; never a forecast."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

SCENARIO_LABEL = "illustrative_scenario_not_forecast"

DEFAULT_SCENARIOS = [
    ("R1", "conservative", 538, 0.25, 0.05, 15000.0, 1800000.0, 3),
    ("R1", "base", 538, 0.40, 0.10, 15000.0, 1800000.0, 3),
    ("R1", "optimistic", 538, 0.60, 0.15, 15000.0, 1800000.0, 3),
    ("R2", "conservative", 1066, 0.20, 0.05, 53081.97, 2500000.0, 3),
    ("R2", "base", 1066, 0.35, 0.10, 53081.97, 2500000.0, 3),
    ("R2", "optimistic", 1066, 0.50, 0.15, 53081.97, 2500000.0, 3),
    ("R3", "conservative", 165, 0.20, 0.10, 5000.0, 500000.0, 3),
    ("R3", "base", 165, 0.35, 0.20, 5000.0, 500000.0, 3),
    ("R3", "optimistic", 165, 0.50, 0.30, 5000.0, 500000.0, 3),
]


def load_scenario_assumptions(path: Path | None) -> pd.DataFrame:
    """Load editable JSON assumptions or documented defaults."""
    columns = [
        "recommendation_id",
        "scenario",
        "baseline_cases",
        "coverage_share",
        "assumed_reduction_share",
        "average_value_per_prevented_case_rub",
        "program_cost_rub",
        "evaluation_period_months",
    ]
    if path is None:
        return pd.DataFrame(DEFAULT_SCENARIOS, columns=columns)
    payload = json.loads(path.read_text(encoding="utf-8"))
    return pd.DataFrame(payload["scenarios"], columns=columns)


def calculate_scenarios(assumptions: pd.DataFrame) -> pd.DataFrame:
    """Calculate transparent benefits without deriving reduction from OR."""
    frame = assumptions.copy()
    for column in ("coverage_share", "assumed_reduction_share"):
        if ((frame[column] < 0) | (frame[column] > 1)).any():
            raise ValueError(f"{column} must be between 0 and 1")
    if (frame["program_cost_rub"] < 0).any():
        raise ValueError("program_cost_rub must be non-negative")
    frame["prevented_cases"] = (
        frame["baseline_cases"]
        * frame["coverage_share"]
        * frame["assumed_reduction_share"]
    )
    frame["potential_preserved_profit_rub"] = (
        frame["prevented_cases"] * frame["average_value_per_prevented_case_rub"]
    )
    frame["net_effect_rub"] = (
        frame["potential_preserved_profit_rub"] - frame["program_cost_rub"]
    )
    monthly_benefit = frame["potential_preserved_profit_rub"] / frame[
        "evaluation_period_months"
    ].replace(0, pd.NA)
    frame["payback_months"] = frame["program_cost_rub"] / monthly_benefit.replace(
        0, pd.NA
    )
    frame["scenario_label"] = SCENARIO_LABEL
    return frame
