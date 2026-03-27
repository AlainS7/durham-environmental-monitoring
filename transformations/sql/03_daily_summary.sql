-- Daily summary aggregation with partition-aware DELETE+INSERT.
-- Uses @proc_date; safe to re-run for the same date.
DECLARE proc_date DATE DEFAULT @proc_date;

-- Bootstrap table if missing
CREATE TABLE IF NOT EXISTS `${PROJECT}.${DATASET}.sensor_readings_daily`
PARTITION BY DATE(day_ts)
CLUSTER BY native_sensor_id, metric_name AS
WITH grouped AS (
  SELECT
    TIMESTAMP_TRUNC(timestamp, DAY) AS day_ts,
    DATE(TIMESTAMP_TRUNC(timestamp, DAY)) AS day_date,
    native_sensor_id,
    source,
    metric_name,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    COUNT(*) AS samples
  FROM `${PROJECT}.${DATASET}.sensor_readings_long`
  WHERE 1=0
  GROUP BY 1,2,3,4,5
)
SELECT
  day_ts,
  day_date,
  native_sensor_id,
  source,
  metric_name,
  avg_value,
  min_value,
  max_value,
  samples,
  FARM_FINGERPRINT(
    CONCAT(
      CAST(day_ts AS STRING),
      '|', native_sensor_id,
      '|', metric_name,
      '|', source
    )
  ) AS row_id
FROM grouped;

-- Refresh only the partition for proc_date (not a rolling window)
DELETE FROM `${PROJECT}.${DATASET}.sensor_readings_daily`
WHERE DATE(day_ts) = proc_date;

INSERT INTO `${PROJECT}.${DATASET}.sensor_readings_daily`
  (day_ts, day_date, native_sensor_id, source, metric_name, avg_value, min_value, max_value, samples, row_id)
WITH grouped AS (
  SELECT
    TIMESTAMP_TRUNC(timestamp, DAY) AS day_ts,
    DATE(TIMESTAMP_TRUNC(timestamp, DAY)) AS day_date,
    native_sensor_id,
    source,
    metric_name,
    AVG(value) AS avg_value,
    MIN(value) AS min_value,
    MAX(value) AS max_value,
    COUNT(*) AS samples
  FROM `${PROJECT}.${DATASET}.sensor_readings_long`
  WHERE DATE(timestamp) = proc_date
  GROUP BY 1,2,3,4,5
)
SELECT
  day_ts,
  day_date,
  native_sensor_id,
  source,
  metric_name,
  avg_value,
  min_value,
  max_value,
  samples,
  FARM_FINGERPRINT(
    CONCAT(
      CAST(day_ts AS STRING),
      '|', native_sensor_id,
      '|', metric_name,
      '|', source
    )
  ) AS row_id
FROM grouped;
