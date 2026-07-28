"""Cross-database validation metrics for publication."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import duckdb

from delivery_pulse.publish.mappings import PRIMARY_KEYS, PUBLISHED_TABLES
from delivery_pulse.publish.models import PublishValidationReport, ValidationCheck


def _source_metrics(connection: duckdb.DuckDBPyConnection) -> dict[str, object]:
    row = connection.execute(
        """
        SELECT
            SUM(net_revenue), SUM(total_delivery_cost), SUM(delivery_profit),
            count_if(p.delivery_status = 'delivered'),
            count_if(p.delivery_status = 'failed'),
            count_if(p.delivery_status = 'cancelled'),
            AVG(CASE WHEN p.delivery_status = 'delivered'
                     THEN p.is_on_time::INTEGER END),
            count_if(f.is_loss_making)
        FROM delivery_financial_mart AS f
        JOIN delivery_performance_mart AS p USING (delivery_id)
        """
    ).fetchone()
    names = (
        "net_revenue",
        "delivery_cost",
        "delivery_profit",
        "delivered",
        "failed",
        "cancelled",
        "otd",
        "loss_making",
    )
    return dict(zip(names, row, strict=True))


def _target_metrics(connection: Any, schema: str) -> dict[str, object]:
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT
                SUM(f.net_revenue), SUM(f.total_delivery_cost),
                SUM(f.delivery_profit),
                count(*) FILTER (WHERE p.delivery_status = 'delivered'),
                count(*) FILTER (WHERE p.delivery_status = 'failed'),
                count(*) FILTER (WHERE p.delivery_status = 'cancelled'),
                AVG(CASE WHEN p.delivery_status = 'delivered'
                         THEN p.is_on_time::INTEGER END),
                count(*) FILTER (WHERE f.is_loss_making)
            FROM "{schema}".delivery_financial_mart AS f
            JOIN "{schema}".delivery_performance_mart AS p USING (delivery_id)
            """
        )
        row = cursor.fetchone()
    names = (
        "net_revenue",
        "delivery_cost",
        "delivery_profit",
        "delivered",
        "failed",
        "cancelled",
        "otd",
        "loss_making",
    )
    return dict(zip(names, row, strict=True))


def validate_publication(
    source: duckdb.DuckDBPyConnection,
    target: Any,
    schema: str,
) -> PublishValidationReport:
    """Reconcile rows, unique keys, financial sums, statuses, and OTD."""
    checks: list[ValidationCheck] = []
    for table in PUBLISHED_TABLES:
        source_count = int(
            source.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        )
        with target.cursor() as cursor:
            cursor.execute(f'SELECT COUNT(*) FROM "{schema}"."{table}"')
            target_count = int(cursor.fetchone()[0])
        checks.append(
            ValidationCheck(
                f"row_count.{table}",
                source_count == target_count,
                str(source_count),
                str(target_count),
                f"{table} row count",
            )
        )
    for table, keys in PRIMARY_KEYS.items():
        key_sql = ", ".join(f'"{key}"' for key in keys)
        with target.cursor() as cursor:
            cursor.execute(
                f'SELECT COUNT(*) FROM (SELECT {key_sql} FROM "{schema}"."{table}" '
                f"GROUP BY {key_sql} HAVING COUNT(*) > 1) AS duplicates"
            )
            duplicates = int(cursor.fetchone()[0])
        checks.append(
            ValidationCheck(
                f"unique_key.{table}",
                duplicates == 0,
                "0",
                str(duplicates),
                f"{table} unique grain",
            )
        )
    source_metrics = _source_metrics(source)
    target_metrics = _target_metrics(target, schema)
    for metric, source_value in source_metrics.items():
        target_value = target_metrics[metric]
        if metric in {"net_revenue", "delivery_cost", "delivery_profit"}:
            passed = Decimal(str(source_value)) == Decimal(str(target_value))
        elif metric == "otd":
            passed = abs(float(str(source_value)) - float(str(target_value))) <= 1e-12
        else:
            passed = source_value == target_value
        checks.append(
            ValidationCheck(
                f"metric.{metric}",
                passed,
                str(source_value),
                str(target_value),
                f"control metric {metric}",
            )
        )
    source_version = str(
        source.execute(
            "SELECT warehouse_schema_version FROM warehouse_metadata"
        ).fetchone()[0]
    )
    with target.cursor() as cursor:
        cursor.execute(
            f'SELECT warehouse_schema_version FROM "{schema}".warehouse_metadata'
        )
        target_version = str(cursor.fetchone()[0])
    checks.append(
        ValidationCheck(
            "metadata.warehouse_schema_version",
            source_version == target_version,
            source_version,
            target_version,
            "warehouse schema version",
        )
    )
    with target.cursor() as cursor:
        cursor.execute(f'SELECT COUNT(*) FROM "{schema}".publish_metadata')
        publish_metadata_rows = int(cursor.fetchone()[0])
    checks.append(
        ValidationCheck(
            "metadata.publish_metadata",
            publish_metadata_rows == 1,
            "1",
            str(publish_metadata_rows),
            "publish_metadata single row",
        )
    )
    return PublishValidationReport(tuple(checks))
