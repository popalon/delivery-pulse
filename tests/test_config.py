"""Tests for the static project configuration."""

from delivery_pulse.config import CONFIG, ProjectConfig


def test_first_release_configuration() -> None:
    assert CONFIG.business_timezone == "Europe/Moscow"
    assert CONFIG.currency_code == "RUB"
    assert CONFIG.encoding.lower() == "utf-8"
    assert isinstance(CONFIG.default_seed, int)


def test_project_config_is_typed_and_has_stable_defaults() -> None:
    assert ProjectConfig() == CONFIG
