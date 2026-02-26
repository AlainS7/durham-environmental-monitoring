-- Example Sensor Calibration Rules
-- Insert these into sensors.calibration_config based on your lab measurements
-- 
-- Formula: pm2_5_calibrated = (pm2_5_raw × slope) + intercept
-- 
-- INSTRUCTIONS:
-- 1. Replace the sensor IDs with your actual sensor IDs
-- 2. Replace slope/intercept with values from your calibration testing
-- 3. Set effective_date to when the calibration should start
-- 4. Leave end_date NULL for ongoing calibrations
-- 5. Run this in BigQuery console

-- DEFAULT calibration (no adjustment - must exist!)
INSERT INTO `durham-weather-466502.sensors.calibration_config`
(native_sensor_id, metric_name, slope, intercept, effective_date, end_date, description, created_at)
VALUES ('DEFAULT', 'pm2_5', 1.0, 0.0, DATE('2025-01-01'), NULL, 'No calibration (default)', CURRENT_TIMESTAMP())
ON CONFLICT DO NOTHING;

-- EXAMPLE: Sensor that came online Nov 17 and needs humidity bias correction
INSERT INTO `durham-weather-466502.sensors.calibration_config`
(native_sensor_id, metric_name, slope, intercept, effective_date, end_date, description, created_at)
VALUES 
  ('dummy_sensor_id', 'pm2_5', 0.95, 0.2, DATE('2025-11-17'), NULL, 'Humidity bias correction (95% of raw + 0.2 offset)', CURRENT_TIMESTAMP()),
  
  -- EXAMPLE: Another sensor with different calibration
  ('dummy_sensor_id', 'pm2_5', 0.88, 1.0, DATE('2025-11-17'), NULL, 'Significant drift correction (88% of raw + 1.0 offset)', CURRENT_TIMESTAMP()),
  
  -- EXAMPLE: Sensor with temporary calibration (end date specified)
  ('dummy_sensor_id', 'pm2_5', 0.92, 0.5, DATE('2025-11-17'), DATE('2025-12-31'), 'Temporary humidity correction (expired Dec 31)', CURRENT_TIMESTAMP()),
  
  -- EXAMPLE: Another metric (not just PM2.5)
  ('dummy_sensor_id', 'no2_ppb', 1.05, -0.1, DATE('2025-11-17'), NULL, 'NOx sensor gain adjustment', CURRENT_TIMESTAMP())
ON CONFLICT DO NOTHING;

-- ==============================================================================
-- TEMPLATE FOR YOUR SENSORS - Copy and modify:
-- ==============================================================================

-- Sensor 1
-- INSERT INTO `durham-weather-466502.sensors.calibration_config`
-- (native_sensor_id, metric_name, slope, intercept, effective_date, end_date, description, created_at)
-- VALUES 
--   ('YOUR_SENSOR_ID_HERE', 'pm2_5', 0.90, 0.5, DATE('2025-11-17'), NULL, 'Your description here', CURRENT_TIMESTAMP());

-- Sensor 2
-- INSERT INTO `durham-weather-466502.sensors.calibration_config`
-- (native_sensor_id, metric_name, slope, intercept, effective_date, end_date, description, created_at)
-- VALUES 
--   ('ANOTHER_SENSOR_ID', 'pm2_5', 0.95, 0.0, DATE('2025-11-17'), NULL, 'Your description here', CURRENT_TIMESTAMP());

-- ==============================================================================
-- HOW TO FIND YOUR SENSOR IDS:
-- ==============================================================================

-- List all sensors with their sensor IDs:
-- SELECT DISTINCT native_sensor_id
-- FROM sensors.tsi_raw_materialized
-- WHERE DATE(ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
-- ORDER BY native_sensor_id;

-- ==============================================================================
-- HOW TO DETERMINE SLOPE AND INTERCEPT:
-- ==============================================================================
-- 
-- If you have lab reference measurements:
-- 1. Collect raw sensor readings
-- 2. Get reference measurements from lab
-- 3. Perform linear regression: reference = slope × raw + intercept
-- 
-- Common values:
-- - No drift: slope=1.0, intercept=0.0
-- - 5% low reading: slope=1.05, intercept=0.0
-- - 5% low + bias: slope=0.95, intercept=1.0
-- - Humidity correction: slope varies by humidity, use average

-- ==============================================================================
-- VERIFICATION QUERY (run after inserting):
-- ==============================================================================

-- SELECT * FROM sensors.calibration_config
-- WHERE effective_date <= CURRENT_DATE()
--   AND (end_date IS NULL OR end_date >= CURRENT_DATE())
-- ORDER BY native_sensor_id, metric_name;

-- ==============================================================================
-- BACKFILL AFTER ADDING RULES:
-- ==============================================================================
--
-- source .venv/bin/activate
-- python scripts/run_transformations_batch.sh 2025-07-01 2026-01-29
--
-- This will re-process all historical data with the new calibration rules.
-- Takes approximately 40 minutes for 200 days of data.

