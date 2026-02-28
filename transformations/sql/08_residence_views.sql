-- Residence-enriched views for Grafana
-- Joins sensor readings with residence assignments for person-centric analysis.
-- Automatically handles temporal sensor assignments (sensors moving between residences).

-- ============================================================================
-- VIEW 1: Hourly readings by residence (for Grafana dashboards)
-- ============================================================================
CREATE OR REPLACE VIEW `${PROJECT}.${DATASET}.residence_readings_hourly` AS
SELECT
  h.hour_ts,
  r.residence_id,
  r.sensor_name,
  r.sensor_role,    -- 'Indoor' or 'Outdoor'
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
  AND (r.end_ts IS NULL OR h.hour_ts < r.end_ts);

-- ============================================================================
-- VIEW 2: Daily readings by residence
-- ============================================================================
CREATE OR REPLACE VIEW `${PROJECT}.${DATASET}.residence_readings_daily` AS
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
  AND (r.end_ts IS NULL OR d.day_ts < r.end_ts);

-- ============================================================================
-- VIEW 3: Indoor vs Outdoor PM2.5 comparison per residence (Grafana favorite)
-- ============================================================================
CREATE OR REPLACE VIEW `${PROJECT}.${DATASET}.residence_indoor_outdoor_pm25` AS
WITH indoor AS (
  SELECT
    day_ts,
    residence_id,
    sensor_name,
    metric_name,
    avg_value
  FROM `${PROJECT}.${DATASET}.residence_readings_daily`
  WHERE sensor_role = 'Indoor'
    AND metric_name IN ('pm2_5', 'pm2_5_harmonized', 'pm2_5_mv_corrected')
),
outdoor AS (
  SELECT
    day_ts,
    residence_id,
    sensor_name,
    metric_name,
    avg_value
  FROM `${PROJECT}.${DATASET}.residence_readings_daily`
  WHERE sensor_role = 'Outdoor'
    AND metric_name IN ('pm2_5', 'pm2_5_harmonized', 'pm2_5_mv_corrected')
)
SELECT
  i.day_ts,
  i.residence_id,
  i.metric_name,
  i.sensor_name  AS indoor_sensor,
  i.avg_value    AS indoor_pm25,
  o.sensor_name  AS outdoor_sensor,
  o.avg_value    AS outdoor_pm25,
  SAFE_DIVIDE(i.avg_value, o.avg_value) AS indoor_outdoor_ratio
FROM indoor i
LEFT JOIN outdoor o
  ON i.residence_id = o.residence_id
  AND i.day_ts = o.day_ts
  AND i.metric_name = o.metric_name;

-- ============================================================================
-- VIEW 4: Active residence sensor pairs (quick reference)
-- ============================================================================
CREATE OR REPLACE VIEW `${PROJECT}.${DATASET}.residence_active_sensors` AS
SELECT
  residence_id,
  sensor_name,
  native_sensor_id,
  sensor_role,
  start_ts,
  end_ts,
  CASE WHEN end_ts IS NULL THEN 'Active' ELSE 'Inactive' END AS status
FROM `${PROJECT}.${DATASET}.residence_sensor_assignments`
ORDER BY residence_id, sensor_role, start_ts;
