CREATE OR REPLACE TABLE customer_monthly_mart AS
WITH base AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.priority,
        o.requested_pickup_at,
        d.delivery_id,
        p.delivery_status,
        p.is_on_time,
        p.delay_minutes,
        p.breakdown_event_count,
        p.loading_delay_minutes,
        f.net_revenue,
        f.total_delivery_cost,
        f.delivery_profit,
        f.financial_data_complete,
        f.is_loss_making,
        date_trunc(
            'month',
            o.requested_pickup_at AT TIME ZONE 'UTC'
                AT TIME ZONE 'Europe/Moscow'
        )::DATE AS calendar_month
    FROM orders AS o
    LEFT JOIN deliveries AS d USING (order_id)
    LEFT JOIN delivery_performance_mart AS p USING (delivery_id)
    LEFT JOIN delivery_financial_mart AS f USING (delivery_id)
)
SELECT
    customer_id,
    calendar_month,
    COUNT(*)::BIGINT AS orders_count,
    count(delivery_id)::BIGINT AS deliveries_count,
    count_if(delivery_status = 'delivered')::BIGINT AS delivered_count,
    count_if(delivery_status = 'failed')::BIGINT AS failed_count,
    count_if(delivery_status = 'cancelled')::BIGINT AS cancelled_count,
    count_if(is_on_time)::DOUBLE
        / nullif(count_if(delivery_status = 'delivered'), 0)
        AS on_time_delivery_rate,
    median(delay_minutes) FILTER (
        WHERE delivery_status = 'delivered' AND delay_minutes > 0
    ) AS median_delay_minutes,
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
    count_if(priority = 'express')::DOUBLE / nullif(COUNT(*), 0)
        AS express_order_share,
    count_if(breakdown_event_count > 0)::BIGINT AS breakdown_delivery_count,
    count_if(loading_delay_minutes > 0)::BIGINT AS loading_delay_delivery_count
FROM base
GROUP BY customer_id, calendar_month;
