-- Resident access mapping and secure residence-level views.
-- This enables true per-resident data isolation when each resident uses
-- distinct query credentials (e.g., one Grafana data source service account
-- per resident).
--
-- Populate resident_user_access with credential identity -> residence mapping.
-- Example principal_email values:
--   resident-r1-grafana@durham-weather-466502.iam.gserviceaccount.com
--   resident-r2-grafana@durham-weather-466502.iam.gserviceaccount.com

DECLARE proc_date DATE DEFAULT @proc_date;

CREATE TABLE IF NOT EXISTS `${PROJECT}.${DATASET}.resident_user_access` (
  principal_email STRING NOT NULL,
  residence_id STRING NOT NULL,
  active BOOL NOT NULL,
  updated_at TIMESTAMP NOT NULL
)
CLUSTER BY principal_email, residence_id;

CREATE OR REPLACE VIEW `${PROJECT}.${DATASET}.residence_readings_daily_secure` AS
SELECT d.*
FROM `${PROJECT}.${DATASET}.residence_readings_daily` d
INNER JOIN `${PROJECT}.${DATASET}.resident_user_access` a
  ON d.residence_id = a.residence_id
WHERE a.active = TRUE
  AND LOWER(a.principal_email) = LOWER(SESSION_USER());

CREATE OR REPLACE VIEW `${PROJECT}.${DATASET}.residence_readings_hourly_secure` AS
SELECT h.*
FROM `${PROJECT}.${DATASET}.residence_readings_hourly` h
INNER JOIN `${PROJECT}.${DATASET}.resident_user_access` a
  ON h.residence_id = a.residence_id
WHERE a.active = TRUE
  AND LOWER(a.principal_email) = LOWER(SESSION_USER());
