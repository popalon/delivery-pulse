CREATE OR REPLACE TABLE delivery_performance_mart AS
WITH event_agg AS (
    SELECT
        delivery_id,
        COUNT(*)::BIGINT AS event_count,
        SUM(delay_minutes)::BIGINT AS event_delay_minutes,
        SUM(CASE WHEN event_type = 'loading_delay' THEN delay_minutes ELSE 0 END)
            ::BIGINT AS loading_delay_minutes,
        SUM(CASE WHEN event_type = 'unloading_delay' THEN delay_minutes ELSE 0 END)
            ::BIGINT AS unloading_delay_minutes,
        SUM(CASE WHEN event_type = 'traffic' THEN delay_minutes ELSE 0 END)
            ::BIGINT AS traffic_delay_minutes,
        SUM(CASE WHEN event_type = 'weather' THEN delay_minutes ELSE 0 END)
            ::BIGINT AS weather_delay_minutes,
        SUM(CASE WHEN event_type = 'breakdown' THEN 1 ELSE 0 END)
            ::BIGINT AS breakdown_event_count
    FROM route_events
    GROUP BY delivery_id
)
SELECT
    d.delivery_id,
    d.order_id,
    o.customer_id,
    o.route_id,
    d.driver_id,
    d.vehicle_id,
    o.priority,
    o.cargo_type,
    d.delivery_status,
    o.created_at,
    o.requested_pickup_at,
    o.promised_delivery_at,
    d.planned_departure_at,
    d.actual_departure_at,
    d.actual_delivery_at,
    CASE
        WHEN d.actual_departure_at IS NOT NULL
        THEN date_diff('minute', d.planned_departure_at, d.actual_departure_at)
    END AS departure_delay_minutes,
    CASE
        WHEN d.delivery_status = 'delivered'
        THEN date_diff('minute', d.actual_departure_at, d.actual_delivery_at) / 60.0
    END AS delivery_cycle_hours,
    CASE
        WHEN d.delivery_status = 'delivered'
        THEN greatest(
            0,
            date_diff('minute', o.promised_delivery_at, d.actual_delivery_at)
        )
    END AS delay_minutes,
    CASE
        WHEN d.delivery_status = 'delivered'
        THEN d.actual_delivery_at <= o.promised_delivery_at
    END AS is_on_time,
    coalesce(e.event_count, 0) AS event_count,
    coalesce(e.event_delay_minutes, 0) AS event_delay_minutes,
    coalesce(e.loading_delay_minutes, 0) AS loading_delay_minutes,
    coalesce(e.unloading_delay_minutes, 0) AS unloading_delay_minutes,
    coalesce(e.traffic_delay_minutes, 0) AS traffic_delay_minutes,
    coalesce(e.weather_delay_minutes, 0) AS weather_delay_minutes,
    coalesce(e.breakdown_event_count, 0) AS breakdown_event_count,
    o.distance_planned_km,
    d.distance_actual_km,
    CASE
        WHEN d.distance_actual_km IS NOT NULL
        THEN (d.distance_actual_km - o.distance_planned_km)
            / nullif(o.distance_planned_km, 0)
    END AS distance_deviation_pct,
    o.cargo_weight_kg,
    v.capacity_kg,
    o.cargo_weight_kg / nullif(v.capacity_kg, 0) AS capacity_utilization
FROM deliveries AS d
JOIN orders AS o USING (order_id)
JOIN vehicles AS v USING (vehicle_id)
LEFT JOIN event_agg AS e USING (delivery_id);
