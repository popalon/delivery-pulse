"""Typed and secret-safe PostgreSQL configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PostgresConfig:
    """PostgreSQL connection settings with a redacted password."""

    host: str
    port: int
    dbname: str
    user: str
    password: str = field(repr=False)
    schema: str = "delivery_pulse"

    @property
    def connection_kwargs(self) -> dict[str, object]:
        """Return kwargs accepted by psycopg without logging them."""
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.dbname,
            "user": self.user,
            "password": self.password,
        }


class PublishConfigError(ValueError):
    """Raised when required publish configuration is missing or invalid."""


def load_postgres_config(
    *,
    host: str | None = None,
    port: int | None = None,
    dbname: str | None = None,
    user: str | None = None,
    password_env: str = "POSTGRES_PASSWORD",
    schema: str | None = None,
) -> PostgresConfig:
    """Load config with CLI values taking precedence over environment."""
    values = {
        "host": host or os.getenv("POSTGRES_HOST"),
        "dbname": dbname or os.getenv("POSTGRES_DB"),
        "user": user or os.getenv("POSTGRES_USER"),
        "schema": schema or os.getenv("POSTGRES_SCHEMA") or "delivery_pulse",
    }
    missing = [key for key in ("host", "dbname", "user") if not values[key]]
    password = os.getenv(password_env)
    if not password:
        missing.append(password_env)
    if missing:
        raise PublishConfigError(
            "missing PostgreSQL configuration: " + ", ".join(missing)
        )
    assert password is not None
    port_value = port or int(os.getenv("POSTGRES_PORT", "5432"))
    if not 1 <= port_value <= 65535:
        raise PublishConfigError("PostgreSQL port must be between 1 and 65535")
    schema_value = str(values["schema"])
    if not schema_value.replace("_", "").isalnum() or not schema_value[0].isalpha():
        raise PublishConfigError("schema must be a simple SQL identifier")
    return PostgresConfig(
        host=str(values["host"]),
        port=port_value,
        dbname=str(values["dbname"]),
        user=str(values["user"]),
        password=password,
        schema=schema_value,
    )
