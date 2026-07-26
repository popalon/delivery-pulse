"""Fleet maintenance history generation."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from delivery_pulse.generation.random_state import RandomState


def generate_initial_maintenance(
    vehicles: pd.DataFrame,
    start_date: date,
    rng: RandomState,
) -> pd.DataFrame:
    """Create one completed pre-period service for every active vehicle."""
    start = pd.Timestamp(start_date, tz="UTC")
    days_before = rng.integers(10, 100, size=len(vehicles))
    completed = start - pd.to_timedelta(days_before, unit="D")
    downtime = np.round(rng.uniform(4, 18, size=len(vehicles)), 2)
    started = completed - pd.to_timedelta(downtime, unit="h")
    km_gap = rng.uniform(500, 12_000, size=len(vehicles))
    odometer = np.maximum(
        vehicles["odometer_at_observation_start_km"].to_numpy(dtype=float) - km_gap,
        0,
    )
    return pd.DataFrame(
        {
            "maintenance_id": np.arange(1, len(vehicles) + 1, dtype=np.int64),
            "vehicle_id": vehicles["vehicle_id"].to_numpy(dtype=np.int64),
            "maintenance_type": np.full(len(vehicles), "scheduled", dtype=object),
            "started_at": started,
            "completed_at": completed,
            "odometer_km": np.round(odometer, 2),
            "cost_amount": np.round(rng.uniform(8_000, 35_000, size=len(vehicles)), 2),
            "downtime_hours": downtime,
            "issue_category": np.full(len(vehicles), None, dtype=object),
            "maintenance_status": np.full(len(vehicles), "completed", dtype=object),
        }
    )


def _next_idle_interval(
    candidate: pd.Timestamp,
    busy: list[tuple[pd.Timestamp, pd.Timestamp]],
    duration_hours: float,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    duration = pd.Timedelta(hours=duration_hours)
    start = candidate
    while True:
        end = start + duration
        overlapping_ends = [
            busy_end
            for busy_start, busy_end in busy
            if start < busy_end and end > busy_start
        ]
        if not overlapping_ends:
            return start, end
        start = max(overlapping_ends)


def generate_period_maintenance(
    initial: pd.DataFrame,
    vehicles: pd.DataFrame,
    deliveries: pd.DataFrame,
    route_events: pd.DataFrame,
    start_date: date,
    months: int,
    rng: RandomState,
) -> pd.DataFrame:
    """Add non-overlapping scheduled services and breakdown repairs."""
    rows = initial.to_dict("records")
    next_id = len(rows) + 1
    start = pd.Timestamp(start_date, tz="UTC")
    end = start + pd.DateOffset(months=months)
    vehicle_lookup = vehicles.set_index("vehicle_id")

    usable = deliveries.dropna(subset=["actual_departure_at"]).copy()
    usable["busy_end"] = usable["actual_delivery_at"].fillna(
        usable["actual_departure_at"] + pd.Timedelta(hours=12)
    )
    busy_by_vehicle: dict[int, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for vehicle_id, group in usable.groupby("vehicle_id"):
        busy_by_vehicle[int(vehicle_id)] = list(
            zip(group["actual_departure_at"], group["busy_end"], strict=True)
        )

    breakdowns = route_events.loc[route_events["event_type"] == "breakdown"]
    breakdown_by_vehicle: dict[int, list[pd.Timestamp]] = {}
    delivery_vehicle = deliveries.set_index("delivery_id")["vehicle_id"]
    for event in breakdowns.itertuples(index=False):
        vehicle_id = int(delivery_vehicle.loc[event.delivery_id])
        breakdown_by_vehicle.setdefault(vehicle_id, []).append(event.event_at)

    for vehicle_id in vehicles["vehicle_id"].astype(int):
        busy = busy_by_vehicle.get(vehicle_id, [])
        base_odometer = float(
            vehicle_lookup.loc[vehicle_id, "odometer_at_observation_start_km"]
        )
        vehicle_deliveries = usable.loc[usable["vehicle_id"] == vehicle_id]
        for day_offset in range(75, months * 31, 90):
            candidate = start + pd.Timedelta(days=day_offset)
            if candidate >= end:
                break
            service_start, service_end = _next_idle_interval(candidate, busy, 10.0)
            km_before = vehicle_deliveries.loc[
                vehicle_deliveries["actual_departure_at"] < service_start,
                "distance_actual_km",
            ].sum()
            rows.append(
                {
                    "maintenance_id": next_id,
                    "vehicle_id": vehicle_id,
                    "maintenance_type": "scheduled",
                    "started_at": service_start,
                    "completed_at": service_end,
                    "odometer_km": round(base_odometer + float(km_before), 2),
                    "cost_amount": round(float(rng.uniform(12_000, 45_000)), 2),
                    "downtime_hours": 10.0,
                    "issue_category": None,
                    "maintenance_status": "completed",
                }
            )
            busy.append((service_start, service_end))
            next_id += 1

        for breakdown_at in breakdown_by_vehicle.get(vehicle_id, []):
            candidate = breakdown_at.ceil("D") + pd.Timedelta(hours=6)
            repair_start, repair_end = _next_idle_interval(candidate, busy, 18.0)
            km_before = vehicle_deliveries.loc[
                vehicle_deliveries["actual_departure_at"] < repair_start,
                "distance_actual_km",
            ].sum()
            rows.append(
                {
                    "maintenance_id": next_id,
                    "vehicle_id": vehicle_id,
                    "maintenance_type": "repair",
                    "started_at": repair_start,
                    "completed_at": repair_end,
                    "odometer_km": round(base_odometer + float(km_before), 2),
                    "cost_amount": round(float(rng.uniform(35_000, 160_000)), 2),
                    "downtime_hours": 18.0,
                    "issue_category": "breakdown_repair",
                    "maintenance_status": "completed",
                }
            )
            busy.append((repair_start, repair_end))
            next_id += 1

    result = pd.DataFrame(rows)
    return result.sort_values(
        ["vehicle_id", "started_at", "maintenance_id"]
    ).reset_index(drop=True)
