CREATE OR REPLACE TABLE delivery_financial_mart AS
WITH event_cost AS (
    SELECT
        delivery_id,
        CASE
            WHEN COUNT(*) FILTER (WHERE extra_cost IS NULL) > 0 THEN NULL
            ELSE SUM(extra_cost)
        END AS event_extra_cost
    FROM route_events
    GROUP BY delivery_id
),
components AS (
    SELECT
        d.delivery_id,
        d.order_id,
        o.customer_id,
        o.route_id,
        o.priority,
        d.delivery_status,
        'RUB'::VARCHAR AS currency_code,
        o.quoted_revenue,
        d.penalty_amount,
        o.quoted_revenue - d.penalty_amount AS net_revenue,
        d.fuel_cost,
        d.driver_cost,
        d.toll_cost,
        d.maintenance_allocated_cost,
        d.other_cost,
        coalesce(e.event_extra_cost, 0::DECIMAL(14, 2)) AS event_extra_cost,
        o.quoted_revenue IS NOT NULL
            AND d.penalty_amount IS NOT NULL
            AND d.fuel_cost IS NOT NULL
            AND d.driver_cost IS NOT NULL
            AND d.toll_cost IS NOT NULL
            AND d.maintenance_allocated_cost IS NOT NULL
            AND d.other_cost IS NOT NULL
            AND coalesce(e.event_extra_cost, 0::DECIMAL(14, 2)) IS NOT NULL
            AS financial_data_complete
    FROM deliveries AS d
    JOIN orders AS o USING (order_id)
    LEFT JOIN event_cost AS e USING (delivery_id)
),
costs AS (
    SELECT
        *,
        CASE
            WHEN financial_data_complete
            THEN fuel_cost
                + driver_cost
                + toll_cost
                + maintenance_allocated_cost
                + other_cost
                + event_extra_cost
        END AS total_delivery_cost
    FROM components
),
profits AS (
    SELECT
        *,
        CASE
            WHEN financial_data_complete
            THEN net_revenue - total_delivery_cost
        END AS delivery_profit
    FROM costs
)
SELECT
    *,
    delivery_profit / nullif(net_revenue, 0) AS margin_pct,
    CASE
        WHEN financial_data_complete THEN delivery_profit < 0
    END AS is_loss_making
FROM profits;
