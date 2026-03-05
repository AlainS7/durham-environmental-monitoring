-- Variables: ${PROJECT} (GCP project ID), substituted at runtime by envsubst or shell
-- Create specialized views for Weather Underground (WU) and TSI sensors
-- These views separate the data by sensor type for easier analysis in Looker Studio

-- =============================================================================
-- VIEW 1: Weather Underground (WU) Daily Summary with Enrichment
-- =============================================================================
-- Purpose: Daily aggregations of WU weather metrics with canonical locations and status
-- Use for: Weather monitoring, humidity, solar, UV, wind analysis
-- Metrics: humidity, solar_radiation, uv_high, wind_direction_avg

CREATE OR REPLACE VIEW `${PROJECT}.sensors.wu_daily_enriched` AS
SELECT
  d.day_ts,
  d.native_sensor_id,
  COALESCE(m.sensor_id, d.native_sensor_id) AS sensor_id,
  d.metric_name,
  d.avg_value,
  d.min_value,
  d.max_value,
  d.samples,
  lc.latitude,
  lc.longitude,
  lc.geog,
  lc.status,
  lc.effective_date,
  'WU' AS sensor_type
FROM `${PROJECT}.sensors.sensor_readings_daily` d
LEFT JOIN `${PROJECT}.sensors.sensor_id_map` m
  ON d.native_sensor_id = m.native_sensor_id
  AND (m.effective_start_date IS NULL OR DATE(d.day_ts) >= m.effective_start_date)
  AND (m.effective_end_date IS NULL OR DATE(d.day_ts) <= m.effective_end_date)
LEFT JOIN `${PROJECT}.sensors.sensor_location_current` lc
  ON d.native_sensor_id = lc.native_sensor_id
WHERE d.metric_name IN ('humidity', 'solar_radiation', 'uv_high', 'wind_direction_avg');

-- =============================================================================
-- VIEW 2: TSI Air Quality Daily Summary with Enrichment
-- =============================================================================
-- Purpose: Daily aggregations of TSI air quality metrics with canonical locations and status
-- Use for: Air quality monitoring, PM2.5, temperature, humidity from TSI sensors
-- Metrics: pm2_5, temperature, humidity (when data becomes available)
-- Note: Currently TSI data has NULL values - this view is ready for when data is fixed

CREATE OR REPLACE VIEW `${PROJECT}.sensors.tsi_daily_enriched` AS
SELECT
  d.day_ts,
  d.native_sensor_id,
  COALESCE(m.sensor_id, d.native_sensor_id) AS sensor_id,
  d.metric_name,
  d.avg_value,
  d.min_value,
  d.max_value,
  d.samples,
  lc.latitude,
  lc.longitude,
  lc.geog,
  lc.status,
  lc.effective_date,
  'TSI' AS sensor_type
FROM `${PROJECT}.sensors.sensor_readings_daily` d
LEFT JOIN `${PROJECT}.sensors.sensor_id_map` m
  ON d.native_sensor_id = m.native_sensor_id
  AND (m.effective_start_date IS NULL OR DATE(d.day_ts) >= m.effective_start_date)
  AND (m.effective_end_date IS NULL OR DATE(d.day_ts) <= m.effective_end_date)
LEFT JOIN `${PROJECT}.sensors.sensor_location_current` lc
  ON d.native_sensor_id = lc.native_sensor_id
WHERE d.metric_name IN ('pm2_5', 'temperature', 'humidity');

-- =============================================================================
-- VIEW 3: Combined WU + TSI Daily Summary (Keep existing view for compatibility)
-- =============================================================================
-- Purpose: Union of all sensor types for comprehensive analysis
-- Use for: Overall monitoring dashboard, comparing all metrics

CREATE OR REPLACE VIEW `${PROJECT}.sensors.sensor_readings_daily_enriched` AS
SELECT
  d.day_ts,
  d.native_sensor_id,
  COALESCE(m.sensor_id, d.native_sensor_id) AS sensor_id,
  d.metric_name,
  d.metric_name AS metric,  -- Alias for Looker compatibility
  d.avg_value AS value,      -- Alias for Looker compatibility
  d.avg_value,
  d.min_value,
  d.max_value,
  d.samples,
  lc.latitude,
  lc.longitude,
  lc.geog,
  lc.status,
  lc.effective_date
FROM `${PROJECT}.sensors.sensor_readings_daily` d
LEFT JOIN `${PROJECT}.sensors.sensor_id_map` m
  ON d.native_sensor_id = m.native_sensor_id
  AND (m.effective_start_date IS NULL OR DATE(d.day_ts) >= m.effective_start_date)
  AND (m.effective_end_date IS NULL OR DATE(d.day_ts) <= m.effective_end_date)
LEFT JOIN `${PROJECT}.sensors.sensor_location_current` lc
  ON d.native_sensor_id = lc.native_sensor_id;

-- =============================================================================
-- Verification Queries (run separately)
-- =============================================================================

-- Check WU view
-- SELECT 'WU View' as view_name, COUNT(*) as row_count, COUNT(DISTINCT native_sensor_id) as sensors, COUNT(DISTINCT metric_name) as metrics
-- FROM `${PROJECT}.sensors.wu_daily_enriched`
-- UNION ALL
-- Check TSI view (will be 0 rows until TSI data is fixed)
-- SELECT 'TSI View', COUNT(*), COUNT(DISTINCT native_sensor_id), COUNT(DISTINCT metric_name)
-- FROM `${PROJECT}.sensors.tsi_daily_enriched`
-- UNION ALL
-- Check combined view
-- SELECT 'Combined View', COUNT(*), COUNT(DISTINCT native_sensor_id), COUNT(DISTINCT metric_name)
-- FROM `${PROJECT}.sensors.sensor_readings_daily_enriched`;
