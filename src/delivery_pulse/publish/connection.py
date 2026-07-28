"""Lazy psycopg connection helpers."""

from __future__ import annotations

from typing import Any

from delivery_pulse.publish.config import PostgresConfig


def connect_postgres(config: PostgresConfig) -> Any:
    """Open a psycopg connection without importing the optional extra eagerly."""
    try:
        import psycopg
    except ImportError as error:
        raise RuntimeError(
            'PostgreSQL support is not installed; use pip install -e ".[postgres]"'
        ) from error
    return psycopg.connect(**config.connection_kwargs, autocommit=True)
