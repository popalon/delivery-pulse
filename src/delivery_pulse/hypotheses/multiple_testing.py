"""Multiple-testing adjustments."""

from __future__ import annotations

import numpy as np


def benjamini_hochberg(p_values: list[float | None]) -> list[float | None]:
    """Return BH-adjusted p-values while preserving missing positions."""
    valid = [
        (index, value) for index, value in enumerate(p_values) if value is not None
    ]
    if not valid:
        return [None] * len(p_values)
    order = sorted(valid, key=lambda item: (float(item[1]), item[0]))
    adjusted: dict[int, float] = {}
    running = 1.0
    total = len(order)
    for rank_from_end, (index, value) in enumerate(reversed(order), start=1):
        rank = total - rank_from_end + 1
        candidate = min(1.0, float(value) * total / rank)
        running = min(running, candidate)
        adjusted[index] = running
    return [adjusted.get(index) for index in range(len(p_values))]


def deterministic_bootstrap_mean_difference(
    exposed: np.ndarray,
    unexposed: np.ndarray,
    *,
    seed: int,
    iterations: int = 500,
) -> tuple[float, float, float]:
    """Bootstrap a mean difference with explicit local random state."""
    generator = np.random.default_rng(seed)
    estimates = np.empty(iterations)
    for index in range(iterations):
        left = generator.choice(exposed, size=len(exposed), replace=True)
        right = generator.choice(unexposed, size=len(unexposed), replace=True)
        estimates[index] = float(left.mean() - right.mean())
    point = float(exposed.mean() - unexposed.mean())
    low, high = np.quantile(estimates, [0.025, 0.975])
    return point, float(low), float(high)
