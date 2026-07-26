CREATE OR REPLACE TABLE vehicle_reliability_mart AS
WITH delivery_base AS (
    SELECT
        vehicle_id,
        date_trunc(
            'month',
            planned_departure_at AT TIME ZONE 'UTC'
                AT TIME ZONE 'Europe/Moscow'
        )::DATE AS calendar_month,
        COUNT(*)::BIGINT AS deliveries_count,
        count_if(delivery_status = 'delivered')::BIGINT AS delivered_count,
        SUM(distance_actual_km) FILTER (
            WHERE delivery_status = 'delivered' AND distance_actual_km > 0
        ) AS actual_distance_km,
        SUM(delivery_cycle_hours) FILTER (
            WHERE delivery_status = 'delivered' AND delivery_cycle_hours > 0
        ) AS trip_hours,
        SUM(breakdown_event_count)::BIGINT AS breakdown_count,
        count_if(breakdown_event_count > 0)::BIGINT AS breakdown_deliveries,
        AVG(capacity_utilization) AS average_capacity_utilization,
        count_if(delivery_status = 'delivered' AND NOT is_on_time)::DOUBLE
            / nullif(count_if(delivery_status = 'delivered'), 0)
            AS late_delivery_rate
    FROM delivery_performance_mart
    GROUP BY vehicle_id, calendar_month
),
maintenance_base AS (
    SELECT
        vehicle_id,
        date_trunc(
            'month',
            started_at AT TIME ZONE 'UTC' AT TIME ZONE 'Europe/Moscow'
        )::DATE AS calendar_month,
        COUNT(*)::BIGINT AS maintenance_events,
        count_if(maintenance_type = 'scheduled')::BIGINT
            AS scheduled_maintenance_events,
        count_if(maintenance_type = 'repair')::BIGINT AS repair_events,
        SUM(cost_amount) AS maintenance_cost,
        SUM(downtime_hours) AS downtime_hours
    FROM maintenance
    GROUP BY vehicle_id, calendar_month
),
combined AS (
    SELECT
        coalesce(d.vehicle_id, m.vehicle_id) AS vehicle_id,
        coalesce(d.calendar_month, m.calendar_month) AS calendar_month,
        coalesce(d.deliveries_count, 0) AS deliveries_count,
        coalesce(d.delivered_count, 0) AS delivered_count,
        d.actual_distance_km,
        d.trip_hours,
        coalesce(d.breakdown_count, 0) AS breakdown_count,
        coalesce(d.breakdown_deliveries, 0) AS breakdown_deliveries,
        coalesce(m.maintenance_events, 0) AS maintenance_events,
        coalesce(m.scheduled_maintenance_events, 0)
            AS scheduled_maintenance_events,
        coalesce(m.repair_events, 0) AS repair_events,
        m.maintenance_cost,
        m.downtime_hours,
        d.average_capacity_utilization,
        d.late_delivery_rate
    FROM delivery_base AS d
    FULL OUTER JOIN maintenance_base AS m
        ON d.vehicle_id = m.vehicle_id
        AND d.calendar_month = m.calendar_month
)
SELECT
    *,
    breakdown_count / nullif(actual_distance_km, 0) * 10000
        AS breakdowns_per_10k_km,
    breakdown_count / nullif(trip_hours, 0) * 1000
        AS breakdowns_per_1000_trip_hours
FROM combined;
