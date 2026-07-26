"""Warehouse grain, count, and formula validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from delivery_pulse.contracts import PRIMARY_KEYS, TABLE_COLUMNS
from delivery_pulse.warehouse.models import ValidationCheck, ValidationReport

MARTS = (
    "delivery_performance_mart",
    "delivery_financial_mart",
    "route_daily_mart",
    "customer_monthly_mart",
    "vehicle_reliability_mart",
)


def _scalar(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    row = connection.execute(query).fetchone()
    return None if row is None else row[0]


def _check(check_id: str, passed: bool, success: str, failure: str) -> ValidationCheck:
    return ValidationCheck(check_id, passed, success if passed else failure)


def validate_connection(
    connection: duckdb.DuckDBPyConnection,
    database: Path,
) -> ValidationReport:
    """Validate required objects, grains, counts, and SQL formulas."""
    checks: list[ValidationCheck] = []
    objects = {
        str(row[0])
        for row in connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main'"
        ).fetchall()
    }
    expected = set(TABLE_COLUMNS) | set(MARTS) | {"warehouse_metadata"}
    missing = sorted(expected - objects)
    checks.append(
        _check(
            "objects.required",
            not missing,
            "All source tables, marts, and warehouse_metadata exist.",
            "Missing warehouse objects: " + ", ".join(missing),
        )
    )
    if missing:
        return ValidationReport(database.resolve(), tuple(checks))

    metadata_rows = int(_scalar(connection, "SELECT COUNT(*) FROM warehouse_metadata"))
    checks.append(
        _check(
            "metadata.single_row",
            metadata_rows == 1,
            "warehouse_metadata contains one row.",
            f"warehouse_metadata contains {metadata_rows} rows.",
        )
    )
    metadata_json = str(
        _scalar(connection, "SELECT row_counts::VARCHAR FROM warehouse_metadata")
    )
    metadata_counts = json.loads(metadata_json)
    for table_name in TABLE_COLUMNS:
        actual = int(_scalar(connection, f'SELECT COUNT(*) FROM "{table_name}"'))
        expected_count = metadata_counts.get(table_name)
        checks.append(
            _check(
                f"source_count.{table_name}",
                actual == expected_count,
                f"{table_name}: {actual} rows match metadata.",
                f"{table_name}: loaded={actual}, metadata={expected_count!r}.",
            )
        )
        primary_key = PRIMARY_KEYS[table_name]
        null_keys = int(
            _scalar(
                connection,
                f'SELECT COUNT(*) FROM "{table_name}" WHERE "{primary_key}" IS NULL',
            )
        )
        checks.append(
            _check(
                f"source_key.{table_name}",
                null_keys == 0,
                f"{table_name}: primary key has no NULL values.",
                f"{table_name}: {null_keys} NULL primary keys.",
            )
        )

    deliveries_count = int(_scalar(connection, "SELECT COUNT(*) FROM deliveries"))
    for mart in ("delivery_performance_mart", "delivery_financial_mart"):
        row_count, distinct_count, null_count = connection.execute(
            f"""
            SELECT
                COUNT(*),
                COUNT(DISTINCT delivery_id),
                count_if(delivery_id IS NULL)
            FROM "{mart}"
            """
        ).fetchone()
        valid = (
            int(row_count) == deliveries_count
            and int(distinct_count) == deliveries_count
            and int(null_count) == 0
        )
        checks.append(
            _check(
                f"grain.{mart}",
                valid,
                f"{mart}: one row per delivery, no multiplication.",
                f"{mart}: rows={row_count}, distinct={distinct_count}, "
                f"source deliveries={deliveries_count}, null keys={null_count}.",
            )
        )

    grain_checks = (
        ("route_daily_mart", "route_id, calendar_date"),
        ("customer_monthly_mart", "customer_id, calendar_month"),
        ("vehicle_reliability_mart", "vehicle_id, calendar_month"),
    )
    for mart, keys in grain_checks:
        duplicates = int(
            _scalar(
                connection,
                f"""
                SELECT COUNT(*) FROM (
                    SELECT {keys}, COUNT(*) AS rows_at_grain
                    FROM "{mart}"
                    GROUP BY {keys}
                    HAVING COUNT(*) > 1
                )
                """,
            )
        )
        null_keys = int(
            _scalar(
                connection,
                f'SELECT COUNT(*) FROM "{mart}" '
                f"WHERE {keys.split(', ')[0]} IS NULL "
                f"OR {keys.split(', ')[1]} IS NULL",
            )
        )
        checks.append(
            _check(
                f"grain.{mart}",
                duplicates == 0 and null_keys == 0,
                f"{mart}: documented grain is unique and non-null.",
                f"{mart}: duplicate groups={duplicates}, null keys={null_keys}.",
            )
        )

    status_mismatches = int(
        _scalar(
            connection,
            """
            SELECT COUNT(*) FROM (
                SELECT delivery_status, COUNT(*) AS count_value
                FROM deliveries
                GROUP BY delivery_status
                EXCEPT
                SELECT delivery_status, COUNT(*) AS count_value
                FROM delivery_performance_mart
                GROUP BY delivery_status
            )
            """,
        )
    )
    checks.append(
        _check(
            "reconciliation.status_counts",
            status_mismatches == 0,
            "Delivery status counts match the source.",
            "Delivery status counts differ between source and performance mart.",
        )
    )

    event_mismatches = int(
        _scalar(
            connection,
            """
            WITH expected AS (
                SELECT
                    d.delivery_id,
                    COUNT(e.event_id) AS event_count,
                    coalesce(SUM(e.delay_minutes), 0) AS event_delay_minutes
                FROM deliveries AS d
                LEFT JOIN route_events AS e USING (delivery_id)
                GROUP BY d.delivery_id
            )
            SELECT COUNT(*)
            FROM expected AS e
            JOIN delivery_performance_mart AS p USING (delivery_id)
            WHERE e.event_count <> p.event_count
                OR e.event_delay_minutes <> p.event_delay_minutes
            """,
        )
    )
    checks.append(
        _check(
            "reconciliation.route_events",
            event_mismatches == 0,
            "Route events are aggregated once per delivery.",
            f"{event_mismatches} deliveries have mismatched event aggregates.",
        )
    )

    financial_mismatches = int(
        _scalar(
            connection,
            """
            SELECT COUNT(*)
            FROM delivery_financial_mart
            WHERE financial_data_complete
                AND (
                    total_delivery_cost
                        <> fuel_cost + driver_cost + toll_cost
                            + maintenance_allocated_cost + other_cost
                            + event_extra_cost
                    OR net_revenue <> quoted_revenue - penalty_amount
                    OR delivery_profit <> net_revenue - total_delivery_cost
                    OR (
                        net_revenue <> 0
                        AND abs(margin_pct - delivery_profit / net_revenue) > 1e-12
                    )
                )
            """,
        )
    )
    checks.append(
        _check(
            "formulas.financial",
            financial_mismatches == 0,
            "Financial formulas preserve penalties, event costs, and NULL rules.",
            f"{financial_mismatches} rows violate financial formulas.",
        )
    )

    sla_mismatches = int(
        _scalar(
            connection,
            """
            SELECT COUNT(*)
            FROM delivery_performance_mart
            WHERE delivery_status = 'delivered'
                AND (
                    delay_minutes <> greatest(
                        0,
                        date_diff(
                            'minute',
                            promised_delivery_at,
                            actual_delivery_at
                        )
                    )
                    OR is_on_time <> (
                        actual_delivery_at <= promised_delivery_at
                    )
                )
            """,
        )
    )
    checks.append(
        _check(
            "formulas.sla",
            sla_mismatches == 0,
            "SLA delay and on-time formulas match documented definitions.",
            f"{sla_mismatches} rows violate SLA formulas.",
        )
    )

    margin_mismatches = 0
    for mart in ("route_daily_mart", "customer_monthly_mart"):
        margin_mismatches += int(
            _scalar(
                connection,
                f"""
                SELECT COUNT(*)
                FROM "{mart}"
                WHERE total_net_revenue <> 0
                    AND abs(
                        group_margin_pct
                        - total_delivery_profit / total_net_revenue
                    ) > 1e-12
                """,
            )
        )
    checks.append(
        _check(
            "formulas.group_margin",
            margin_mismatches == 0,
            "Group margin is the ratio of aggregate profit and revenue.",
            f"{margin_mismatches} aggregate rows have an invalid group margin.",
        )
    )

    event_cost_difference = _scalar(
        connection,
        """
        SELECT
            abs(
                (SELECT coalesce(SUM(event_extra_cost), 0)
                 FROM delivery_financial_mart)
                - (SELECT coalesce(SUM(extra_cost), 0) FROM route_events)
            )
        """,
    )
    checks.append(
        _check(
            "reconciliation.event_cost",
            float(event_cost_difference) < 0.01,
            "Event costs are not duplicated.",
            f"Event cost reconciliation difference is {event_cost_difference}.",
        )
    )

    maintenance_count = int(_scalar(connection, "SELECT COUNT(*) FROM maintenance"))
    mart_maintenance_count = int(
        _scalar(
            connection,
            "SELECT coalesce(SUM(maintenance_events), 0) FROM vehicle_reliability_mart",
        )
    )
    checks.append(
        _check(
            "reconciliation.maintenance",
            maintenance_count == mart_maintenance_count,
            "Maintenance events are aggregated once into vehicle-month grain.",
            f"Source maintenance={maintenance_count}, mart={mart_maintenance_count}.",
        )
    )
    return ValidationReport(database.resolve(), tuple(checks))
