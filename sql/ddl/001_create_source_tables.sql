CREATE TABLE customers (
    customer_id BIGINT NOT NULL,
    customer_name VARCHAR NOT NULL,
    customer_segment VARCHAR NOT NULL,
    industry VARCHAR NOT NULL,
    contract_start_date DATE NOT NULL,
    contract_end_date DATE,
    default_sla_hours SMALLINT NOT NULL,
    payment_terms_days SMALLINT NOT NULL,
    is_active BOOLEAN NOT NULL,
    PRIMARY KEY (customer_id)
);

CREATE TABLE routes (
    route_id BIGINT NOT NULL,
    route_code VARCHAR NOT NULL,
    origin_region VARCHAR NOT NULL,
    destination_region VARCHAR NOT NULL,
    standard_distance_km DECIMAL(10, 2) NOT NULL,
    standard_transit_hours DECIMAL(8, 2) NOT NULL,
    route_class VARCHAR NOT NULL,
    is_active BOOLEAN NOT NULL,
    PRIMARY KEY (route_id)
);

CREATE TABLE drivers (
    driver_id BIGINT NOT NULL,
    driver_code VARCHAR NOT NULL,
    hire_date DATE NOT NULL,
    experience_years DECIMAL(4, 1) NOT NULL,
    license_class VARCHAR NOT NULL,
    home_region VARCHAR NOT NULL,
    employment_status VARCHAR NOT NULL,
    PRIMARY KEY (driver_id)
);

CREATE TABLE vehicles (
    vehicle_id BIGINT NOT NULL,
    vehicle_code VARCHAR NOT NULL,
    vehicle_type VARCHAR NOT NULL,
    capacity_kg DECIMAL(10, 2) NOT NULL,
    manufacture_year SMALLINT NOT NULL,
    fuel_type VARCHAR NOT NULL,
    fuel_consumption_l_100km DECIMAL(6, 2) NOT NULL,
    odometer_at_observation_start_km DECIMAL(12, 2) NOT NULL,
    home_region VARCHAR NOT NULL,
    service_status VARCHAR NOT NULL,
    PRIMARY KEY (vehicle_id)
);

CREATE TABLE orders (
    order_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    route_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    requested_pickup_at TIMESTAMP NOT NULL,
    promised_delivery_at TIMESTAMP NOT NULL,
    cargo_type VARCHAR NOT NULL,
    cargo_weight_kg DECIMAL(10, 2) NOT NULL,
    distance_planned_km DECIMAL(10, 2) NOT NULL,
    quoted_revenue DECIMAL(14, 2) NOT NULL,
    priority VARCHAR NOT NULL,
    order_status VARCHAR NOT NULL,
    PRIMARY KEY (order_id)
);

CREATE TABLE deliveries (
    delivery_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    driver_id BIGINT NOT NULL,
    vehicle_id BIGINT NOT NULL,
    planned_departure_at TIMESTAMP NOT NULL,
    actual_departure_at TIMESTAMP,
    actual_delivery_at TIMESTAMP,
    distance_actual_km DECIMAL(10, 2),
    delivery_status VARCHAR NOT NULL,
    fuel_cost DECIMAL(14, 2),
    driver_cost DECIMAL(14, 2),
    toll_cost DECIMAL(14, 2),
    maintenance_allocated_cost DECIMAL(14, 2),
    other_cost DECIMAL(14, 2),
    penalty_amount DECIMAL(14, 2),
    PRIMARY KEY (delivery_id)
);

CREATE TABLE route_events (
    event_id BIGINT NOT NULL,
    delivery_id BIGINT NOT NULL,
    event_at TIMESTAMP NOT NULL,
    event_end_at TIMESTAMP,
    event_type VARCHAR NOT NULL,
    severity VARCHAR NOT NULL,
    delay_minutes INTEGER NOT NULL,
    extra_cost DECIMAL(14, 2) NOT NULL,
    region VARCHAR NOT NULL,
    notes_code VARCHAR,
    PRIMARY KEY (event_id)
);

CREATE TABLE maintenance (
    maintenance_id BIGINT NOT NULL,
    vehicle_id BIGINT NOT NULL,
    maintenance_type VARCHAR NOT NULL,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    odometer_km DECIMAL(12, 2) NOT NULL,
    cost_amount DECIMAL(14, 2) NOT NULL,
    downtime_hours DECIMAL(10, 2),
    issue_category VARCHAR,
    maintenance_status VARCHAR NOT NULL,
    PRIMARY KEY (maintenance_id)
);

CREATE TABLE warehouse_metadata (
    project_version VARCHAR NOT NULL,
    generator_version VARCHAR NOT NULL,
    seed BIGINT NOT NULL,
    profile VARCHAR NOT NULL,
    start_date DATE NOT NULL,
    months INTEGER NOT NULL,
    loaded_at TIMESTAMP NOT NULL,
    source_directory VARCHAR NOT NULL,
    row_counts JSON NOT NULL,
    warehouse_schema_version VARCHAR NOT NULL
);
