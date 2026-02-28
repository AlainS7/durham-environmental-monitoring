-- Residence-Sensor Assignment Dimension Table
-- Tracks which sensors are deployed at which residence over time.
-- Supports temporal assignments (sensors can move between residences).
--
-- Public template: sensor_name values are safe to commit.
-- Keep native_sensor_id as 'dummy_sensor_id' in this file.
-- Generate the gitignored production SQL with:
--   make generate-sensor-assignments PROJECT=<gcp-project> RAW_DATASET=<dataset>
-- Generator source: scripts/generate_residence_assignments.py

DECLARE proc_date DATE DEFAULT @proc_date;

-- Bootstrap table
CREATE TABLE IF NOT EXISTS `${PROJECT}.${DATASET}.residence_sensor_assignments`
(
  residence_id      STRING    NOT NULL,   -- e.g., 'R1', 'R2', ..., 'R13'
  native_sensor_id  STRING    NOT NULL,   -- TSI device ID
  sensor_name       STRING,               -- friendly name: 'AA-13', 'BS-22'
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
  -- R1: Indoor AA-13, Outdoor BS-1 → BS-22
  ('R1', 'dummy_sensor_id', 'AA-13',  'Indoor',  TIMESTAMP('2025-07-28 21:00:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R1', 'dummy_sensor_id', 'BS-1',   'Outdoor', TIMESTAMP('2025-02-20 00:00:00'), TIMESTAMP('2025-07-28 21:00:00'),  CURRENT_TIMESTAMP()),
  ('R1', 'dummy_sensor_id', 'BS-22',  'Outdoor', TIMESTAMP('2025-07-28 21:00:00'), NULL,                              CURRENT_TIMESTAMP()),

  -- R2: Indoor AA-4, Outdoor BS-3 → BS-23
  ('R2', 'dummy_sensor_id', 'AA-4',   'Indoor',  TIMESTAMP('2025-07-24 19:00:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R2', 'dummy_sensor_id', 'BS-3',   'Outdoor', TIMESTAMP('2025-04-26 14:30:00'), TIMESTAMP('2025-07-24 19:00:00'),  CURRENT_TIMESTAMP()),
  ('R2', 'dummy_sensor_id', 'BS-23',  'Outdoor', TIMESTAMP('2025-07-24 19:00:00'), NULL,                              CURRENT_TIMESTAMP()),

  -- R3: Indoor AA-2 (two stints) + AA-15, Outdoor BS-13
  ('R3', 'dummy_sensor_id', 'AA-2',   'Indoor',  TIMESTAMP('2025-06-06 00:00:00'), TIMESTAMP('2025-07-10 00:00:00'),  CURRENT_TIMESTAMP()),
  ('R3', 'dummy_sensor_id', 'AA-15',  'Indoor',  TIMESTAMP('2025-07-28 17:00:00'), TIMESTAMP('2025-09-24 00:00:00'),  CURRENT_TIMESTAMP()),
  ('R3', 'dummy_sensor_id', 'AA-2',   'Indoor',  TIMESTAMP('2025-12-31 00:00:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R3', 'dummy_sensor_id', 'BS-13',  'Outdoor', TIMESTAMP('2025-05-12 15:00:00'), NULL,                              CURRENT_TIMESTAMP()),

  -- R4: Indoor AA-3, Outdoor BS-18
  ('R4', 'dummy_sensor_id', 'AA-3',   'Indoor',  TIMESTAMP('2025-07-21 20:30:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R4', 'dummy_sensor_id', 'BS-18',  'Outdoor', TIMESTAMP('2025-07-21 20:30:00'), NULL,                              CURRENT_TIMESTAMP()),

  -- R5: Indoor AA-7, Outdoor BS-18 (shared with R4)
  ('R5', 'dummy_sensor_id', 'AA-7',   'Indoor',  TIMESTAMP('2025-09-11 10:00:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R5', 'dummy_sensor_id', 'BS-18',  'Outdoor', TIMESTAMP('2025-09-11 10:00:00'), NULL,                              CURRENT_TIMESTAMP()),

  -- R6: Indoor AA-14, Outdoor BS-26
  ('R6', 'dummy_sensor_id', 'AA-14',  'Indoor',  TIMESTAMP('2025-08-06 10:00:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R6', 'dummy_sensor_id', 'BS-26',  'Outdoor', TIMESTAMP('2025-08-06 10:00:00'), NULL,                              CURRENT_TIMESTAMP()),

  -- R7: Indoor AA-6, Outdoor BS-19
  ('R7', 'dummy_sensor_id', 'AA-6',   'Indoor',  TIMESTAMP('2025-07-22 14:00:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R7', 'dummy_sensor_id', 'BS-19',  'Outdoor', TIMESTAMP('2025-07-22 14:00:00'), NULL,                              CURRENT_TIMESTAMP()),

  -- R8: Indoor AA-10, Outdoor BS-20
  ('R8', 'dummy_sensor_id', 'AA-10',  'Indoor',  TIMESTAMP('2025-07-22 15:00:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R8', 'dummy_sensor_id', 'BS-20',  'Outdoor', TIMESTAMP('2025-07-22 15:00:00'), NULL,                              CURRENT_TIMESTAMP()),

  -- R9: Indoor AA-5, Outdoor BS-15
  ('R9', 'dummy_sensor_id', 'AA-5',   'Indoor',  TIMESTAMP('2025-07-24 17:30:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R9', 'dummy_sensor_id', 'BS-15',  'Outdoor', TIMESTAMP('2025-07-24 17:30:00'), NULL,                              CURRENT_TIMESTAMP()),

  -- R10: Indoor AA-12, Outdoor BS-27
  ('R10', 'dummy_sensor_id', 'AA-12',  'Indoor',  TIMESTAMP('2025-07-28 20:00:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R10', 'dummy_sensor_id', 'BS-27',  'Outdoor', TIMESTAMP('2025-07-28 20:00:00'), NULL,                              CURRENT_TIMESTAMP()),

  -- R11: Indoor AA-8, Outdoor BS-16
  ('R11', 'dummy_sensor_id', 'AA-8',   'Indoor',  TIMESTAMP('2025-07-26 11:00:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R11', 'dummy_sensor_id', 'BS-16',  'Outdoor', TIMESTAMP('2025-07-26 11:00:00'), NULL,                              CURRENT_TIMESTAMP()),

  -- R12: Indoor AA-9, Outdoor BS-6
  ('R12', 'dummy_sensor_id', 'AA-9',   'Indoor',  TIMESTAMP('2025-08-19 00:00:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R12', 'dummy_sensor_id', 'BS-6',   'Outdoor', TIMESTAMP('2025-08-19 00:00:00'), NULL,                              CURRENT_TIMESTAMP()),

  -- R13: Indoor AA-11, Outdoor BS-21
  ('R13', 'dummy_sensor_id', 'AA-11',  'Indoor',  TIMESTAMP('2025-07-21 14:00:00'), NULL,                              CURRENT_TIMESTAMP()),
  ('R13', 'dummy_sensor_id', 'BS-21',  'Outdoor', TIMESTAMP('2025-07-21 14:00:00'), NULL,                              CURRENT_TIMESTAMP());
