"""Synthetic order generation."""

from datetime import date

import numpy as np
import pandas as pd

from delivery_pulse.generation.random_state import RandomState


def _sample_pickup_times(
    count: int,
    start_date: date,
    months: int,
    rng: RandomState,
) -> pd.DatetimeIndex:
    start = pd.Timestamp(start_date, tz="Europe/Moscow")
    end = start + pd.DateOffset(months=months)
    days = pd.date_range(start, end, inclusive="left", freq="D")
    weekday_weight = np.array([1.05, 1.08, 1.05, 1.0, 1.12, 0.68, 0.55], dtype=float)
    seasonal = 1.0 + 0.22 * np.sin(2 * np.pi * (days.month.to_numpy() - 1) / 12)
    weights = weekday_weight[days.dayofweek.to_numpy()] * seasonal
    selected_days = days[rng.choice(len(days), size=count, p=weights / weights.sum())]
    hours = rng.choice(
        np.arange(6, 21),
        size=count,
        p=np.array([2, 3, 5, 7, 9, 10, 10, 9, 8, 8, 7, 6, 5, 4, 3]) / 96,
    )
    minutes = rng.integers(0, 60, size=count)
    local = (
        selected_days
        + pd.to_timedelta(hours, unit="h")
        + pd.to_timedelta(minutes, unit="m")
    )
    return pd.DatetimeIndex(local).tz_convert("UTC")


def generate_orders(
    count: int,
    start_date: date,
    months: int,
    customers: pd.DataFrame,
    routes: pd.DataFrame,
    rng: RandomState,
) -> pd.DataFrame:
    """Generate orders with customer, calendar, route, and pricing effects."""
    customer_scale = customers["customer_segment"].map(
        {"small": 0.7, "medium": 1.5, "enterprise": 3.5}
    )
    customer_noise = rng.lognormal(0, 0.45, size=len(customers))
    customer_weights = customer_scale.to_numpy() * customer_noise
    customer_ids = rng.choice(
        customers["customer_id"].to_numpy(),
        size=count,
        p=customer_weights / customer_weights.sum(),
    )

    route_distance = routes["standard_distance_km"].to_numpy(dtype=float)
    route_weights = 1 / np.sqrt(route_distance)
    route_ids = rng.choice(
        routes["route_id"].to_numpy(),
        size=count,
        p=route_weights / route_weights.sum(),
    )
    pickup_at = _sample_pickup_times(count, start_date, months, rng)
    lead_hours = rng.integers(8, 96, size=count)
    created_at = pickup_at - pd.to_timedelta(lead_hours, unit="h")
    priority = rng.choice(["standard", "express"], size=count, p=[0.82, 0.18])
    cargo_type = rng.choice(
        ["general", "fragile", "refrigerated"],
        size=count,
        p=[0.67, 0.18, 0.15],
    )

    cargo_weight = np.empty(count)
    general = cargo_type == "general"
    fragile = cargo_type == "fragile"
    refrigerated = cargo_type == "refrigerated"
    cargo_weight[general] = rng.lognormal(7.7, 0.75, size=int(general.sum()))
    cargo_weight[fragile] = rng.lognormal(7.1, 0.65, size=int(fragile.sum()))
    cargo_weight[refrigerated] = rng.lognormal(8.1, 0.55, size=int(refrigerated.sum()))
    cargo_weight = np.clip(cargo_weight, 80, 10_500)

    route_lookup = routes.set_index("route_id")
    distances = route_lookup.loc[route_ids, "standard_distance_km"].to_numpy(
        dtype=float
    )
    transit = route_lookup.loc[route_ids, "standard_transit_hours"].to_numpy(
        dtype=float
    )
    planned_distance = distances * rng.normal(1.0, 0.035, size=count)
    sla_factor = np.where(priority == "express", 1.08, 1.35)
    promised_at = pickup_at + pd.to_timedelta(
        np.maximum(transit * sla_factor + 3, 8), unit="h"
    )

    customer_lookup = customers.set_index("customer_id")
    segment = customer_lookup.loc[customer_ids, "customer_segment"].to_numpy()
    segment_price = pd.Series(segment).map(
        {"small": 1.10, "medium": 1.00, "enterprise": 0.91}
    )
    express_price = np.where(priority == "express", 1.25, 1.0)
    cargo_price = np.where(cargo_type == "refrigerated", 1.22, 1.0)
    quoted = (
        (5_500 + planned_distance * 43 + cargo_weight * 1.25)
        * segment_price.to_numpy()
        * express_price
        * cargo_price
    )
    quoted *= rng.normal(1.0, 0.07, size=count)

    result = pd.DataFrame(
        {
            "order_id": np.arange(1, count + 1, dtype=np.int64),
            "customer_id": customer_ids.astype(np.int64),
            "route_id": route_ids.astype(np.int64),
            "created_at": created_at,
            "requested_pickup_at": pickup_at,
            "promised_delivery_at": promised_at,
            "cargo_type": cargo_type,
            "cargo_weight_kg": np.round(cargo_weight, 2),
            "distance_planned_km": np.round(planned_distance, 2),
            "quoted_revenue": np.round(np.maximum(quoted, 0), 2),
            "priority": priority,
            "order_status": np.full(count, "assigned", dtype=object),
        }
    )
    return result.sort_values(["requested_pickup_at", "order_id"]).reset_index(
        drop=True
    )
