"""Pre-model feasibility checks fixed by the hypothesis protocol."""

from __future__ import annotations

import pandas as pd

from delivery_pulse.hypotheses.models import FeasibilityResult


def _binary_feasibility(
    hypothesis_id: str,
    frame: pd.DataFrame,
    *,
    outcome: str,
    exposure: str,
    estimated_parameters: int,
    minimum_exposed: int,
    minimum_events: int,
) -> FeasibilityResult:
    complete = frame.dropna(subset=[outcome, exposure])
    events = int(complete[outcome].sum())
    exposed = int((complete[exposure] == 1).sum())
    unexposed = int((complete[exposure] == 0).sum())
    exposed_events = int(complete.loc[complete[exposure] == 1, outcome].sum())
    epv = events / estimated_parameters
    feasible = (
        exposed >= minimum_exposed
        and unexposed >= minimum_exposed
        and events >= minimum_events
        and epv >= 10
        and complete[exposure].nunique() == 2
    )
    return FeasibilityResult(
        hypothesis_id=hypothesis_id,
        feasible=feasible,
        observations=len(complete),
        events=events,
        exposed=exposed,
        unexposed=unexposed,
        exposed_events=exposed_events,
        missing_rate=1 - len(complete) / len(frame),
        estimated_parameters=estimated_parameters,
        events_per_parameter=epv,
        reason=(
            "Sample, event count, variation, and EPV meet the protocol."
            if feasible
            else "One or more protocol thresholds for sample, events, or EPV fail."
        ),
    )


def assess_feasibility(
    delivery: pd.DataFrame,
    vehicle_month: pd.DataFrame,
    *,
    min_group_size: int,
) -> tuple[FeasibilityResult, ...]:
    """Assess H1–H6 without using direction, coefficients, or p-values."""
    delivered = delivery.loc[delivery["delivery_status"] == "delivered"]
    financial = delivery.loc[delivery["financial_data_complete"] == 1]
    results = [
        _binary_feasibility(
            "H1",
            delivered,
            outcome="is_late",
            exposure="has_loading_delay",
            estimated_parameters=35,
            minimum_exposed=200,
            minimum_events=30,
        ),
        _binary_feasibility(
            "H2",
            delivered.assign(
                is_express=(delivered["priority"] == "express").astype(int)
            ),
            outcome="is_late",
            exposure="is_express",
            estimated_parameters=40,
            minimum_exposed=500,
            minimum_events=30,
        ),
        _binary_feasibility(
            "H3",
            financial,
            outcome="is_loss_making",
            exposure="has_breakdown",
            estimated_parameters=35,
            minimum_exposed=100,
            minimum_events=30,
        ),
    ]
    vehicle_complete = vehicle_month.loc[
        (vehicle_month["actual_distance_km"] > 0) & (vehicle_month["trip_hours"] > 0)
    ]
    h4_events = int(vehicle_complete["breakdown_count"].sum())
    h4_parameters = 18
    h4_epv = h4_events / h4_parameters
    h4_feasible = (
        len(vehicle_complete) >= 500
        and h4_events >= 100
        and h4_epv >= 10
        and vehicle_complete["had_scheduled_maintenance_previous_month"].nunique() == 2
    )
    results.append(
        FeasibilityResult(
            "H4",
            h4_feasible,
            len(vehicle_complete),
            h4_events,
            int(
                (
                    vehicle_complete["had_scheduled_maintenance_previous_month"] == 1
                ).sum()
            ),
            int(
                (
                    vehicle_complete["had_scheduled_maintenance_previous_month"] == 0
                ).sum()
            ),
            int(
                vehicle_complete.loc[
                    vehicle_complete["had_scheduled_maintenance_previous_month"] == 1,
                    "breakdown_count",
                ].sum()
            ),
            1 - len(vehicle_complete) / len(vehicle_month),
            h4_parameters,
            h4_epv,
            (
                "Vehicle-month exposure and event thresholds meet the protocol."
                if h4_feasible
                else "Vehicle-month exposure, variation, or events are insufficient."
            ),
        )
    )
    customer_counts = financial.groupby("customer_id").size()
    eligible_customers = customer_counts.loc[customer_counts >= min_group_size]
    h5_feasible = len(eligible_customers) >= 10
    results.append(
        FeasibilityResult(
            "H5",
            h5_feasible,
            int(customer_counts.sum()),
            0,
            len(eligible_customers),
            int((customer_counts < min_group_size).sum()),
            0,
            1 - len(financial) / len(delivery),
            len(eligible_customers) + 40,
            None,
            (
                "At least ten customers meet the pre-specified volume threshold."
                if h5_feasible
                else "Too few customers meet the pre-specified volume threshold."
            ),
        )
    )
    h6 = _binary_feasibility(
        "H6",
        financial,
        outcome="is_loss_making",
        exposure="operational_overload",
        estimated_parameters=20,
        minimum_exposed=100,
        minimum_events=20,
    )
    overload_events_ok = h6.exposed_events >= 20
    cells = (
        financial.groupby("vehicle_type", observed=True)
        .apply(
            lambda group: pd.Series(
                {
                    "overload_n": int(group["operational_overload"].sum()),
                    "overload_events": int(
                        (
                            (group["operational_overload"] == 1)
                            & (group["is_loss_making"] == 1)
                        ).sum()
                    ),
                }
            ),
            include_groups=False,
        )
        .reset_index()
    )
    cell_ok = bool(
        ((cells["overload_n"] >= 30) & (cells["overload_events"] >= 5)).all()
    )
    h6.feasible = h6.feasible and overload_events_ok and cell_ok
    h6.reason = (
        "All pre-specified overload interaction cells meet thresholds."
        if h6.feasible
        else "Overload losses or pre-specified vehicle-type cells are insufficient."
    )
    results.append(h6)
    return tuple(results)
