-- Example Sensor Calibration Rules
-- Insert these into sensors.calibration_config based on your lab measurements
-- 
-- Formula: pm2_5_calibrated = (pm2_5_raw × slope) + intercept
-- 
-- NOTE:
-- - This file intentionally uses example values.
-- - Replace the project ID and all dummy sensor IDs before production use.
-- 
-- INSTRUCTIONS:
-- 1. Replace the sensor IDs with your actual sensor IDs
-- 2. Replace slope/intercept with values from your calibration testing
-- 3. Set effective_date to when the calibration should start
-- 4. Leave end_date NULL for ongoing calibrations
-- 5. Run this in BigQuery console

-- DEFAULT calibration (no adjustment - must exist!)
MERGE `durham-weather-466502.sensors.calibration_config` T
USING (
  SELECT
    'DEFAULT' AS native_sensor_id,
    'pm2_5' AS metric_name,
    1.0 AS slope,
    0.0 AS intercept,
    DATE('2025-01-01') AS effective_date,
    CAST(NULL AS DATE) AS end_date,
    'No calibration (default)' AS description
) S
ON T.native_sensor_id = S.native_sensor_id
  AND T.metric_name = S.metric_name
  AND T.slope = S.slope
  AND T.intercept = S.intercept
  AND T.effective_date = S.effective_date
  AND ((T.end_date IS NULL AND S.end_date IS NULL) OR T.end_date = S.end_date)
  AND T.description = S.description
WHEN NOT MATCHED THEN
  INSERT (native_sensor_id, metric_name, slope, intercept, effective_date, end_date, description, created_at)
  VALUES (S.native_sensor_id, S.metric_name, S.slope, S.intercept, S.effective_date, S.end_date, S.description, CURRENT_TIMESTAMP());

-- EXAMPLE: Sensor that came online Nov 17 and needs humidity bias correction
MERGE `durham-weather-466502.sensors.calibration_config` T
USING (
  SELECT * FROM UNNEST([
    STRUCT(
      'dummy_sensor_id' AS native_sensor_id,
      'pm2_5' AS metric_name,
      0.95 AS slope,
      0.2 AS intercept,
      DATE('2025-11-17') AS effective_date,
      CAST(NULL AS DATE) AS end_date,
      'Humidity bias correction (95% of raw + 0.2 offset)' AS description
    ),
    -- EXAMPLE: Another sensor with different calibration
    STRUCT(
      'dummy_sensor_id' AS native_sensor_id,
      'pm2_5' AS metric_name,
      0.88 AS slope,
      1.0 AS intercept,
      DATE('2025-11-17') AS effective_date,
      CAST(NULL AS DATE) AS end_date,
      'Significant drift correction (88% of raw + 1.0 offset)' AS description
    ),
    -- EXAMPLE: Sensor with temporary calibration (end date specified)
    STRUCT(
      'dummy_sensor_id' AS native_sensor_id,
      'pm2_5' AS metric_name,
      0.92 AS slope,
      0.5 AS intercept,
      DATE('2025-11-17') AS effective_date,
      DATE('2025-12-31') AS end_date,
      'Temporary humidity correction (expired Dec 31)' AS description
    ),
    -- EXAMPLE: Another metric (not just PM2.5)
    STRUCT(
      'dummy_sensor_id' AS native_sensor_id,
      'no2_ppb' AS metric_name,
      1.05 AS slope,
      -0.1 AS intercept,
      DATE('2025-11-17') AS effective_date,
      CAST(NULL AS DATE) AS end_date,
      'NOx sensor gain adjustment' AS description
    )
  ])
) S
ON T.native_sensor_id = S.native_sensor_id
  AND T.metric_name = S.metric_name
  AND T.slope = S.slope
  AND T.intercept = S.intercept
  AND T.effective_date = S.effective_date
  AND ((T.end_date IS NULL AND S.end_date IS NULL) OR T.end_date = S.end_date)
  AND T.description = S.description
WHEN NOT MATCHED THEN
  INSERT (native_sensor_id, metric_name, slope, intercept, effective_date, end_date, description, created_at)
  VALUES (S.native_sensor_id, S.metric_name, S.slope, S.intercept, S.effective_date, S.end_date, S.description, CURRENT_TIMESTAMP());

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
