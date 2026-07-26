CREATE UNIQUE INDEX customers_name_uq ON customers (customer_name);
CREATE UNIQUE INDEX routes_code_uq ON routes (route_code);
CREATE UNIQUE INDEX drivers_code_uq ON drivers (driver_code);
CREATE UNIQUE INDEX vehicles_code_uq ON vehicles (vehicle_code);
CREATE UNIQUE INDEX deliveries_order_uq ON deliveries (order_id);

CREATE INDEX orders_customer_idx ON orders (customer_id);
CREATE INDEX orders_route_idx ON orders (route_id);
CREATE INDEX deliveries_driver_idx ON deliveries (driver_id);
CREATE INDEX deliveries_vehicle_idx ON deliveries (vehicle_id);
CREATE INDEX route_events_delivery_idx ON route_events (delivery_id);
CREATE INDEX maintenance_vehicle_idx ON maintenance (vehicle_id);
