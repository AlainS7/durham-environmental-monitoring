-- Build long (tall) unified fact table with partition-aware DELETE+INSERT.
-- Uses @proc_date; safe to re-run for the same date.
--
-- HARMONIZATION STRATEGY (Feb 2026):
--   1. Raw metrics preserved as-is (e.g., pm2_5, temperature, humidity)
--   2. Per-sensor harmonized metrics added with _harmonized suffix
--      (e.g., pm2_5_harmonized, temperature_harmonized)
--      Uses per-sensor slope/intercept from calibration_config table.
--   3. Multivariate-corrected PM2.5 added as pm2_5_mv_corrected
--      Uses regression model: f(PM2.5, Temperature, Humidity) per sensor type.
--      AA (indoor):  30.2038 + 0.7833*PM2.5 - 0.2791*RH - 0.1221*T
--      BS (outdoor):  2.6875 + 0.6923*PM2.5 + 0.1156*T  - 0.0238*RH

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
      CAST(temperature AS FLOAT64) AS temperature,
      CAST(temperature_high AS FLOAT64) AS temperature_high,
      CAST(temperature_low AS FLOAT64) AS temperature_low,
      CAST(humidity AS FLOAT64) AS humidity,
      CAST(humidity_high AS FLOAT64) AS humidity_high,
      CAST(humidity_low AS FLOAT64) AS humidity_low,
      CAST(precip_rate AS FLOAT64) AS precip_rate,
      CAST(precip_total AS FLOAT64) AS precip_total,
      CAST(pressure_max AS FLOAT64) AS pressure_max,
      CAST(pressure_min AS FLOAT64) AS pressure_min,
      CAST(pressure_trend AS FLOAT64) AS pressure_trend,
      CAST(wind_speed_avg AS FLOAT64) AS wind_speed_avg,
      CAST(wind_speed_high AS FLOAT64) AS wind_speed_high,
      CAST(wind_speed_low AS FLOAT64) AS wind_speed_low,
      CAST(wind_gust_avg AS FLOAT64) AS wind_gust_avg,
      CAST(wind_gust_high AS FLOAT64) AS wind_gust_high,
      CAST(wind_gust_low AS FLOAT64) AS wind_gust_low,
      CAST(wind_direction_avg AS FLOAT64) AS wind_direction_avg,
      CAST(dew_point_avg AS FLOAT64) AS dew_point_avg,
      CAST(dew_point_high AS FLOAT64) AS dew_point_high,
      CAST(dew_point_low AS FLOAT64) AS dew_point_low,
      CAST(heat_index_avg AS FLOAT64) AS heat_index_avg,
      CAST(heat_index_high AS FLOAT64) AS heat_index_high,
      CAST(heat_index_low AS FLOAT64) AS heat_index_low,
      CAST(wind_chill_avg AS FLOAT64) AS wind_chill_avg,
      CAST(wind_chill_high AS FLOAT64) AS wind_chill_high,
      CAST(wind_chill_low AS FLOAT64) AS wind_chill_low,
      CAST(solar_radiation AS FLOAT64) AS solar_radiation,
      CAST(uv_high AS FLOAT64) AS uv_high
    FROM `${PROJECT}.${DATASET}.wu_raw_materialized`
    WHERE ts IS NOT NULL AND DATE(ts) = proc_date
  ),
  tsi_src AS (
    SELECT
      ts AS timestamp,
      native_sensor_id,
      is_indoor,
      CAST(pm1_0 AS FLOAT64) AS pm1_0,
      CAST(pm2_5 AS FLOAT64) AS pm2_5,
      CAST(pm4_0 AS FLOAT64) AS pm4_0,
      CAST(pm10 AS FLOAT64) AS pm10,
      CAST(pm2_5_aqi AS FLOAT64) AS pm2_5_aqi,
      CAST(pm10_aqi AS FLOAT64) AS pm10_aqi,
      CAST(ncpm0_5 AS FLOAT64) AS ncpm0_5,
      CAST(ncpm1_0 AS FLOAT64) AS ncpm1_0,
      CAST(ncpm2_5 AS FLOAT64) AS ncpm2_5,
      CAST(ncpm4_0 AS FLOAT64) AS ncpm4_0,
      CAST(ncpm10 AS FLOAT64) AS ncpm10,
      CAST(temperature AS FLOAT64) AS temperature,
      CAST(humidity AS FLOAT64) AS humidity,
      CAST(tpsize AS FLOAT64) AS tpsize,
      CAST(co2_ppm AS FLOAT64) AS co2_ppm,
      CAST(co_ppm AS FLOAT64) AS co_ppm,
      CAST(o3_ppb AS FLOAT64) AS o3_ppb,
      CAST(no2_ppb AS FLOAT64) AS no2_ppb,
      CAST(so2_ppb AS FLOAT64) AS so2_ppb,
      CAST(ch2o_ppb AS FLOAT64) AS ch2o_ppb,
      CAST(voc_mgm3 AS FLOAT64) AS voc_mgm3,
      CAST(baro_inhg AS FLOAT64) AS baro_inhg
    FROM `${PROJECT}.${DATASET}.tsi_raw_materialized`
    WHERE ts IS NOT NULL AND DATE(ts) = proc_date
  ),
  wu_long AS (
    SELECT timestamp, native_sensor_id, metric_name, value, 'wu' AS source
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
    SELECT timestamp, native_sensor_id, metric_name, value, 'tsi' AS source
    FROM tsi_src
    UNPIVOT (value FOR metric_name IN (
      pm1_0, pm2_5, pm4_0, pm10, pm2_5_aqi, pm10_aqi,
      ncpm0_5, ncpm1_0, ncpm2_5, ncpm4_0, ncpm10,
      temperature, humidity, tpsize,
      co2_ppm, co_ppm, o3_ppb, no2_ppb, so2_ppb, ch2o_ppb, voc_mgm3,
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

-- ============================================================================
-- ACTUAL DATA LOAD: DELETE+INSERT for the partition
-- ============================================================================

DELETE FROM `${PROJECT}.${DATASET}.sensor_readings_long`
WHERE DATE(timestamp) = proc_date;

INSERT INTO `${PROJECT}.${DATASET}.sensor_readings_long`
  (timestamp, timestamp_date, native_sensor_id, metric_name, value, source, row_id)
WITH
  -- ─── Raw source CTEs ─────────────────────────────────────────────────
  wu_src AS (
    SELECT
      ts AS timestamp,
      native_sensor_id,
      COALESCE(CAST(lat_f AS FLOAT64), CAST(lat AS FLOAT64)) AS latitude,
      COALESCE(CAST(lon_f AS FLOAT64), CAST(lon AS FLOAT64)) AS longitude,
      CAST(temperature AS FLOAT64) AS temperature,
      CAST(temperature_high AS FLOAT64) AS temperature_high,
      CAST(temperature_low AS FLOAT64) AS temperature_low,
      CAST(humidity AS FLOAT64) AS humidity,
      CAST(humidity_high AS FLOAT64) AS humidity_high,
      CAST(humidity_low AS FLOAT64) AS humidity_low,
      CAST(precip_rate AS FLOAT64) AS precip_rate,
      CAST(precip_total AS FLOAT64) AS precip_total,
      CAST(pressure_max AS FLOAT64) AS pressure_max,
      CAST(pressure_min AS FLOAT64) AS pressure_min,
      CAST(pressure_trend AS FLOAT64) AS pressure_trend,
      CAST(wind_speed_avg AS FLOAT64) AS wind_speed_avg,
      CAST(wind_speed_high AS FLOAT64) AS wind_speed_high,
      CAST(wind_speed_low AS FLOAT64) AS wind_speed_low,
      CAST(wind_gust_avg AS FLOAT64) AS wind_gust_avg,
      CAST(wind_gust_high AS FLOAT64) AS wind_gust_high,
      CAST(wind_gust_low AS FLOAT64) AS wind_gust_low,
      CAST(wind_direction_avg AS FLOAT64) AS wind_direction_avg,
      CAST(dew_point_avg AS FLOAT64) AS dew_point_avg,
      CAST(dew_point_high AS FLOAT64) AS dew_point_high,
      CAST(dew_point_low AS FLOAT64) AS dew_point_low,
      CAST(heat_index_avg AS FLOAT64) AS heat_index_avg,
      CAST(heat_index_high AS FLOAT64) AS heat_index_high,
      CAST(heat_index_low AS FLOAT64) AS heat_index_low,
      CAST(wind_chill_avg AS FLOAT64) AS wind_chill_avg,
      CAST(wind_chill_high AS FLOAT64) AS wind_chill_high,
      CAST(wind_chill_low AS FLOAT64) AS wind_chill_low,
      CAST(solar_radiation AS FLOAT64) AS solar_radiation,
      CAST(uv_high AS FLOAT64) AS uv_high
    FROM `${PROJECT}.${DATASET}.wu_raw_materialized`
    WHERE ts IS NOT NULL AND DATE(ts) = proc_date
  ),

  tsi_src AS (
    SELECT
      ts AS timestamp,
      native_sensor_id,
      is_indoor,
      COALESCE(CAST(latitude_f AS FLOAT64), CAST(latitude AS FLOAT64)) AS latitude,
      COALESCE(CAST(longitude_f AS FLOAT64), CAST(longitude AS FLOAT64)) AS longitude,
      CAST(pm1_0 AS FLOAT64) AS pm1_0,
      CAST(pm2_5 AS FLOAT64) AS pm2_5,
      CAST(pm4_0 AS FLOAT64) AS pm4_0,
      CAST(pm10 AS FLOAT64) AS pm10,
      CAST(pm2_5_aqi AS FLOAT64) AS pm2_5_aqi,
      CAST(pm10_aqi AS FLOAT64) AS pm10_aqi,
      CAST(ncpm0_5 AS FLOAT64) AS ncpm0_5,
      CAST(ncpm1_0 AS FLOAT64) AS ncpm1_0,
      CAST(ncpm2_5 AS FLOAT64) AS ncpm2_5,
      CAST(ncpm4_0 AS FLOAT64) AS ncpm4_0,
      CAST(ncpm10 AS FLOAT64) AS ncpm10,
      CAST(temperature AS FLOAT64) AS temperature,
      CAST(humidity AS FLOAT64) AS humidity,
      CAST(tpsize AS FLOAT64) AS tpsize,
      CAST(co2_ppm AS FLOAT64) AS co2_ppm,
      CAST(co_ppm AS FLOAT64) AS co_ppm,
      CAST(o3_ppb AS FLOAT64) AS o3_ppb,
      CAST(no2_ppb AS FLOAT64) AS no2_ppb,
      CAST(so2_ppb AS FLOAT64) AS so2_ppb,
      CAST(ch2o_ppb AS FLOAT64) AS ch2o_ppb,
      CAST(voc_mgm3 AS FLOAT64) AS voc_mgm3,
      CAST(baro_inhg AS FLOAT64) AS baro_inhg
    FROM `${PROJECT}.${DATASET}.tsi_raw_materialized`
    WHERE ts IS NOT NULL AND DATE(ts) = proc_date
  ),

  -- ─── UNPIVOT to long format (raw values) ─────────────────────────────
  wu_long AS (
    SELECT timestamp, native_sensor_id, metric_name, value, 'wu' AS source
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

  -- ─── WU Calibration (station-based temperature & humidity correction) ───
  -- Applies temperature and humidity calibration coefficients to WU sensor data.
  -- Calibration formula: calibrated = (raw × slope) + intercept
  wu_calibrated AS (
    SELECT
      wu.timestamp,
      wu.native_sensor_id,
      CONCAT(wu.metric_name, '_calibrated') AS metric_name,
      CASE
        WHEN wu.metric_name = 'temperature' AND c.a_temp IS NOT NULL THEN
          CAST((wu.value * c.a_temp) + c.b_temp AS FLOAT64)
        WHEN wu.metric_name = 'humidity' AND c.a_rh IS NOT NULL THEN
          CAST((wu.value * c.a_rh) + c.b_rh AS FLOAT64)
        ELSE NULL
      END AS value,
      'wu' AS source
    FROM wu_long wu
    LEFT JOIN `${PROJECT}.${DATASET}.wu_calibration_config` c
      ON wu.native_sensor_id = c.stationId
    WHERE wu.metric_name IN ('temperature', 'humidity')
      AND CASE
        WHEN wu.metric_name = 'temperature' THEN c.a_temp IS NOT NULL
        WHEN wu.metric_name = 'humidity' THEN c.a_rh IS NOT NULL
        ELSE FALSE
      END
  ),

  tsi_long AS (
    SELECT timestamp, native_sensor_id, metric_name, value, 'tsi' AS source
    FROM tsi_src
    UNPIVOT (value FOR metric_name IN (
      pm1_0, pm2_5, pm4_0, pm10, pm2_5_aqi, pm10_aqi,
      ncpm0_5, ncpm1_0, ncpm2_5, ncpm4_0, ncpm10,
      temperature, humidity, tpsize,
      co2_ppm, co_ppm, o3_ppb, no2_ppb, so2_ppb, ch2o_ppb, voc_mgm3,
      baro_inhg
    ))
  ),

  -- ─── Per-sensor harmonization (post-UNPIVOT) ─────────────────────────
  -- Applies slope/intercept from calibration_config to create _harmonized metrics.
  -- Only produces rows for metrics that have a matching calibration rule.
  harmonization_rules AS (
    SELECT
      native_sensor_id,
      metric_name,
      slope,
      intercept
    FROM `${PROJECT}.${DATASET}.calibration_config`
    WHERE effective_date <= proc_date
      AND (end_date IS NULL OR end_date >= proc_date)
      AND native_sensor_id != 'DEFAULT'
  ),

  tsi_harmonized AS (
    SELECT
      t.timestamp,
      t.native_sensor_id,
      CONCAT(t.metric_name, '_harmonized') AS metric_name,
      (t.value * h.slope) + h.intercept AS value,
      'tsi' AS source
    FROM tsi_long t
    INNER JOIN harmonization_rules h
      ON t.native_sensor_id = h.native_sensor_id
      AND t.metric_name = h.metric_name
  ),

  -- ─── Multivariate PM2.5 correction (pre-UNPIVOT) ─────────────────────
  -- Uses regression model with PM2.5 + Temperature + Humidity co-variates.
  -- Different coefficients for indoor (AA) vs outdoor (BS) sensors.
  -- AA: pm2_5_mv = 30.2038 + 0.7833*PM2.5 - 0.2791*RH - 0.1221*T
  -- BS: pm2_5_mv =  2.6875 + 0.6923*PM2.5 + 0.1156*T  - 0.0238*RH
  tsi_multivar_pm25 AS (
    SELECT
      timestamp,
      native_sensor_id,
      'pm2_5_mv_corrected' AS metric_name,
      CASE
        WHEN is_indoor = TRUE THEN
          30.203778832333313
          + 0.7832728929424163 * pm2_5
          + (-0.27911836195444806) * humidity
          + (-0.12214891946933756) * temperature
        ELSE
          2.687510099385168
          + 0.6922536497361194 * pm2_5
          + 0.11562486449436704 * temperature
          + (-0.023752731801088067) * humidity
      END AS value,
      'tsi' AS source
    FROM tsi_src
    WHERE pm2_5 IS NOT NULL
      AND humidity IS NOT NULL
      AND temperature IS NOT NULL
  ),

  -- ─── Combine everything ──────────────────────────────────────────────
  all_readings AS (
    -- Weather Underground: raw only
    SELECT timestamp, native_sensor_id, metric_name, value, source
    FROM wu_long

    UNION ALL

    -- Weather Underground: calibrated temperature & humidity
    SELECT timestamp, native_sensor_id, metric_name, value, source
    FROM wu_calibrated
    WHERE value IS NOT NULL

    UNION ALL

    -- TSI: raw metrics
    SELECT timestamp, native_sensor_id, metric_name, value, source
    FROM tsi_long

    UNION ALL

    -- TSI: per-sensor harmonized metrics (metric_name has _harmonized suffix)
    SELECT timestamp, native_sensor_id, metric_name, value, source
    FROM tsi_harmonized

    UNION ALL

    -- TSI: multivariate PM2.5 correction
    SELECT timestamp, native_sensor_id, metric_name, value, source
    FROM tsi_multivar_pm25
  )

SELECT
  timestamp,
  DATE(timestamp) AS timestamp_date,
  native_sensor_id,
  metric_name,
  value,
  source,
  FARM_FINGERPRINT(CONCAT(CAST(timestamp AS STRING), native_sensor_id, metric_name)) AS row_id
FROM all_readings;
