"""Route, customer, event, profitability, and fleet segment tables."""

from __future__ import annotations

import duckdb
import pandas as pd

from delivery_pulse.analysis.loader import query_frame

EVENT_COMPARISONS = (
    ("any_event", "event_count > 0"),
    ("loading_delay", "loading_delay_minutes > 0"),
    ("breakdown", "breakdown_event_count > 0"),
    ("traffic", "traffic_delay_minutes > 0"),
    ("weather", "weather_delay_minutes > 0"),
    ("route_deviation", "has_route_deviation"),
)


def route_summary(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return one descriptive row per route with sample size beside rates."""
    return query_frame(
        connection,
        """
        WITH performance AS (
            SELECT
                route_id,
                COUNT(*)::BIGINT AS deliveries_count,
                count_if(delivery_status = 'delivered')::BIGINT AS delivered_count,
                count_if(is_on_time)::DOUBLE
                    / nullif(count_if(delivery_status = 'delivered'), 0)
                    AS on_time_delivery_rate,
                median(delay_minutes) FILTER (
                    WHERE delivery_status = 'delivered' AND delay_minutes > 0
                ) AS median_delay_minutes,
                quantile_cont(delay_minutes, 0.9) FILTER (
                    WHERE delivery_status = 'delivered' AND delay_minutes > 0
                ) AS p90_delay_minutes,
                count_if(breakdown_event_count > 0)::BIGINT
                    AS breakdown_deliveries,
                count_if(loading_delay_minutes > 0)::BIGINT
                    AS loading_delay_deliveries
            FROM delivery_performance_mart
            GROUP BY route_id
        ),
        financial AS (
            SELECT
                route_id,
                SUM(delivery_profit) FILTER (
                    WHERE financial_data_complete
                ) AS total_delivery_profit,
                SUM(delivery_profit) FILTER (WHERE financial_data_complete)
                    / nullif(
                        SUM(net_revenue) FILTER (WHERE financial_data_complete),
                        0
                    ) AS group_margin_pct,
                count_if(is_loss_making)::BIGINT AS loss_making_deliveries,
                SUM(greatest(-delivery_profit, 0)) FILTER (
                    WHERE financial_data_complete
                ) AS loss_amount
            FROM delivery_financial_mart
            GROUP BY route_id
        )
        SELECT
            r.route_id,
            r.route_code,
            r.origin_region,
            r.destination_region,
            p.* EXCLUDE (route_id),
            f.* EXCLUDE (route_id)
        FROM routes AS r
        JOIN performance AS p USING (route_id)
        JOIN financial AS f USING (route_id)
        ORDER BY r.route_id
        """,
    )


def customer_summary(
    connection: duckdb.DuckDBPyConnection,
    min_group_size: int,
) -> pd.DataFrame:
    """Return one customer row with explicit volume reliability bands."""
    return query_frame(
        connection,
        """
        WITH monthly AS (
            SELECT
                customer_id,
                SUM(orders_count)::BIGINT AS orders_count,
                SUM(deliveries_count)::BIGINT AS deliveries_count,
                SUM(delivered_count)::BIGINT AS delivered_count,
                SUM(failed_count)::BIGINT AS failed_count,
                SUM(cancelled_count)::BIGINT AS cancelled_count,
                SUM(failed_count)::DOUBLE / nullif(SUM(deliveries_count), 0)
                    AS failed_rate,
                SUM(total_net_revenue) AS total_net_revenue,
                SUM(total_delivery_profit) AS total_delivery_profit,
                SUM(total_delivery_profit) / nullif(SUM(total_net_revenue), 0)
                    AS group_margin_pct,
                SUM(loss_making_deliveries)::BIGINT AS loss_making_deliveries,
                SUM(loss_amount) AS loss_amount,
                SUM(orders_count * express_order_share)::DOUBLE
                    / nullif(SUM(orders_count), 0) AS express_share,
                SUM(loading_delay_delivery_count)::BIGINT
                    AS loading_delay_count,
                SUM(breakdown_delivery_count)::BIGINT AS breakdown_count
            FROM customer_monthly_mart
            GROUP BY customer_id
        ),
        performance AS (
            SELECT
                customer_id,
                count_if(is_on_time)::DOUBLE
                    / nullif(count_if(delivery_status = 'delivered'), 0)
                    AS on_time_delivery_rate
            FROM delivery_performance_mart
            GROUP BY customer_id
        )
        SELECT
            c.customer_id,
            c.customer_name,
            c.customer_segment,
            m.* EXCLUDE (customer_id),
            p.on_time_delivery_rate,
            CASE
                WHEN m.deliveries_count < ? THEN 'small_sample'
                WHEN m.deliveries_count < ? * 3 THEN 'medium_sample'
                ELSE 'large_sample'
            END AS volume_band
        FROM customers AS c
        JOIN monthly AS m USING (customer_id)
        JOIN performance AS p USING (customer_id)
        ORDER BY c.customer_id
        """,
        [min_group_size, min_group_size],
    )


def event_comparisons(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Return descriptive with/without comparisons for documented event flags."""
    union_parts: list[str] = []
    for event_name, predicate in EVENT_COMPARISONS:
        comparisons = (("with", predicate), ("without", f"NOT ({predicate})"))
        for state, condition in comparisons:
            union_parts.append(
                f"""
                SELECT
                    '{event_name}' AS event_type,
                    '{state}' AS comparison_group,
                    COUNT(*)::BIGINT AS deliveries_count,
                    count_if(delivery_status = 'delivered')::BIGINT
                        AS delivered_count,
                    count_if(delivery_status = 'delivered' AND NOT is_on_time)
                        ::DOUBLE
                        / nullif(count_if(delivery_status = 'delivered'), 0)
                        AS late_delivery_rate,
                    median(delay_minutes) FILTER (
                        WHERE delivery_status = 'delivered' AND delay_minutes > 0
                    ) AS median_delay_minutes,
                    quantile_cont(delay_minutes, 0.9) FILTER (
                        WHERE delivery_status = 'delivered' AND delay_minutes > 0
                    ) AS p90_delay_minutes,
                    SUM(event_extra_cost) AS event_extra_cost,
                    AVG(delivery_profit) FILTER (
                        WHERE financial_data_complete
                    ) AS average_delivery_profit,
                    AVG((delivery_profit IS NULL)::INTEGER)::DOUBLE
                        AS profit_missing_rate,
                    AVG((delay_minutes IS NULL)::INTEGER)::DOUBLE
                        AS delay_missing_rate
                FROM base
                WHERE {condition}
                """
            )
    query = (
        """
        WITH route_deviation AS (
            SELECT
                delivery_id,
                count_if(event_type = 'route_deviation') > 0
                    AS has_route_deviation
            FROM route_events
            GROUP BY delivery_id
        ),
        base AS (
            SELECT
                p.*,
                f.event_extra_cost,
                f.delivery_profit,
                f.financial_data_complete,
                coalesce(r.has_route_deviation, false) AS has_route_deviation
            FROM delivery_performance_mart AS p
            JOIN delivery_financial_mart AS f USING (delivery_id)
            LEFT JOIN route_deviation AS r USING (delivery_id)
        )
        """
        + "\nUNION ALL\n".join(union_parts)
        + "\nORDER BY event_type, comparison_group"
    )
    frame = query_frame(connection, query)
    with_rows = frame.loc[frame["comparison_group"] == "with"].set_index("event_type")
    without_rows = frame.loc[frame["comparison_group"] == "without"].set_index(
        "event_type"
    )
    frame["late_rate_absolute_difference"] = frame["event_type"].map(
        with_rows["late_delivery_rate"] - without_rows["late_delivery_rate"]
    )
    frame["late_rate_relative_ratio"] = frame["event_type"].map(
        with_rows["late_delivery_rate"]
        / without_rows["late_delivery_rate"].replace(0, pd.NA)
    )
    return frame.sort_values(["event_type", "comparison_group"], ignore_index=True)


def event_type_costs(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Summarize point-detail source events without recalculating delivery KPI."""
    return query_frame(
        connection,
        """
        SELECT
            event_type,
            COUNT(*)::BIGINT AS event_count,
            COUNT(DISTINCT delivery_id)::BIGINT AS deliveries_count,
            SUM(extra_cost) AS extra_cost,
            median(delay_minutes) AS median_event_delay_minutes,
            quantile_cont(delay_minutes, 0.9) AS p90_event_delay_minutes
        FROM route_events
        GROUP BY event_type
        ORDER BY event_type
        """,
    )


def profitability_segments(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Compare loss rates across priority, segment, breakdown, and overload."""
    return query_frame(
        connection,
        """
        WITH base AS (
            SELECT
                p.delivery_id,
                p.priority,
                c.customer_segment,
                p.breakdown_event_count > 0 AS has_breakdown,
                p.capacity_utilization > 1 AND p.capacity_utilization <= 1.05
                    AS operational_overload,
                f.net_revenue,
                f.delivery_profit,
                f.is_loss_making,
                f.financial_data_complete
            FROM delivery_performance_mart AS p
            JOIN delivery_financial_mart AS f USING (delivery_id)
            JOIN customers AS c ON c.customer_id = p.customer_id
        ),
        segments AS (
            SELECT
                'priority' AS dimension,
                priority AS segment,
                delivery_id,
                net_revenue,
                delivery_profit,
                is_loss_making,
                financial_data_complete
            FROM base
            UNION ALL
            SELECT
                'customer_segment',
                customer_segment,
                delivery_id,
                net_revenue,
                delivery_profit,
                is_loss_making,
                financial_data_complete
            FROM base
            UNION ALL
            SELECT
                'breakdown',
                CASE WHEN has_breakdown THEN 'with' ELSE 'without' END,
                delivery_id,
                net_revenue,
                delivery_profit,
                is_loss_making,
                financial_data_complete
            FROM base
            UNION ALL
            SELECT
                'operational_overload',
                CASE WHEN operational_overload THEN 'with' ELSE 'without' END,
                delivery_id,
                net_revenue,
                delivery_profit,
                is_loss_making,
                financial_data_complete
            FROM base
        )
        SELECT
            dimension,
            segment,
            COUNT(*)::BIGINT AS deliveries_count,
            count_if(financial_data_complete)::BIGINT AS complete_financial_count,
            count_if(is_loss_making)::BIGINT AS loss_making_deliveries,
            count_if(is_loss_making)::DOUBLE
                / nullif(count_if(financial_data_complete), 0)
                AS loss_making_delivery_rate,
            SUM(greatest(-delivery_profit, 0)) FILTER (
                WHERE financial_data_complete
            ) AS loss_amount,
            SUM(delivery_profit) FILTER (WHERE financial_data_complete)
                / nullif(
                    SUM(net_revenue) FILTER (WHERE financial_data_complete),
                    0
                ) AS group_margin_pct
        FROM segments
        GROUP BY dimension, segment
        ORDER BY dimension, segment
        """,
    )


def vehicle_summary(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Aggregate vehicle-month exposure and reliability to vehicle grain."""
    return query_frame(
        connection,
        """
        WITH metadata AS (
            SELECT year(start_date) AS observation_year
            FROM warehouse_metadata
        )
        SELECT
            v.vehicle_id,
            v.vehicle_code,
            v.vehicle_type,
            m.observation_year - v.manufacture_year AS vehicle_age_years,
            SUM(r.deliveries_count)::BIGINT AS deliveries_count,
            SUM(r.delivered_count)::BIGINT AS delivered_count,
            SUM(r.actual_distance_km) AS actual_distance_km,
            SUM(r.trip_hours) AS trip_hours,
            SUM(r.breakdown_count)::BIGINT AS breakdown_count,
            SUM(r.breakdown_deliveries)::BIGINT AS breakdown_deliveries,
            SUM(r.breakdown_count) / nullif(SUM(r.actual_distance_km), 0) * 10000
                AS breakdowns_per_10k_km,
            SUM(r.breakdown_count) / nullif(SUM(r.trip_hours), 0) * 1000
                AS breakdowns_per_1000_trip_hours,
            SUM(r.maintenance_events)::BIGINT AS maintenance_events,
            SUM(r.scheduled_maintenance_events)::BIGINT
                AS scheduled_maintenance_events,
            SUM(r.repair_events)::BIGINT AS repair_events,
            SUM(r.maintenance_cost) AS maintenance_cost,
            SUM(r.downtime_hours) AS downtime_hours,
            SUM(r.average_capacity_utilization * r.deliveries_count)
                / nullif(SUM(r.deliveries_count), 0)
                AS average_capacity_utilization,
            SUM(r.late_delivery_rate * r.delivered_count)
                / nullif(SUM(r.delivered_count), 0)
                AS late_delivery_rate
        FROM vehicle_reliability_mart AS r
        JOIN vehicles AS v USING (vehicle_id)
        CROSS JOIN metadata AS m
        GROUP BY
            v.vehicle_id,
            v.vehicle_code,
            v.vehicle_type,
            vehicle_age_years
        ORDER BY v.vehicle_id
        """,
    )


def vehicle_type_summary(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Aggregate exposure-normalized reliability by vehicle type."""
    vehicles = vehicle_summary(connection)
    rows: list[dict[str, object]] = []
    for vehicle_type, group in vehicles.groupby("vehicle_type", sort=True):
        distance = group["actual_distance_km"].sum(min_count=1)
        hours = group["trip_hours"].sum(min_count=1)
        breakdowns = int(group["breakdown_count"].sum())
        rows.append(
            {
                "vehicle_type": vehicle_type,
                "vehicles_count": len(group),
                "deliveries_count": int(group["deliveries_count"].sum()),
                "actual_distance_km": distance,
                "trip_hours": hours,
                "breakdown_count": breakdowns,
                "breakdowns_per_10k_km": (
                    breakdowns / distance * 10000
                    if pd.notna(distance) and distance > 0
                    else None
                ),
                "breakdowns_per_1000_trip_hours": (
                    breakdowns / hours * 1000 if pd.notna(hours) and hours > 0 else None
                ),
                "maintenance_events": int(group["maintenance_events"].sum()),
                "maintenance_cost": group["maintenance_cost"].sum(min_count=1),
                "downtime_hours": group["downtime_hours"].sum(min_count=1),
            }
        )
    return pd.DataFrame(rows).sort_values("vehicle_type", ignore_index=True)


def vehicle_age_summary(vehicles: pd.DataFrame) -> pd.DataFrame:
    """Aggregate reliability into explicit vehicle-age bands."""
    frame = vehicles.copy()
    frame["age_band"] = pd.cut(
        frame["vehicle_age_years"],
        bins=[-1, 3, 7, float("inf")],
        labels=["0–3 years", "4–7 years", "8+ years"],
    )
    rows: list[dict[str, object]] = []
    for age_band, group in frame.groupby("age_band", observed=True, sort=True):
        distance = group["actual_distance_km"].sum(min_count=1)
        hours = group["trip_hours"].sum(min_count=1)
        breakdowns = int(group["breakdown_count"].sum())
        rows.append(
            {
                "age_band": str(age_band),
                "vehicles_count": len(group),
                "deliveries_count": int(group["deliveries_count"].sum()),
                "actual_distance_km": distance,
                "trip_hours": hours,
                "breakdown_count": breakdowns,
                "breakdowns_per_10k_km": (
                    breakdowns / distance * 10_000
                    if pd.notna(distance) and distance > 0
                    else None
                ),
                "breakdowns_per_1000_trip_hours": (
                    breakdowns / hours * 1_000
                    if pd.notna(hours) and hours > 0
                    else None
                ),
            }
        )
    return pd.DataFrame(rows)


def rank_table(
    frame: pd.DataFrame,
    measure: str,
    *,
    top_n: int,
    ascending: bool,
    min_group_size: int = 0,
    sample_column: str = "deliveries_count",
) -> pd.DataFrame:
    """Return a deterministic top-N ranking after an explicit sample filter."""
    eligible = frame.loc[frame[sample_column] >= min_group_size].copy()
    return (
        eligible.sort_values(
            [measure, sample_column, frame.columns[0]],
            ascending=[ascending, False, True],
            na_position="last",
        )
        .head(top_n)
        .reset_index(drop=True)
    )
