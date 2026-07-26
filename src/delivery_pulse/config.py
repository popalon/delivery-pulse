"""Static configuration for the first DeliveryPulse release."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProjectConfig:
    """Typed, non-secret project settings."""

    business_timezone: str = "Europe/Moscow"
    currency_code: str = "RUB"
    default_seed: int = 42
    encoding: str = "utf-8"


CONFIG = ProjectConfig()
