-- Vehicle-month exposure and reliability.
SELECT
    v.vehicle_id,
    d.vehicle_type,
    v.calendar_month,
    v.deliveries_count,
    v.actual_distance_km,
    v.trip_hours,
    v.breakdown_count,
    v.breakdowns_per_10k_km,
    v.breakdowns_per_1000_trip_hours,
    v.downtime_hours,
    v.maintenance_events,
    v.maintenance_cost,
    v.late_delivery_rate
FROM delivery_pulse.vehicle_reliability_mart AS v
JOIN delivery_pulse.vehicles AS d USING (vehicle_id)
ORDER BY v.breakdown_count DESC, v.vehicle_id, v.calendar_month;
