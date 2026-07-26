"""Synthetic route reference data."""

import pandas as pd

from delivery_pulse.generation.random_state import RandomState

REGIONS = (
    "central",
    "northwest",
    "south",
    "volga",
    "ural",
    "siberia",
    "far_east",
    "north_caucasus",
)


def generate_routes(count: int, rng: RandomState) -> pd.DataFrame:
    """Generate unique directed routes with heterogeneous risk and distance."""
    pairs = [
        (origin, destination)
        for origin in REGIONS
        for destination in REGIONS
        if origin != destination
    ]
    chosen = rng.choice(len(pairs), size=count, replace=False)
    rows: list[dict[str, object]] = []
    for route_id, pair_index in enumerate(chosen, start=1):
        origin, destination = pairs[int(pair_index)]
        distance = float(rng.uniform(180, 3_800))
        if distance < 500:
            route_class = "regional"
            speed = 55.0
        elif distance < 1_600:
            route_class = "interregional"
            speed = 62.0
        else:
            route_class = "long_haul"
            speed = 58.0
        rows.append(
            {
                "route_id": route_id,
                "route_code": (
                    f"R{route_id:03d}_{origin[:3].upper()}_{destination[:3].upper()}"
                ),
                "origin_region": origin,
                "destination_region": destination,
                "standard_distance_km": round(distance, 2),
                "standard_transit_hours": round(distance / speed + 2.0, 2),
                "route_class": route_class,
                "is_active": True,
            }
        )
    return pd.DataFrame(rows)
