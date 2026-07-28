-- Customer/route profitability; group margin is never AVG(margin_pct).
SELECT
    f.customer_id,
    f.route_id,
    COUNT(*) AS deliveries_count,
    SUM(f.net_revenue) AS total_net_revenue,
    SUM(f.total_delivery_cost) AS total_delivery_cost,
    SUM(f.delivery_profit) AS total_delivery_profit,
    SUM(f.delivery_profit) / NULLIF(SUM(f.net_revenue), 0) AS group_margin_pct,
    COUNT(*) FILTER (WHERE f.is_loss_making) AS loss_making_deliveries,
    -SUM(LEAST(f.delivery_profit, 0)) AS loss_amount
FROM delivery_pulse.delivery_financial_mart AS f
WHERE f.financial_data_complete
GROUP BY f.customer_id, f.route_id
ORDER BY loss_amount DESC, f.customer_id, f.route_id;
