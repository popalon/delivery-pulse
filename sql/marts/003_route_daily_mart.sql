CREATE OR REPLACE TABLE route_daily_mart AS
WITH base AS (
    SELECT
        p.*,
        f.net_revenue,
        f.total_delivery_cost,
        f.delivery_profit,
        f.financial_data_complete,
        f.is_loss_making,
        CAST(
            p.planned_departure_at AT TIME ZONE 'UTC'
                AT TIME ZONE 'Europe/Moscow'
            AS DATE
        ) AS calendar_date
    FROM delivery_performance_mart AS p
    JOIN delivery_financial_mart AS f USING (delivery_id)
)
SELECT
    route_id,
    calendar_date,
    COUNT(*)::BIGINT AS deliveries_count,
    count_if(delivery_status = 'delivered')::BIGINT AS delivered_count,
    count_if(delivery_status = 'failed')::BIGINT AS failed_count,
    count_if(delivery_status = 'cancelled')::BIGINT AS cancelled_count,
    count_if(is_on_time)::BIGINT AS on_time_count,
    count_if(delivery_status = 'delivered' AND NOT is_on_time)::BIGINT AS late_count,
    count_if(is_on_time)::DOUBLE
        / nullif(count_if(delivery_status = 'delivered'), 0)
        AS on_time_delivery_rate,
    median(delay_minutes) FILTER (
        WHERE delivery_status = 'delivered' AND delay_minutes > 0
    ) AS median_delay_minutes,
    quantile_cont(delay_minutes, 0.9) FILTER (
        WHERE delivery_status = 'delivered' AND delay_minutes > 0
    ) AS p90_delay_minutes,
    SUM(net_revenue) FILTER (WHERE financial_data_complete) AS total_net_revenue,
    SUM(total_delivery_cost) FILTER (
        WHERE financial_data_complete
    ) AS total_delivery_cost,
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
    ) AS loss_amount,
    count_if(breakdown_event_count > 0)::BIGINT AS breakdown_deliveries,
    count_if(loading_delay_minutes > 0)::BIGINT AS loading_delay_deliveries
FROM base
GROUP BY route_id, calendar_date;
