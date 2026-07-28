-- Route/priority reliability with sample sizes and event-family indicators.
SELECT
    p.route_id,
    p.priority,
    COUNT(*) AS deliveries_count,
    COUNT(*) FILTER (WHERE p.delivery_status = 'delivered') AS delivered_count,
    AVG(CASE WHEN p.delivery_status = 'delivered'
             THEN p.is_on_time::INTEGER END) AS on_time_delivery_rate,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY p.delay_minutes)
        FILTER (WHERE p.delay_minutes > 0) AS median_late_minutes,
    percentile_cont(0.9) WITHIN GROUP (ORDER BY p.delay_minutes)
        FILTER (WHERE p.delay_minutes > 0) AS p90_late_minutes,
    COUNT(*) FILTER (WHERE p.loading_delay_minutes > 0) AS loading_delay_count,
    COUNT(*) FILTER (WHERE p.traffic_delay_minutes > 0) AS traffic_count,
    COUNT(*) FILTER (WHERE p.weather_delay_minutes > 0) AS weather_count,
    COUNT(*) FILTER (WHERE p.breakdown_event_count > 0) AS breakdown_count
FROM delivery_pulse.delivery_performance_mart AS p
GROUP BY p.route_id, p.priority
ORDER BY deliveries_count DESC, p.route_id, p.priority;
