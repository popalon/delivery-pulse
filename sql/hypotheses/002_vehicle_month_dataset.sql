WITH observation AS (
    SELECT start_date
    FROM warehouse_metadata
),
vehicle_month AS (
    SELECT
        r.*,
        v.vehicle_type,
        year(r.calendar_month) - v.manufacture_year AS vehicle_age_years,
        lag(r.scheduled_maintenance_events, 1, 0) OVER (
            PARTITION BY r.vehicle_id
            ORDER BY r.calendar_month
        ) AS lag_scheduled_maintenance_events
    FROM vehicle_reliability_mart AS r
    JOIN vehicles AS v USING (vehicle_id)
)
SELECT
    vehicle_id,
    calendar_month,
    breakdown_count,
    actual_distance_km,
    trip_hours,
    scheduled_maintenance_events,
    repair_events,
    vehicle_type,
    vehicle_age_years,
    lag_scheduled_maintenance_events,
    CASE
        WHEN lag_scheduled_maintenance_events > 0 THEN 1
        ELSE 0
    END AS had_scheduled_maintenance_previous_month
FROM vehicle_month
CROSS JOIN observation
ORDER BY vehicle_id, calendar_month;
