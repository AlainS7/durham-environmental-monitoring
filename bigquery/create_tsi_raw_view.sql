-- Variables: ${PROJECT} (GCP project ID), substituted at runtime by envsubst or shell
-- TSI cross-dataset view.
-- Strategy: view points to production table sensors.tsi_raw_materialized (no data duplication).
-- Materialized table refresh is handled in bigquery/tsi_pipeline.sql.

CREATE SCHEMA IF NOT EXISTS `${PROJECT}.sensors_shared`;

-- Cross-dataset view: points to production native table in sensors dataset
-- Preserves partition pruning for cost efficiency
CREATE OR REPLACE VIEW `${PROJECT}.sensors_shared.tsi_raw_view` AS
SELECT
	ts, cloud_account_id, native_sensor_id, model, serial,
	latitude, longitude, is_indoor, is_public,
	pm1_0, pm2_5, pm4_0, pm10, pm2_5_aqi, pm10_aqi,
	ncpm0_5, ncpm1_0, ncpm2_5, ncpm4_0, ncpm10,
	temperature, humidity, tpsize, co2_ppm, co_ppm, baro_inhg,
	o3_ppb, no2_ppb, so2_ppb, ch2o_ppb, voc_mgm3, latitude_f, longitude_f
FROM `${PROJECT}.sensors.tsi_raw_materialized`;
