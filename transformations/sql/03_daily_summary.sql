-- Daily summary aggregation with partition-aware DELETE+INSERT for 7-day window.
DECLARE proc_date DATE DEFAULT @proc_date;
DECLARE start_date DATE DEFAULT DATE_SUB(proc_date, INTERVAL 6 DAY);

-- Bootstrap table if missing
CREATE TABLE IF NOT EXISTS `${PROJECT}.${DATASET}.sensor_readings_daily`
PARTITION BY DATE(day_ts)
CLUSTER BY native_sensor_id, metric_name AS
SELECT
  TIMESTAMP_TRUNC(timestamp, DAY) AS day_ts,
  native_sensor_id,
  metric_name,
  AVG(value) AS avg_value,
  MIN(value) AS min_value,
  MAX(value) AS max_value,
  COUNT(*) AS samples
FROM `${PROJECT}.${DATASET}.sensor_readings_long`
WHERE 1=0
GROUP BY 1,2,3;

-- Refresh the 7-day window partitions
DELETE FROM `${PROJECT}.${DATASET}.sensor_readings_daily`
WHERE DATE(day_ts) BETWEEN start_date AND proc_date;

INSERT INTO `${PROJECT}.${DATASET}.sensor_readings_daily`
  (day_ts, native_sensor_id, metric_name, avg_value, min_value, max_value, samples)
SELECT
  TIMESTAMP_TRUNC(timestamp, DAY) AS day_ts,
  native_sensor_id,
  metric_name,
  AVG(value) AS avg_value,
  MIN(value) AS min_value,
  MAX(value) AS max_value,
  COUNT(*) AS samples
FROM `${PROJECT}.${DATASET}.sensor_readings_long`
WHERE DATE(timestamp) BETWEEN start_date AND proc_date
GROUP BY 1,2,3;
