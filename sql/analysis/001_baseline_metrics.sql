WITH customer_totals AS (
    SELECT SUM(orders_count) AS orders_count
    FROM customer_monthly_mart
),
delivery_totals AS (
    SELECT
        COUNT(*) AS deliveries_count,
        count_if(delivery_status = 'delivered') AS delivered_count,
        count_if(delivery_status = 'failed') AS failed_count,
        count_if(delivery_status = 'cancelled') AS cancelled_count,
        count_if(is_on_time)::DOUBLE
            / nullif(count_if(delivery_status = 'delivered'), 0)
            AS on_time_delivery_rate,
        median(delay_minutes) FILTER (
            WHERE delivery_status = 'delivered' AND delay_minutes > 0
        ) AS median_delay_minutes,
        quantile_cont(delay_minutes, 0.9) FILTER (
            WHERE delivery_status = 'delivered' AND delay_minutes > 0
        ) AS p90_delay_minutes,
        count_if(
            capacity_utilization > 1 AND capacity_utilization <= 1.05
        ) AS operational_overload_count
    FROM delivery_performance_mart
),
financial_totals AS (
    SELECT
        SUM(net_revenue) FILTER (
            WHERE financial_data_complete
        ) AS total_net_revenue,
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
        count_if(is_loss_making)::DOUBLE
            / nullif(count_if(financial_data_complete), 0)
            AS loss_making_delivery_rate,
        SUM(greatest(-delivery_profit, 0)) FILTER (
            WHERE financial_data_complete
        ) AS loss_amount,
        AVG(financial_data_complete::INTEGER) AS data_completeness_rate
    FROM delivery_financial_mart
),
reliability_totals AS (
    SELECT SUM(breakdown_count) AS breakdown_count
    FROM vehicle_reliability_mart
)
SELECT *
FROM customer_totals
CROSS JOIN delivery_totals
CROSS JOIN financial_totals
CROSS JOIN reliability_totals;
