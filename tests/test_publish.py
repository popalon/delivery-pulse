"""Unit tests for optional PostgreSQL publication."""

from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb
import pytest

from delivery_pulse.__main__ import main
from delivery_pulse.generation import GenerationConfig, generate_dataset
from delivery_pulse.publish.config import (
    PostgresConfig,
    PublishConfigError,
    load_postgres_config,
)
from delivery_pulse.publish.mappings import (
    EXCLUDED_COLUMNS,
    PUBLISHED_TABLES,
    postgres_type,
)
from delivery_pulse.publish.models import PublishConfig
from delivery_pulse.publish.pipeline import PublishError, publish_postgres
from delivery_pulse.publish.postgres import create_and_load_table
from delivery_pulse.warehouse import BuildConfig, build_warehouse


def test_config_cli_precedence_and_secret_redaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "environment-host")
    monkeypatch.setenv("POSTGRES_DB", "analytics")
    monkeypatch.setenv("POSTGRES_USER", "reader")
    monkeypatch.setenv("SAFE_PASSWORD", "very-secret-value")
    config = load_postgres_config(
        host="cli-host",
        password_env="SAFE_PASSWORD",
        schema="delivery_pulse",
    )

    assert config.host == "cli-host"
    assert config.password == "very-secret-value"
    assert "very-secret-value" not in repr(config)


def test_missing_config_and_unsafe_schema_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in (
        "POSTGRES_HOST",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
    ):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(PublishConfigError, match="missing"):
        load_postgres_config()
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-only")
    with pytest.raises(PublishConfigError, match="schema"):
        load_postgres_config(
            host="localhost",
            dbname="test",
            user="test",
            schema="unsafe-name",
        )


def test_publish_cli_does_not_accept_or_print_plain_password(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("MISSING_PASSWORD", raising=False)
    code = main(
        [
            "publish",
            "postgres",
            "--database",
            str(tmp_path / "warehouse.duckdb"),
            "--host",
            "localhost",
            "--dbname",
            "test",
            "--user",
            "test",
            "--password-env",
            "MISSING_PASSWORD",
        ]
    )
    captured = capsys.readouterr()
    assert code == 2
    assert "MISSING_PASSWORD" in captured.err
    assert "password=" not in captured.err


def test_explicit_type_mappings_preserve_numeric_contract() -> None:
    assert postgres_type("BIGINT") == "BIGINT"
    assert postgres_type("DECIMAL(14,2)") == "NUMERIC(14,2)"
    assert postgres_type("DOUBLE") == "DOUBLE PRECISION"
    assert postgres_type("TIMESTAMP") == "TIMESTAMP"
    with pytest.raises(ValueError):
        postgres_type("STRUCT(a INTEGER)")


class _Copy:
    def __init__(self) -> None:
        self.rows: list[tuple[object, ...]] = []

    def __enter__(self) -> _Copy:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def write_row(self, row: tuple[object, ...]) -> None:
        self.rows.append(row)


class _Cursor:
    def __init__(self) -> None:
        self.copy_writer = _Copy()
        self.statements: list[str] = []

    def __enter__(self) -> _Cursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, statement: str, *_args: object) -> None:
        self.statements.append(statement)

    def copy(self, _statement: str) -> _Copy:
        return self.copy_writer


class _Target:
    def __init__(self) -> None:
        self.cursor_instance = _Cursor()

    def cursor(self) -> _Cursor:
        return self.cursor_instance


def test_copy_preserves_decimal_and_null() -> None:
    source = duckdb.connect()
    source.execute(
        "CREATE TABLE sample (id BIGINT, amount DECIMAL(14,2), note VARCHAR)"
    )
    source.execute("INSERT INTO sample VALUES (1, 12.34, NULL)")
    target = _Target()

    count = create_and_load_table(source, target, "stage", "sample")

    assert count == 1
    row = target.cursor_instance.copy_writer.rows[0]
    assert isinstance(row[1], Decimal)
    assert row[1] == Decimal("12.34")
    assert row[2] is None


def _postgres_config() -> PostgresConfig:
    return PostgresConfig("localhost", 5432, "test", "test", "secret")


def test_replace_requires_force_before_connecting(tmp_path: Path) -> None:
    with pytest.raises(PublishError, match="requires --force"):
        publish_postgres(
            PublishConfig(
                database=tmp_path / "missing.duckdb",
                postgres=_postgres_config(),
                mode="replace",
            )
        )


def test_publish_order_excludes_manifest() -> None:
    assert tuple(sorted(PUBLISHED_TABLES, key=PUBLISHED_TABLES.index)) == (
        PUBLISHED_TABLES
    )
    assert "quality_issues_manifest" not in PUBLISHED_TABLES
    assert "model_coefficients" not in PUBLISHED_TABLES
    assert "source_directory" in EXCLUDED_COLUMNS["warehouse_metadata"]


class _Transaction:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_args: object) -> None:
        return None


class _RollbackTarget:
    def __init__(self) -> None:
        self.rollback_calls = 0
        self.closed = False

    def transaction(self) -> _Transaction:
        return _Transaction()

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.closed = True


class _Source:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_failure_rolls_back_and_closes_connections(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = _RollbackTarget()
    source = _Source()
    monkeypatch.setattr("delivery_pulse.publish.pipeline.load_context", lambda _p: None)
    monkeypatch.setattr(
        "delivery_pulse.publish.pipeline.database_sha256", lambda _p: "hash"
    )
    monkeypatch.setattr(
        "delivery_pulse.publish.pipeline.duckdb.connect", lambda *_a, **_k: source
    )
    monkeypatch.setattr(
        "delivery_pulse.publish.pipeline.connect_postgres", lambda _c: target
    )
    monkeypatch.setattr(
        "delivery_pulse.publish.pipeline.schema_exists", lambda *_a: False
    )

    def fail_load(*_args: object) -> dict[str, int]:
        raise RuntimeError("synthetic load failure")

    monkeypatch.setattr(
        "delivery_pulse.publish.pipeline.load_staging_schema", fail_load
    )
    with pytest.raises(PublishError, match="rolled back"):
        publish_postgres(PublishConfig(tmp_path / "source.duckdb", _postgres_config()))

    assert target.rollback_calls == 1
    assert target.closed
    assert source.closed


def test_create_refuses_existing_schema(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = _RollbackTarget()
    source = _Source()
    monkeypatch.setattr("delivery_pulse.publish.pipeline.load_context", lambda _p: None)
    monkeypatch.setattr(
        "delivery_pulse.publish.pipeline.database_sha256", lambda _p: "hash"
    )
    monkeypatch.setattr(
        "delivery_pulse.publish.pipeline.duckdb.connect", lambda *_a, **_k: source
    )
    monkeypatch.setattr(
        "delivery_pulse.publish.pipeline.connect_postgres", lambda _c: target
    )
    monkeypatch.setattr(
        "delivery_pulse.publish.pipeline.schema_exists", lambda *_a: True
    )

    with pytest.raises(PublishError, match="already exists"):
        publish_postgres(PublishConfig(tmp_path / "source.duckdb", _postgres_config()))

    assert target.rollback_calls == 1
    assert target.closed
    assert source.closed


def test_compose_and_dashboard_sql_are_safe_and_publish_only() -> None:
    root = Path(__file__).resolve().parents[1]
    compose = (root / "compose.yaml").read_text(encoding="utf-8")
    assert "postgres:" in compose
    assert "metabase:" in compose
    assert "healthcheck:" in compose
    assert "privileged:" not in compose
    assert "/home/" not in compose
    assert "${POSTGRES_PASSWORD}" in compose
    dashboard_files = sorted((root / "sql" / "dashboard").glob("*.sql"))
    assert len(dashboard_files) == 5
    for path in dashboard_files:
        sql = path.read_text(encoding="utf-8").lower()
        assert "delivery_pulse." in sql
        assert "/home/" not in sql
        assert "quality_issues_manifest" not in sql
        assert "data/raw" not in sql


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("DELIVERY_PULSE_TEST_POSTGRES"),
    reason="DELIVERY_PULSE_TEST_POSTGRES is not configured",
)
def test_postgres_integration_is_explicitly_opt_in(tmp_path: Path) -> None:
    """Live create/replace/validation remains isolated and explicitly opt-in."""
    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    dsn = os.environ["DELIVERY_PULSE_TEST_POSTGRES"]
    values = conninfo_to_dict(dsn)
    schema = f"delivery_pulse_test_{uuid.uuid4().hex[:10]}"
    config = PostgresConfig(
        host=values.get("host", "localhost"),
        port=int(values.get("port", "5432")),
        dbname=values["dbname"],
        user=values["user"],
        password=values["password"],
        schema=schema,
    )
    test_root = tmp_path / schema
    raw = generate_dataset(
        GenerationConfig(
            profile="test",
            orders=80,
            seed=42,
            start_date=date(2024, 1, 1),
            months=2,
            output_dir=test_root / "raw",
        )
    ).output_dir
    database = test_root / "warehouse.duckdb"
    build_warehouse(BuildConfig(raw, database))
    try:
        created = publish_postgres(PublishConfig(database, config))
        assert created.validation.passed
        with pytest.raises(PublishError, match="already exists"):
            publish_postgres(PublishConfig(database, config))
        replaced = publish_postgres(
            PublishConfig(database, config, mode="replace", force=True)
        )
        assert replaced.validation.passed
        with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s ORDER BY table_name",
                (schema,),
            )
            tables = {row[0] for row in cursor.fetchall()}
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.schemata "
                "WHERE schema_name IN (%s, %s)",
                (f"{schema}__staging", f"{schema}__previous"),
            )
            staging_count = int(cursor.fetchone()[0])
        assert set(PUBLISHED_TABLES) | {"publish_metadata"} == tables
        assert staging_count == 0
    finally:
        with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
            cursor.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
