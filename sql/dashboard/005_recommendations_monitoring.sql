-- R1–R6 KPI/guardrail monitoring from published marts only.
SELECT
    'R1_express' AS recommendation_id,
    COUNT(*) FILTER (WHERE priority = 'express') AS sample_size,
    AVG(CASE WHEN priority = 'express' AND delivery_status = 'delivered'
             THEN is_on_time::INTEGER END) AS primary_kpi,
    AVG(CASE WHEN priority = 'standard' AND delivery_status = 'delivered'
             THEN is_on_time::INTEGER END) AS guardrail
FROM delivery_pulse.delivery_performance_mart
UNION ALL
SELECT
    'R2_breakdown',
    COUNT(*) FILTER (WHERE p.breakdown_event_count > 0),
    AVG(CASE WHEN p.breakdown_event_count > 0
             THEN f.is_loss_making::INTEGER END),
    AVG(CASE WHEN p.breakdown_event_count = 0
             THEN f.is_loss_making::INTEGER END)
FROM delivery_pulse.delivery_performance_mart AS p
JOIN delivery_pulse.delivery_financial_mart AS f USING (delivery_id)
UNION ALL
SELECT
    'R3_clients',
    COUNT(DISTINCT customer_id),
    SUM(delivery_profit) / NULLIF(SUM(net_revenue), 0),
    AVG(is_loss_making::INTEGER)
FROM delivery_pulse.delivery_financial_mart
WHERE financial_data_complete
UNION ALL
SELECT
    'R4_loading',
    COUNT(*) FILTER (WHERE loading_delay_minutes > 0),
    AVG(loading_delay_minutes),
    AVG(CASE WHEN delivery_status = 'delivered'
             THEN is_on_time::INTEGER END)
FROM delivery_pulse.delivery_performance_mart
UNION ALL
SELECT
    'R5_maintenance',
    SUM(maintenance_events),
    AVG(breakdowns_per_10k_km),
    AVG(late_delivery_rate)
FROM delivery_pulse.vehicle_reliability_mart
UNION ALL
SELECT
    'R6_overload',
    COUNT(*) FILTER (WHERE capacity_utilization > 1),
    AVG(CASE WHEN capacity_utilization > 1
             THEN capacity_utilization END),
    MAX(capacity_utilization)
FROM delivery_pulse.delivery_performance_mart;
