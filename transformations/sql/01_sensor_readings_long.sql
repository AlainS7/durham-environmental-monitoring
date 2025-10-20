-- Build long (tall) unified fact table with partition-aware DELETE+INSERT.
-- Uses @proc_date; safe to re-run for the same date.

DECLARE proc_date DATE DEFAULT @proc_date;

-- Bootstrap table if missing (defines partitioning/clustering via empty CTAS)
CREATE TABLE IF NOT EXISTS `${PROJECT}.${DATASET}.sensor_readings_long`
PARTITION BY DATE(timestamp)
CLUSTER BY native_sensor_id, metric_name AS
WITH
  wu_src AS (
    SELECT
      ts AS timestamp,
      native_sensor_id,
  -- latitude, longitude removed
      -- Core measurements
      CAST(temperature AS FLOAT64) AS temperature,
      CAST(temperature_high AS FLOAT64) AS temperature_high,
      CAST(temperature_low AS FLOAT64) AS temperature_low,
      CAST(humidity AS FLOAT64) AS humidity,
      CAST(humidity_high AS FLOAT64) AS humidity_high,
      CAST(humidity_low AS FLOAT64) AS humidity_low,
      -- Precipitation
      CAST(precip_rate AS FLOAT64) AS precip_rate,
      CAST(precip_total AS FLOAT64) AS precip_total,
      -- Pressure
      CAST(pressure_max AS FLOAT64) AS pressure_max,
      CAST(pressure_min AS FLOAT64) AS pressure_min,
      CAST(pressure_trend AS FLOAT64) AS pressure_trend,
      -- Wind
      CAST(wind_speed_avg AS FLOAT64) AS wind_speed_avg,
      CAST(wind_speed_high AS FLOAT64) AS wind_speed_high,
      CAST(wind_speed_low AS FLOAT64) AS wind_speed_low,
      CAST(wind_gust_avg AS FLOAT64) AS wind_gust_avg,
      CAST(wind_gust_high AS FLOAT64) AS wind_gust_high,
      CAST(wind_gust_low AS FLOAT64) AS wind_gust_low,
      CAST(wind_direction_avg AS FLOAT64) AS wind_direction_avg,
      -- Dew point
      CAST(dew_point_avg AS FLOAT64) AS dew_point_avg,
      CAST(dew_point_high AS FLOAT64) AS dew_point_high,
      CAST(dew_point_low AS FLOAT64) AS dew_point_low,
      -- Heat index
      CAST(heat_index_avg AS FLOAT64) AS heat_index_avg,
      CAST(heat_index_high AS FLOAT64) AS heat_index_high,
      CAST(heat_index_low AS FLOAT64) AS heat_index_low,
      -- Wind chill
      CAST(wind_chill_avg AS FLOAT64) AS wind_chill_avg,
      CAST(wind_chill_high AS FLOAT64) AS wind_chill_high,
      CAST(wind_chill_low AS FLOAT64) AS wind_chill_low,
      -- Solar
      CAST(solar_radiation AS FLOAT64) AS solar_radiation,
      CAST(uv_high AS FLOAT64) AS uv_high
    FROM `${PROJECT}.${DATASET}.wu_raw_materialized`
    WHERE ts IS NOT NULL AND DATE(ts) = proc_date
  ),
  tsi_src AS (
    SELECT
      ts AS timestamp,
      native_sensor_id,
  -- latitude, longitude removed
      -- Particulate Matter measurements
      CAST(pm1_0 AS FLOAT64) AS pm1_0,
      CAST(pm2_5 AS FLOAT64) AS pm2_5,
      CAST(pm4_0 AS FLOAT64) AS pm4_0,
      CAST(pm10 AS FLOAT64) AS pm10,
      CAST(pm2_5_aqi AS FLOAT64) AS pm2_5_aqi,
      CAST(pm10_aqi AS FLOAT64) AS pm10_aqi,
      -- Number Concentration measurements
      CAST(ncpm0_5 AS FLOAT64) AS ncpm0_5,
      CAST(ncpm1_0 AS FLOAT64) AS ncpm1_0,
      CAST(ncpm2_5 AS FLOAT64) AS ncpm2_5,
      CAST(ncpm4_0 AS FLOAT64) AS ncpm4_0,
      CAST(ncpm10 AS FLOAT64) AS ncpm10,
      -- Environmental measurements
      CAST(temperature AS FLOAT64) AS temperature,
      CAST(humidity AS FLOAT64) AS humidity,
      CAST(tpsize AS FLOAT64) AS tpsize,
      -- Gas measurements
      CAST(co2_ppm AS FLOAT64) AS co2_ppm,
      CAST(co_ppm AS FLOAT64) AS co_ppm,
      CAST(o3_ppb AS FLOAT64) AS o3_ppb,
      CAST(no2_ppb AS FLOAT64) AS no2_ppb,
      CAST(so2_ppb AS FLOAT64) AS so2_ppb,
      CAST(ch2o_ppb AS FLOAT64) AS ch2o_ppb,
      CAST(voc_mgm3 AS FLOAT64) AS voc_mgm3,
      -- Pressure
      CAST(baro_inhg AS FLOAT64) AS baro_inhg
    FROM `${PROJECT}.${DATASET}.tsi_raw_materialized`
    WHERE ts IS NOT NULL AND DATE(ts) = proc_date
  ),
  wu_long AS (
    SELECT 
      timestamp, 
      native_sensor_id, 
      metric_name, 
      value,
      'wu' AS source
    FROM wu_src
    UNPIVOT (value FOR metric_name IN (
      temperature, temperature_high, temperature_low,
      humidity, humidity_high, humidity_low,
      precip_rate, precip_total,
      pressure_max, pressure_min, pressure_trend,
      wind_speed_avg, wind_speed_high, wind_speed_low,
      wind_gust_avg, wind_gust_high, wind_gust_low,
      wind_direction_avg,
      dew_point_avg, dew_point_high, dew_point_low,
      heat_index_avg, heat_index_high, heat_index_low,
      wind_chill_avg, wind_chill_high, wind_chill_low,
      solar_radiation, uv_high
    ))
  ),
  tsi_long AS (
    SELECT 
      timestamp, 
      native_sensor_id, 
      metric_name, 
      value,
      'tsi' AS source
    FROM tsi_src
    UNPIVOT (value FOR metric_name IN (
      -- Particulate Matter
      pm1_0, pm2_5, pm4_0, pm10, pm2_5_aqi, pm10_aqi,
      -- Number Concentration
      ncpm0_5, ncpm1_0, ncpm2_5, ncpm4_0, ncpm10,
      -- Environmental
      temperature, humidity, tpsize,
      -- Gases
      co2_ppm, co_ppm, o3_ppb, no2_ppb, so2_ppb, ch2o_ppb, voc_mgm3,
      -- Pressure
      baro_inhg
    ))
  )
SELECT 
  timestamp,
  DATE(timestamp) AS timestamp_date,
  native_sensor_id, 
  metric_name, 
  value,
  source,
  FARM_FINGERPRINT(CONCAT(CAST(timestamp AS STRING), native_sensor_id, metric_name)) AS row_id
FROM wu_long
UNION ALL
SELECT 
  timestamp,
  DATE(timestamp) AS timestamp_date,
  native_sensor_id, 
  metric_name, 
  value,
  source,
  FARM_FINGERPRINT(CONCAT(CAST(timestamp AS STRING), native_sensor_id, metric_name)) AS row_id
FROM tsi_long
LIMIT 0;

-- Refresh the target partition for proc_date
DELETE FROM `${PROJECT}.${DATASET}.sensor_readings_long`
WHERE DATE(timestamp) = proc_date;

INSERT INTO `${PROJECT}.${DATASET}.sensor_readings_long`
  (timestamp, timestamp_date, native_sensor_id, metric_name, value, source, row_id)
WITH
  wu_src AS (
    SELECT
      ts AS timestamp,
      native_sensor_id,
      COALESCE(CAST(lat_f AS FLOAT64), CAST(lat AS FLOAT64)) AS latitude,
      COALESCE(CAST(lon_f AS FLOAT64), CAST(lon AS FLOAT64)) AS longitude,
      -- Core measurements
      CAST(temperature AS FLOAT64) AS temperature,
      CAST(temperature_high AS FLOAT64) AS temperature_high,
      CAST(temperature_low AS FLOAT64) AS temperature_low,
      CAST(humidity AS FLOAT64) AS humidity,
      CAST(humidity_high AS FLOAT64) AS humidity_high,
      CAST(humidity_low AS FLOAT64) AS humidity_low,
      -- Precipitation
      CAST(precip_rate AS FLOAT64) AS precip_rate,
      CAST(precip_total AS FLOAT64) AS precip_total,
      -- Pressure
      CAST(pressure_max AS FLOAT64) AS pressure_max,
      CAST(pressure_min AS FLOAT64) AS pressure_min,
      CAST(pressure_trend AS FLOAT64) AS pressure_trend,
      -- Wind
      CAST(wind_speed_avg AS FLOAT64) AS wind_speed_avg,
      CAST(wind_speed_high AS FLOAT64) AS wind_speed_high,
      CAST(wind_speed_low AS FLOAT64) AS wind_speed_low,
      CAST(wind_gust_avg AS FLOAT64) AS wind_gust_avg,
      CAST(wind_gust_high AS FLOAT64) AS wind_gust_high,
      CAST(wind_gust_low AS FLOAT64) AS wind_gust_low,
      CAST(wind_direction_avg AS FLOAT64) AS wind_direction_avg,
      -- Dew point
      CAST(dew_point_avg AS FLOAT64) AS dew_point_avg,
      CAST(dew_point_high AS FLOAT64) AS dew_point_high,
      CAST(dew_point_low AS FLOAT64) AS dew_point_low,
      -- Heat index
      CAST(heat_index_avg AS FLOAT64) AS heat_index_avg,
      CAST(heat_index_high AS FLOAT64) AS heat_index_high,
      CAST(heat_index_low AS FLOAT64) AS heat_index_low,
      -- Wind chill
      CAST(wind_chill_avg AS FLOAT64) AS wind_chill_avg,
      CAST(wind_chill_high AS FLOAT64) AS wind_chill_high,
      CAST(wind_chill_low AS FLOAT64) AS wind_chill_low,
      -- Solar
      CAST(solar_radiation AS FLOAT64) AS solar_radiation,
      CAST(uv_high AS FLOAT64) AS uv_high
    FROM `${PROJECT}.${DATASET}.wu_raw_materialized`
    WHERE ts IS NOT NULL AND DATE(ts) = proc_date
  ),
  tsi_src AS (
    SELECT
      ts AS timestamp,
      native_sensor_id,
      COALESCE(CAST(latitude_f AS FLOAT64), CAST(latitude AS FLOAT64)) AS latitude,
      COALESCE(CAST(longitude_f AS FLOAT64), CAST(longitude AS FLOAT64)) AS longitude,
      -- Particulate Matter measurements
      CAST(pm1_0 AS FLOAT64) AS pm1_0,
      CAST(pm2_5 AS FLOAT64) AS pm2_5,
      CAST(pm4_0 AS FLOAT64) AS pm4_0,
      CAST(pm10 AS FLOAT64) AS pm10,
      CAST(pm2_5_aqi AS FLOAT64) AS pm2_5_aqi,
      CAST(pm10_aqi AS FLOAT64) AS pm10_aqi,
      -- Number Concentration measurements
      CAST(ncpm0_5 AS FLOAT64) AS ncpm0_5,
      CAST(ncpm1_0 AS FLOAT64) AS ncpm1_0,
      CAST(ncpm2_5 AS FLOAT64) AS ncpm2_5,
      CAST(ncpm4_0 AS FLOAT64) AS ncpm4_0,
      CAST(ncpm10 AS FLOAT64) AS ncpm10,
      -- Environmental measurements
      CAST(temperature AS FLOAT64) AS temperature,
      CAST(humidity AS FLOAT64) AS humidity,
      CAST(tpsize AS FLOAT64) AS tpsize,
      -- Gas measurements
      CAST(co2_ppm AS FLOAT64) AS co2_ppm,
      CAST(co_ppm AS FLOAT64) AS co_ppm,
      CAST(o3_ppb AS FLOAT64) AS o3_ppb,
      CAST(no2_ppb AS FLOAT64) AS no2_ppb,
      CAST(so2_ppb AS FLOAT64) AS so2_ppb,
      CAST(ch2o_ppb AS FLOAT64) AS ch2o_ppb,
      CAST(voc_mgm3 AS FLOAT64) AS voc_mgm3,
      -- Pressure
      CAST(baro_inhg AS FLOAT64) AS baro_inhg
    FROM `${PROJECT}.${DATASET}.tsi_raw_materialized`
    WHERE ts IS NOT NULL AND DATE(ts) = proc_date
  ),
  wu_long AS (
    SELECT 
      timestamp, 
      native_sensor_id, 
      metric_name, 
      value,
      'wu' AS source
    FROM wu_src
    UNPIVOT (value FOR metric_name IN (
      temperature, temperature_high, temperature_low,
      humidity, humidity_high, humidity_low,
      precip_rate, precip_total,
      pressure_max, pressure_min, pressure_trend,
      wind_speed_avg, wind_speed_high, wind_speed_low,
      wind_gust_avg, wind_gust_high, wind_gust_low,
      wind_direction_avg,
      dew_point_avg, dew_point_high, dew_point_low,
      heat_index_avg, heat_index_high, heat_index_low,
      wind_chill_avg, wind_chill_high, wind_chill_low,
      solar_radiation, uv_high
    ))
  ),
  tsi_long AS (
    SELECT 
      timestamp, 
      native_sensor_id, 
      metric_name, 
      value,
      'tsi' AS source
    FROM tsi_src
    UNPIVOT (value FOR metric_name IN (
      -- Particulate Matter
      pm1_0, pm2_5, pm4_0, pm10, pm2_5_aqi, pm10_aqi,
      -- Number Concentration
      ncpm0_5, ncpm1_0, ncpm2_5, ncpm4_0, ncpm10,
      -- Environmental
      temperature, humidity, tpsize,
      -- Gases
      co2_ppm, co_ppm, o3_ppb, no2_ppb, so2_ppb, ch2o_ppb, voc_mgm3,
      -- Pressure
      baro_inhg
    ))
  )
SELECT 
  timestamp,
  DATE(timestamp) AS timestamp_date,
  native_sensor_id, 
  metric_name, 
  value,
  source,
  FARM_FINGERPRINT(CONCAT(CAST(timestamp AS STRING), native_sensor_id, metric_name)) AS row_id
FROM wu_long
UNION ALL
SELECT 
  timestamp,
  DATE(timestamp) AS timestamp_date,
  native_sensor_id, 
  metric_name, 
  value,
  source,
  FARM_FINGERPRINT(CONCAT(CAST(timestamp AS STRING), native_sensor_id, metric_name)) AS row_id
FROM tsi_long;
