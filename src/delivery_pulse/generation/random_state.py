"""Managed random state for deterministic generation."""

from typing import Any

import numpy as np

RandomState = Any


def create_random_state(seed: int) -> RandomState:
    """Create the only random number generator used by a pipeline run."""
    return np.random.default_rng(seed)
