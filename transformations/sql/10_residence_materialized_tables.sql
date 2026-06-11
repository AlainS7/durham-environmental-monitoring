-- Materialized residence tables for low-cost per-residence dashboard queries.
-- Same join logic as residence_readings_* views, but physically stored with
-- clustering on residence_id so partition + cluster pruning works for apps.
DECLARE proc_date DATE DEFAULT @proc_date;

-- ============================================================================
-- TABLE 1: Hourly readings by residence (dashboard / API)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `${PROJECT}.${DATASET}.residence_hourly_by_residence`
PARTITION BY DATE(hour_ts)
CLUSTER BY residence_id, sensor_role, metric_name AS
SELECT
  CAST(NULL AS TIMESTAMP) AS hour_ts,
  CAST(NULL AS STRING) AS residence_id,
  CAST(NULL AS STRING) AS sensor_name,
  CAST(NULL AS STRING) AS sensor_role,
  CAST(NULL AS STRING) AS native_sensor_id,
  CAST(NULL AS STRING) AS metric_name,
  CAST(NULL AS FLOAT64) AS avg_value,
  CAST(NULL AS FLOAT64) AS min_value,
  CAST(NULL AS FLOAT64) AS max_value,
  CAST(NULL AS INT64) AS samples
FROM (SELECT 1) WHERE FALSE;

DELETE FROM `${PROJECT}.${DATASET}.residence_hourly_by_residence`
WHERE DATE(hour_ts) = proc_date;

INSERT INTO `${PROJECT}.${DATASET}.residence_hourly_by_residence`
  (hour_ts, residence_id, sensor_name, sensor_role, native_sensor_id, metric_name, avg_value, min_value, max_value, samples)
SELECT
  h.hour_ts,
  r.residence_id,
  r.sensor_name,
  r.sensor_role,
  h.native_sensor_id,
  h.metric_name,
  h.avg_value,
  h.min_value,
  h.max_value,
  h.samples
FROM `${PROJECT}.${DATASET}.sensor_readings_hourly` h
INNER JOIN `${PROJECT}.${DATASET}.residence_sensor_assignments` r
  ON h.native_sensor_id = r.native_sensor_id
  AND h.hour_ts >= r.start_ts
  AND (r.end_ts IS NULL OR h.hour_ts < r.end_ts)
WHERE DATE(h.hour_ts) = proc_date;

-- ============================================================================
-- TABLE 2: Daily readings by residence (dashboard / API)
-- ============================================================================
CREATE TABLE IF NOT EXISTS `${PROJECT}.${DATASET}.residence_daily_by_residence`
PARTITION BY DATE(day_ts)
CLUSTER BY residence_id, sensor_role, metric_name AS
SELECT
  CAST(NULL AS TIMESTAMP) AS day_ts,
  CAST(NULL AS STRING) AS residence_id,
  CAST(NULL AS STRING) AS sensor_name,
  CAST(NULL AS STRING) AS sensor_role,
  CAST(NULL AS STRING) AS native_sensor_id,
  CAST(NULL AS STRING) AS metric_name,
  CAST(NULL AS FLOAT64) AS avg_value,
  CAST(NULL AS FLOAT64) AS min_value,
  CAST(NULL AS FLOAT64) AS max_value,
  CAST(NULL AS INT64) AS samples
FROM (SELECT 1) WHERE FALSE;

DELETE FROM `${PROJECT}.${DATASET}.residence_daily_by_residence`
WHERE DATE(day_ts) = proc_date;

INSERT INTO `${PROJECT}.${DATASET}.residence_daily_by_residence`
  (day_ts, residence_id, sensor_name, sensor_role, native_sensor_id, metric_name, avg_value, min_value, max_value, samples)
SELECT
  d.day_ts,
  r.residence_id,
  r.sensor_name,
  r.sensor_role,
  d.native_sensor_id,
  d.metric_name,
  d.avg_value,
  d.min_value,
  d.max_value,
  d.samples
FROM `${PROJECT}.${DATASET}.sensor_readings_daily` d
INNER JOIN `${PROJECT}.${DATASET}.residence_sensor_assignments` r
  ON d.native_sensor_id = r.native_sensor_id
  AND d.day_ts >= r.start_ts
  AND (r.end_ts IS NULL OR d.day_ts < r.end_ts)
WHERE DATE(d.day_ts) = proc_date;
