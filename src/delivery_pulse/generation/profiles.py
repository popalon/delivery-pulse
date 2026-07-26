"""Named generation profiles."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GenerationProfile:
    """Default dataset sizes for one generation profile."""

    name: str
    orders: int
    customers: int
    routes: int
    drivers: int
    vehicles: int


PROFILES: dict[str, GenerationProfile] = {
    "test": GenerationProfile("test", 60, 8, 6, 10, 8),
    "demo": GenerationProfile("demo", 2_000, 40, 12, 80, 55),
    "full": GenerationProfile("full", 50_000, 180, 24, 700, 450),
}


def get_profile(name: str) -> GenerationProfile:
    """Return a known profile or raise a user-facing ValueError."""
    try:
        return PROFILES[name]
    except KeyError as error:
        choices = ", ".join(PROFILES)
        raise ValueError(
            f"unknown profile {name!r}; choose one of: {choices}"
        ) from error
