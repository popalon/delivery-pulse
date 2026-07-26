"""Synthetic driver generation."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from delivery_pulse.generation.random_state import RandomState
from delivery_pulse.generation.routes import REGIONS


def generate_drivers(count: int, start_date: date, rng: RandomState) -> pd.DataFrame:
    """Generate non-personal driver records."""
    experience = np.round(rng.gamma(shape=2.2, scale=3.2, size=count), 1)
    return pd.DataFrame(
        {
            "driver_id": np.arange(1, count + 1, dtype=np.int64),
            "driver_code": [f"DRV-{index:05d}" for index in range(1, count + 1)],
            "hire_date": [
                start_date - timedelta(days=int(years * 365 + rng.integers(30, 500)))
                for years in experience
            ],
            "experience_years": experience,
            "license_class": rng.choice(
                ["b", "c", "ce"], size=count, p=[0.15, 0.5, 0.35]
            ),
            "home_region": rng.choice(REGIONS, size=count),
            "employment_status": np.full(count, "active", dtype=object),
        }
    )
