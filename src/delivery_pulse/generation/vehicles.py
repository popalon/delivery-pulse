"""Synthetic fleet generation."""

from datetime import date

import numpy as np
import pandas as pd

from delivery_pulse.generation.random_state import RandomState
from delivery_pulse.generation.routes import REGIONS

VEHICLE_CAPACITY = {
    "van": 1_500.0,
    "truck": 8_000.0,
    "refrigerated_truck": 12_000.0,
}
FUEL_CONSUMPTION = {
    "van": 12.5,
    "truck": 27.0,
    "refrigerated_truck": 31.5,
}


def generate_vehicles(count: int, start_date: date, rng: RandomState) -> pd.DataFrame:
    """Generate a heterogeneous active fleet with starting odometers."""
    vehicle_types = rng.choice(
        list(VEHICLE_CAPACITY),
        size=count,
        p=[0.35, 0.45, 0.20],
    )
    ages = np.clip(rng.gamma(2.0, 2.4, size=count).astype(int) + 1, 1, 14)
    consumption_noise = rng.normal(1.0, 0.05, size=count)

    return pd.DataFrame(
        {
            "vehicle_id": np.arange(1, count + 1, dtype=np.int64),
            "vehicle_code": [f"VEH-{index:05d}" for index in range(1, count + 1)],
            "vehicle_type": vehicle_types,
            "capacity_kg": [
                VEHICLE_CAPACITY[str(vehicle_type)] for vehicle_type in vehicle_types
            ],
            "manufacture_year": start_date.year - ages,
            "fuel_type": np.full(count, "diesel", dtype=object),
            "fuel_consumption_l_100km": np.round(
                [
                    FUEL_CONSUMPTION[str(vehicle_type)] * noise
                    for vehicle_type, noise in zip(
                        vehicle_types, consumption_noise, strict=True
                    )
                ],
                2,
            ),
            "odometer_at_observation_start_km": np.round(
                ages * rng.uniform(18_000, 42_000, size=count), 2
            ),
            "home_region": rng.choice(REGIONS, size=count),
            "service_status": np.full(count, "active", dtype=object),
        }
    )
