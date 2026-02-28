-- Variables: ${PROJECT} (GCP project ID), substituted at runtime by envsubst or shell
-- TSI pipeline: numeric schema hardening + cross-dataset view + daily refresh.
-- Strategy: Avoid data duplication; view in sensors_shared points to sensors.tsi_raw_materialized.
-- Materialized table refreshed daily to match your staging cadence; Grafana queries it directly.

-- 1) Numeric coercion applied in src/storage/gcs_uploader.py before Parquet write
--    ensures all float/int columns are written as float64 (no schema drift).

-- 2) sensors.tsi_raw_materialized (production table)
--    - Partitioned by DATE(ts), clustered by native_sensor_id
--    - ~1.32M rows, ~15GB current physical bytes
--    - Updated incrementally as new Parquet files load

-- 3) sensors_shared.tsi_raw_view (cross-dataset view)
--    - Points to sensors.tsi_raw_materialized
--    - No data duplication, preserves partition pruning
--    - Example Grafana query: SELECT ts, native_sensor_id, pm2_5 FROM `${PROJECT}.sensors_shared.tsi_raw_view` WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)

-- 4) sensors_shared.tsi_raw_materialized (refreshed daily)
--    - Materialized snapshot for Grafana direct access (better perf vs view)
--    - Refresh via: bash scripts/refresh_tsi_shared.sh (daily, e.g., after staging)
--    - Or use BigQuery Scheduled Query with the SQL below
--    - Partition pruning: DATE(ts) CLUSTER BY native_sensor_id

CREATE OR REPLACE TABLE `${PROJECT}.sensors_shared.tsi_raw_materialized`
PARTITION BY DATE(ts)
CLUSTER BY native_sensor_id AS
SELECT ts, cloud_account_id, native_sensor_id, model, serial,
       latitude, longitude, is_indoor, is_public,
       pm1_0, pm2_5, pm4_0, pm10, pm2_5_aqi, pm10_aqi,
       ncpm0_5, ncpm1_0, ncpm2_5, ncpm4_0, ncpm10,
       temperature, humidity, tpsize, co2_ppm, co_ppm, baro_inhg,
       o3_ppb, no2_ppb, so2_ppb, ch2o_ppb, voc_mgm3, latitude_f, longitude_f
FROM `${PROJECT}.sensors_shared.tsi_raw_view`;

-- Validation
-- SELECT COUNT(*) rows, MAX(ts) max_ts FROM `${PROJECT}.sensors_shared.tsi_raw_materialized`;
-- SELECT ts, native_sensor_id, pm2_5 FROM `${PROJECT}.sensors_shared.tsi_raw_view` 
--   WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) ORDER BY ts DESC LIMIT 10;
