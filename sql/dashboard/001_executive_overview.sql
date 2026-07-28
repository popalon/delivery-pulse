-- Executive overview: one row for headline cards.
SELECT
    COUNT(*) AS deliveries_count,
    COUNT(*) FILTER (WHERE p.delivery_status = 'delivered') AS delivered_count,
    COUNT(*) FILTER (WHERE p.delivery_status = 'failed') AS failed_count,
    AVG(CASE WHEN p.delivery_status = 'delivered'
             THEN p.is_on_time::INTEGER END) AS on_time_delivery_rate,
    SUM(f.net_revenue) AS total_net_revenue,
    SUM(f.delivery_profit) AS total_delivery_profit,
    SUM(f.delivery_profit) / NULLIF(SUM(f.net_revenue), 0) AS group_margin_pct,
    AVG(f.is_loss_making::INTEGER) AS loss_making_rate,
    AVG((p.delivery_status = 'failed')::INTEGER) AS failed_rate
FROM delivery_pulse.delivery_performance_mart AS p
JOIN delivery_pulse.delivery_financial_mart AS f USING (delivery_id);
