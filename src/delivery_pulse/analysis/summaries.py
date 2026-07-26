"""Summary tables calculated from canonical warehouse marts."""

from __future__ import annotations

import duckdb
import pandas as pd

from delivery_pulse.analysis.loader import query_frame


def monthly_summary(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Aggregate canonical daily route metrics to business calendar months."""
    return query_frame(
        connection,
        """
        SELECT
            date_trunc('month', calendar_date)::DATE AS calendar_month,
            SUM(deliveries_count)::BIGINT AS deliveries_count,
            SUM(delivered_count)::BIGINT AS delivered_count,
            SUM(failed_count)::BIGINT AS failed_count,
            SUM(cancelled_count)::BIGINT AS cancelled_count,
            SUM(on_time_count)::DOUBLE / nullif(SUM(delivered_count), 0)
                AS on_time_delivery_rate,
            SUM(failed_count)::DOUBLE / nullif(SUM(deliveries_count), 0)
                AS failed_rate,
            SUM(total_net_revenue) AS total_net_revenue,
            SUM(total_delivery_cost) AS total_delivery_cost,
            SUM(total_delivery_profit) AS total_delivery_profit,
            SUM(total_delivery_profit) / nullif(SUM(total_net_revenue), 0)
                AS group_margin_pct,
            SUM(loss_making_deliveries)::BIGINT AS loss_making_deliveries,
            SUM(loss_amount) AS loss_amount,
            SUM(breakdown_deliveries)::BIGINT AS breakdown_deliveries,
            SUM(loading_delay_deliveries)::BIGINT AS loading_delay_deliveries
        FROM route_daily_mart
        GROUP BY calendar_month
        ORDER BY calendar_month
        """,
    )


def daily_summary(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Aggregate route-day rows to one row per business calendar day."""
    return query_frame(
        connection,
        """
        SELECT
            calendar_date,
            SUM(deliveries_count)::BIGINT AS deliveries_count,
            SUM(delivered_count)::BIGINT AS delivered_count,
            SUM(failed_count)::BIGINT AS failed_count,
            SUM(on_time_count)::DOUBLE / nullif(SUM(delivered_count), 0)
                AS on_time_delivery_rate,
            SUM(total_delivery_profit) AS total_delivery_profit,
            SUM(total_delivery_profit) / nullif(SUM(total_net_revenue), 0)
                AS group_margin_pct,
            SUM(loss_making_deliveries)::BIGINT AS loss_making_deliveries,
            SUM(breakdown_deliveries)::BIGINT AS breakdown_deliveries,
            SUM(loading_delay_deliveries)::BIGINT AS loading_delay_deliveries
        FROM route_daily_mart
        GROUP BY calendar_date
        ORDER BY calendar_date
        """,
    )


def profitability_distribution(
    connection: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    """Load canonical delivery-level financial measures for distributions."""
    return query_frame(
        connection,
        """
        SELECT
            delivery_id,
            customer_id,
            route_id,
            priority,
            delivery_status,
            net_revenue,
            total_delivery_cost,
            delivery_profit,
            margin_pct,
            is_loss_making,
            financial_data_complete
        FROM delivery_financial_mart
        ORDER BY delivery_id
        """,
    )


def priority_summary(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Compare standard and express at delivery grain without significance tests."""
    return query_frame(
        connection,
        """
        SELECT
            p.priority,
            COUNT(*)::BIGINT AS deliveries_count,
            count_if(p.delivery_status = 'delivered')::BIGINT AS delivered_count,
            count_if(p.is_on_time)::DOUBLE
                / nullif(count_if(p.delivery_status = 'delivered'), 0)
                AS on_time_delivery_rate,
            median(p.delay_minutes) FILTER (
                WHERE p.delivery_status = 'delivered' AND p.delay_minutes > 0
            ) AS median_delay_minutes,
            quantile_cont(p.delay_minutes, 0.9) FILTER (
                WHERE p.delivery_status = 'delivered' AND p.delay_minutes > 0
            ) AS p90_delay_minutes,
            SUM(f.net_revenue) FILTER (
                WHERE f.financial_data_complete
            ) AS total_net_revenue,
            SUM(f.total_delivery_cost) FILTER (
                WHERE f.financial_data_complete
            ) AS total_delivery_cost,
            SUM(f.delivery_profit) FILTER (
                WHERE f.financial_data_complete
            ) AS total_delivery_profit,
            SUM(f.delivery_profit) FILTER (WHERE f.financial_data_complete)
                / nullif(
                    SUM(f.net_revenue) FILTER (WHERE f.financial_data_complete),
                    0
                ) AS group_margin_pct,
            count_if(f.is_loss_making)::DOUBLE
                / nullif(count_if(f.financial_data_complete), 0)
                AS loss_making_delivery_rate,
            count_if(p.breakdown_event_count > 0)::DOUBLE
                / nullif(COUNT(*), 0) AS breakdown_delivery_rate,
            count_if(p.loading_delay_minutes > 0)::DOUBLE
                / nullif(COUNT(*), 0) AS loading_delay_delivery_rate
        FROM delivery_performance_mart AS p
        JOIN delivery_financial_mart AS f USING (delivery_id)
        GROUP BY p.priority
        ORDER BY p.priority
        """,
    )
