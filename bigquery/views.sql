-- Variables: ${PROJECT} (GCP project ID), substituted at runtime by envsubst or shell
-- Standardized view layer for dashboards
CREATE OR REPLACE VIEW `${PROJECT}.sensors.v_wu_clean` AS
SELECT
  timestamp,
  native_sensor_id,
  -- add more standardized field renames here as needed
  * EXCEPT(timestamp)
FROM `${PROJECT}.sensors.wu_raw_materialized`;

CREATE OR REPLACE VIEW `${PROJECT}.sensors.v_tsi_clean` AS
SELECT
  timestamp,
  native_sensor_id,
  * EXCEPT(timestamp)
FROM `${PROJECT}.sensors.tsi_raw_materialized`;
