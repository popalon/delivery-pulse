"""Synthetic delivery execution and financial generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from delivery_pulse.generation.random_state import RandomState


@dataclass(frozen=True, slots=True)
class DeliverySignals:
    """Latent operational events used to build route event records."""

    loading_delay: Any
    unloading_delay: Any
    traffic_delay: Any
    weather_delay: Any
    deviation_delay: Any
    breakdown_delay: Any


def _choose_vehicle(
    cargo_type: str,
    weight: float,
    vehicles: pd.DataFrame,
    rng: RandomState,
) -> int:
    refrigerated = vehicles["vehicle_type"] == "refrigerated_truck"
    type_mask = (
        refrigerated
        if cargo_type == "refrigerated"
        else np.ones(len(vehicles), dtype=bool)
    )
    capacity = vehicles["capacity_kg"].to_numpy(dtype=float)
    eligible = vehicles.loc[type_mask & (capacity >= weight)]
    if eligible.empty:
        eligible = vehicles.loc[type_mask].sort_values("capacity_kg").tail(1)
    return int(rng.choice(eligible["vehicle_id"].to_numpy()))


def generate_deliveries(
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    routes: pd.DataFrame,
    drivers: pd.DataFrame,
    vehicles: pd.DataFrame,
    initial_maintenance: pd.DataFrame,
    start_date: date,
    rng: RandomState,
) -> tuple[pd.DataFrame, pd.DataFrame, DeliverySignals]:
    """Generate one deterministic delivery attempt per order."""
    count = len(orders)
    route_lookup = routes.set_index("route_id")
    customer_lookup = customers.set_index("customer_id")
    vehicle_lookup = vehicles.set_index("vehicle_id")
    initial_lookup = initial_maintenance.set_index("vehicle_id")

    status = rng.choice(
        ["delivered", "failed", "cancelled"],
        size=count,
        p=[0.91, 0.035, 0.055],
    )
    overload_flags = rng.random(count) < 0.004
    vehicle_ids = np.empty(count, dtype=np.int64)
    driver_ids = rng.choice(drivers["driver_id"].to_numpy(), size=count)
    cumulative_km = {int(vehicle_id): 0.0 for vehicle_id in vehicles["vehicle_id"]}
    last_service_km = {int(vehicle_id): 0.0 for vehicle_id in vehicles["vehicle_id"]}
    preperiod_gap = {
        int(vehicle_id): float(
            vehicle_lookup.loc[vehicle_id, "odometer_at_observation_start_km"]
            - initial_lookup.loc[vehicle_id, "odometer_km"]
        )
        for vehicle_id in vehicles["vehicle_id"]
    }
    period_service_occurred = {
        int(vehicle_id): False for vehicle_id in vehicles["vehicle_id"]
    }
    observation_start = pd.Timestamp(start_date, tz="UTC")
    next_service_at = {
        int(vehicle_id): observation_start + pd.Timedelta(days=75)
        for vehicle_id in vehicles["vehicle_id"]
    }

    loading_delay = np.zeros(count, dtype=int)
    unloading_delay = np.zeros(count, dtype=int)
    traffic_delay = np.zeros(count, dtype=int)
    weather_delay = np.zeros(count, dtype=int)
    deviation_delay = np.zeros(count, dtype=int)
    breakdown_delay = np.zeros(count, dtype=int)
    actual_departures: list[pd.Timestamp | pd.NaTType] = []
    actual_deliveries: list[pd.Timestamp | pd.NaTType] = []
    actual_distances = np.full(count, np.nan)
    fuel_cost = np.zeros(count)
    driver_cost = np.zeros(count)
    toll_cost = np.zeros(count)
    maintenance_cost = np.zeros(count)
    other_cost = np.zeros(count)
    penalty = np.zeros(count)
    updated_orders = orders.copy()

    for index, order in enumerate(orders.itertuples(index=False)):
        route = route_lookup.loc[order.route_id]
        customer = customer_lookup.loc[order.customer_id]
        vehicle_id = _choose_vehicle(
            str(order.cargo_type),
            float(order.cargo_weight_kg),
            vehicles,
            rng,
        )
        vehicle_ids[index] = vehicle_id
        effective_weight = float(order.cargo_weight_kg)
        if overload_flags[index] and status[index] != "cancelled":
            capacity = float(vehicle_lookup.loc[vehicle_id, "capacity_kg"])
            effective_weight = capacity * float(rng.uniform(1.01, 1.05))
            updated_orders.loc[index, "cargo_weight_kg"] = round(effective_weight, 2)

        if status[index] == "cancelled":
            actual_departures.append(pd.NaT)
            actual_deliveries.append(pd.NaT)
            continue

        route_risk = 0.04 + 0.025 * (int(order.route_id) % 5)
        enterprise_loading = (
            1.35 if customer["customer_segment"] == "enterprise" else 1.0
        )
        loading_delay[index] = int(
            rng.gamma(1.8, 18.0) * enterprise_loading
            if rng.random() < 0.34
            else rng.integers(0, 8)
        )
        if rng.random() < 0.22 + route_risk:
            traffic_delay[index] = int(rng.gamma(2.0, 28.0))
        winter = order.requested_pickup_at.month in {1, 2, 11, 12}
        if rng.random() < (0.13 if winter else 0.045):
            weather_delay[index] = int(rng.gamma(2.0, 35.0))
        if rng.random() < 0.08 + route_risk / 2:
            deviation_delay[index] = int(rng.gamma(1.7, 22.0))
        if rng.random() < 0.26:
            unloading_delay[index] = int(rng.gamma(1.8, 16.0))

        start_gap = (
            0.0 if period_service_occurred[vehicle_id] else preperiod_gap[vehicle_id]
        )
        while order.requested_pickup_at >= next_service_at[vehicle_id]:
            last_service_km[vehicle_id] = cumulative_km[vehicle_id]
            start_gap = 0
            period_service_occurred[vehicle_id] = True
            next_service_at[vehicle_id] += pd.Timedelta(days=90)
        km_since_service = (
            start_gap + cumulative_km[vehicle_id] - last_service_km[vehicle_id]
        )
        breakdown_probability = 0.003 + max(km_since_service - 18_000, 0) / 450_000
        if rng.random() < min(breakdown_probability, 0.06):
            breakdown_delay[index] = int(rng.integers(120, 600))

        departure = order.requested_pickup_at + pd.Timedelta(
            minutes=int(loading_delay[index])
        )
        distance_factor = max(
            0.85,
            rng.normal(1.0 + deviation_delay[index] / 2_500, 0.035),
        )
        distance = float(order.distance_planned_km) * distance_factor
        if status[index] == "failed":
            distance *= float(rng.uniform(0.2, 0.85))
        actual_distances[index] = round(distance, 2)
        cumulative_km[vehicle_id] += distance

        base_hours = float(route["standard_transit_hours"]) * float(
            rng.lognormal(0, 0.08)
        )
        event_minutes = (
            traffic_delay[index]
            + weather_delay[index]
            + deviation_delay[index]
            + unloading_delay[index]
            + breakdown_delay[index]
        )
        trip_hours = base_hours + event_minutes / 60
        actual_departures.append(departure)
        if status[index] == "delivered":
            completed = departure + pd.Timedelta(hours=trip_hours)
            actual_deliveries.append(completed)
            late_minutes = max(
                (completed - order.promised_delivery_at).total_seconds() / 60,
                0,
            )
        else:
            actual_deliveries.append(pd.NaT)
            late_minutes = 0

        vehicle = vehicle_lookup.loc[vehicle_id]
        load_ratio = effective_weight / float(vehicle["capacity_kg"])
        fuel_cost[index] = (
            distance
            * float(vehicle["fuel_consumption_l_100km"])
            / 100
            * 62
            * (1 + 0.12 * min(load_ratio, 1.2))
        )
        driver_cost[index] = trip_hours * 650
        toll_cost[index] = (
            distance * 0.9 if route["route_class"] == "long_haul" else distance * 0.25
        )
        maintenance_cost[index] = distance * 0.85
        other_cost[index] = 700 + float(rng.gamma(1.7, 500))
        if late_minutes > 360:
            penalty[index] = float(order.quoted_revenue) * 0.12
        elif late_minutes > 120:
            penalty[index] = float(order.quoted_revenue) * 0.05

    updated_orders["order_status"] = np.where(
        status == "cancelled", "cancelled", "completed"
    )
    deliveries = pd.DataFrame(
        {
            "delivery_id": np.arange(1, count + 1, dtype=np.int64),
            "order_id": updated_orders["order_id"].to_numpy(dtype=np.int64),
            "driver_id": driver_ids.astype(np.int64),
            "vehicle_id": vehicle_ids,
            "planned_departure_at": updated_orders["requested_pickup_at"],
            "actual_departure_at": actual_departures,
            "actual_delivery_at": actual_deliveries,
            "distance_actual_km": np.round(actual_distances, 2),
            "delivery_status": status,
            "fuel_cost": np.round(fuel_cost, 2),
            "driver_cost": np.round(driver_cost, 2),
            "toll_cost": np.round(toll_cost, 2),
            "maintenance_allocated_cost": np.round(maintenance_cost, 2),
            "other_cost": np.round(other_cost, 2),
            "penalty_amount": np.round(penalty, 2),
        }
    )
    signals = DeliverySignals(
        loading_delay=loading_delay,
        unloading_delay=unloading_delay,
        traffic_delay=traffic_delay,
        weather_delay=weather_delay,
        deviation_delay=deviation_delay,
        breakdown_delay=breakdown_delay,
    )
    return deliveries, updated_orders, signals
