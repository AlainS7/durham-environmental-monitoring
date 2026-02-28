-- Residence-Sensor Assignment Dimension Table
-- Tracks which sensors are deployed at which residence over time.
-- Supports temporal assignments (sensors can move between residences).
--
-- Public template: sensor_name values are safe to commit.
-- Keep native_sensor_id placeholders as dummy_sensor_id* in this file.
-- Generate the gitignored production SQL with:
--   make generate-sensor-assignments PROJECT=<gcp-project> RAW_DATASET=<dataset>
-- Preferred input for generation is a private template stored in
-- Secret Manager (RESIDENCE_ASSIGNMENTS_TEMPLATE_SECRET_ID) for cloud runs,
-- or transformations/sql/07_residence_sensor_assignments.private.template.sql
-- for local runs (gitignored).
-- Generator source: scripts/generate_residence_assignments.py

DECLARE proc_date DATE DEFAULT @proc_date;

-- Bootstrap table
CREATE TABLE IF NOT EXISTS `${PROJECT}.${DATASET}.residence_sensor_assignments`
(
  residence_id      STRING    NOT NULL,   -- anonymized residence identifier
  native_sensor_id  STRING    NOT NULL,   -- TSI device ID
  sensor_name       STRING,               -- anonymized sensor label
  sensor_role       STRING    NOT NULL,   -- 'Indoor' or 'Outdoor'
  start_ts          TIMESTAMP NOT NULL,   -- deployment start
  end_ts            TIMESTAMP,            -- deployment end (NULL = currently active)
  updated_at        TIMESTAMP NOT NULL
)
PARTITION BY DATE(start_ts)
CLUSTER BY residence_id, native_sensor_id;

-- ============================================================================
-- Seed / refresh assignment data
-- ============================================================================
-- WARNING: Do not commit real native_sensor_id values in this template.
-- Use the generator script to create the gitignored production SQL file.

-- Idempotent: clear and reload
DELETE FROM `${PROJECT}.${DATASET}.residence_sensor_assignments` WHERE TRUE;

INSERT INTO `${PROJECT}.${DATASET}.residence_sensor_assignments`
  (residence_id, native_sensor_id, sensor_name, sensor_role, start_ts, end_ts, updated_at)
VALUES
  -- Public-safe sample rows only. Keep real residence/sensor mappings out of git.
  ('RESIDENCE_A', 'dummy_sensor_id_in',  'SENSOR_A_IN',  'Indoor',  TIMESTAMP('2025-01-01 00:00:00'), NULL, CURRENT_TIMESTAMP()),
  ('RESIDENCE_A', 'dummy_sensor_id_out', 'SENSOR_A_OUT', 'Outdoor', TIMESTAMP('2025-01-01 00:00:00'), NULL, CURRENT_TIMESTAMP());
