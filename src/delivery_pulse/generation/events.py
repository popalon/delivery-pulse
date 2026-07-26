"""Synthetic route event generation."""

from __future__ import annotations

import pandas as pd

from delivery_pulse.generation.deliveries import DeliverySignals
from delivery_pulse.generation.random_state import RandomState


def generate_route_events(
    deliveries: pd.DataFrame,
    orders: pd.DataFrame,
    routes: pd.DataFrame,
    signals: DeliverySignals,
    rng: RandomState,
) -> pd.DataFrame:
    """Materialize operational event signals inside valid delivery intervals."""
    route_lookup = routes.set_index("route_id")
    order_lookup = orders.set_index("order_id")
    signal_map = {
        "loading_delay": signals.loading_delay,
        "traffic": signals.traffic_delay,
        "weather": signals.weather_delay,
        "route_deviation": signals.deviation_delay,
        "breakdown": signals.breakdown_delay,
        "unloading_delay": signals.unloading_delay,
    }
    cost_factor = {
        "loading_delay": 12.0,
        "traffic": 8.0,
        "weather": 10.0,
        "route_deviation": 15.0,
        "breakdown": 180.0,
        "unloading_delay": 10.0,
    }
    rows: list[dict[str, object]] = []
    event_id = 1

    for index, delivery in enumerate(deliveries.itertuples(index=False)):
        if delivery.delivery_status == "cancelled":
            continue
        order = order_lookup.loc[delivery.order_id]
        route = route_lookup.loc[order["route_id"]]
        departure = delivery.actual_departure_at
        completed = delivery.actual_delivery_at
        fallback_end = departure + pd.Timedelta(hours=12)
        interval_end = completed if pd.notna(completed) else fallback_end

        for event_type, values in signal_map.items():
            delay = int(values[index])
            if delay <= 0:
                continue
            if event_type == "loading_delay":
                event_at = delivery.planned_departure_at
                event_end = departure
                region = route["origin_region"]
            elif event_type == "unloading_delay":
                event_end = interval_end
                event_at = max(
                    departure,
                    event_end - pd.Timedelta(minutes=max(delay, 1)),
                )
                region = route["destination_region"]
            else:
                span_seconds = max((interval_end - departure).total_seconds(), 120)
                fraction = float(rng.uniform(0.15, 0.75))
                event_at = departure + pd.Timedelta(seconds=span_seconds * fraction)
                event_end = min(
                    interval_end,
                    event_at + pd.Timedelta(minutes=max(delay, 1)),
                )
                region = (
                    route["origin_region"]
                    if fraction < 0.5
                    else route["destination_region"]
                )
            severity = "high" if delay >= 180 else "medium" if delay >= 60 else "low"
            rows.append(
                {
                    "event_id": event_id,
                    "delivery_id": delivery.delivery_id,
                    "event_at": event_at,
                    "event_end_at": event_end,
                    "event_type": event_type,
                    "severity": severity,
                    "delay_minutes": delay,
                    "extra_cost": round(delay * cost_factor[event_type], 2),
                    "region": region,
                    "notes_code": f"{event_type}_{severity}",
                }
            )
            event_id += 1

    columns = [
        "event_id",
        "delivery_id",
        "event_at",
        "event_end_at",
        "event_type",
        "severity",
        "delay_minutes",
        "extra_cost",
        "region",
        "notes_code",
    ]
    return pd.DataFrame(rows, columns=columns)
