-- Table 1: Tracks the physical sensor device itself. The "Who".
CREATE TABLE sensors_master (
    sensor_pk SERIAL PRIMARY KEY,
    native_sensor_id VARCHAR(255) NOT NULL,
    sensor_type VARCHAR(50) NOT NULL, -- e.g., 'TSI', 'WU'
    friendly_name VARCHAR(255),
    -- A sensor can only have one native_sensor_id per type at any given time
    CONSTRAINT uq_native_sensor_id_type UNIQUE (native_sensor_id, sensor_type)
);

-- Table 2: Tracks each specific "tour of duty" for a sensor. The "What, Where, and When".
CREATE TABLE deployments (
    deployment_pk SERIAL PRIMARY KEY,
    sensor_fk INTEGER NOT NULL REFERENCES sensors_master(sensor_pk) ON DELETE CASCADE,
    location VARCHAR(255) NOT NULL, -- e.g., 'The Lab', 'City Hall'
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    status VARCHAR(50) NOT NULL, -- 'testing', 'active', 'inactive', 'decommissioned'
    start_date DATE NOT NULL,
    end_date DATE, -- NULL if the deployment is currently active
    CONSTRAINT uq_one_active_deployment_per_sensor UNIQUE (sensor_fk, end_date)
);

-- Table 3: Stores all time-series data, linked to a specific deployment.
CREATE TABLE sensor_readings (
    "timestamp" TIMESTAMPTZ NOT NULL,
    deployment_fk INTEGER NOT NULL REFERENCES deployments(deployment_pk) ON DELETE CASCADE,
    metric_name VARCHAR(100) NOT NULL,
    value DOUBLE PRECISION,
    PRIMARY KEY ("timestamp", deployment_fk, metric_name)
);

-- Index to speed up lookups for recent readings for a specific deployment
CREATE INDEX idx_sensor_readings_deployment_timestamp ON sensor_readings(deployment_fk, "timestamp" DESC);