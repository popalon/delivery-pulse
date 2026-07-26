WITH event_flags AS (
    SELECT
        delivery_id,
        count_if(event_type = 'route_deviation') > 0 AS has_route_deviation
    FROM route_events
    GROUP BY delivery_id
)
SELECT
    p.delivery_id,
    p.customer_id,
    p.route_id,
    p.vehicle_id,
    p.priority,
    p.cargo_type,
    p.delivery_status,
    p.is_on_time,
    CASE
        WHEN p.delivery_status = 'delivered' THEN NOT p.is_on_time
        ELSE NULL
    END AS is_late,
    p.distance_planned_km,
    p.loading_delay_minutes > 0 AS has_loading_delay,
    p.loading_delay_minutes,
    p.traffic_delay_minutes > 0 AS has_traffic,
    p.weather_delay_minutes > 0 AS has_weather,
    p.breakdown_event_count > 0 AS has_breakdown,
    coalesce(e.has_route_deviation, false) AS has_route_deviation,
    p.capacity_utilization > 1
        AND p.capacity_utilization <= 1.05 AS operational_overload,
    f.financial_data_complete,
    f.is_loss_making,
    f.delivery_profit,
    f.net_revenue,
    c.customer_segment,
    r.route_class,
    v.vehicle_type,
    v.manufacture_year,
    date_trunc(
        'month',
        (p.planned_departure_at AT TIME ZONE 'UTC')
            AT TIME ZONE 'Europe/Moscow'
    )::DATE AS calendar_month
FROM delivery_performance_mart AS p
JOIN delivery_financial_mart AS f USING (delivery_id)
JOIN customers AS c ON c.customer_id = p.customer_id
JOIN routes AS r ON r.route_id = p.route_id
JOIN vehicles AS v ON v.vehicle_id = p.vehicle_id
LEFT JOIN event_flags AS e USING (delivery_id)
ORDER BY p.delivery_id;
