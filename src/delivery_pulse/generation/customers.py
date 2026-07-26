"""Synthetic customer generation."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from delivery_pulse.generation.random_state import RandomState


def generate_customers(count: int, start_date: date, rng: RandomState) -> pd.DataFrame:
    """Generate synthetic customers with heterogeneous commercial terms."""
    segments = rng.choice(
        ["small", "medium", "enterprise"],
        size=count,
        p=[0.55, 0.30, 0.15],
    )
    industries = rng.choice(
        ["retail", "manufacturing", "pharma", "food", "ecommerce"],
        size=count,
    )
    sla_by_segment = {"small": 48, "medium": 42, "enterprise": 36}
    terms_by_segment = {"small": 14, "medium": 30, "enterprise": 45}
    offsets = rng.integers(60, 1_200, size=count)

    return pd.DataFrame(
        {
            "customer_id": np.arange(1, count + 1, dtype=np.int64),
            "customer_name": [
                f"Synthetic Customer {index:04d}" for index in range(1, count + 1)
            ],
            "customer_segment": segments,
            "industry": industries,
            "contract_start_date": [
                start_date - timedelta(days=int(offset)) for offset in offsets
            ],
            "contract_end_date": [None] * count,
            "default_sla_hours": [sla_by_segment[str(segment)] for segment in segments],
            "payment_terms_days": [
                terms_by_segment[str(segment)] for segment in segments
            ],
            "is_active": np.ones(count, dtype=bool),
        }
    )
