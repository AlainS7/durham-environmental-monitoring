-- Views to simplify mapping in Looker Studio.

-- Latest canonical position per sensor (by as_of_date)
CREATE OR REPLACE VIEW `${PROJECT}.${DATASET}.sensor_canonical_latest` AS
WITH ranked AS (
  SELECT
    c.*,
    ROW_NUMBER() OVER (PARTITION BY c.native_sensor_id ORDER BY c.as_of_date DESC) AS rn
  FROM `${PROJECT}.${DATASET}.sensor_canonical_location` c
)
SELECT
  native_sensor_id,
  canonical_latitude,
  canonical_longitude,
  canonical_geog,
  as_of_date,
  days_observed,
  distinct_locations,
  coord_mode_count,
  coord_mode_last_day
FROM ranked
WHERE rn = 1;

-- Curated-over-canonical current coordinates per sensor
CREATE OR REPLACE VIEW `${PROJECT}.${DATASET}.sensor_location_current` AS
SELECT
  s.native_sensor_id,
  COALESCE(d.latitude, c.canonical_latitude) AS latitude,
  COALESCE(d.longitude, c.canonical_longitude) AS longitude,
  COALESCE(d.geog, c.canonical_geog) AS geog,
  -- Surface lifecycle fields from curated dim when present
  d.status,
  d.effective_date,
  d.notes,
  d.updated_at
FROM `${PROJECT}.${DATASET}.sensor_canonical_latest` c
RIGHT JOIN (
  SELECT DISTINCT native_sensor_id FROM `${PROJECT}.${DATASET}.sensor_readings_long`
) s USING (native_sensor_id)
LEFT JOIN `${PROJECT}.${DATASET}.sensor_location_dim` d USING (native_sensor_id);

-- Daily enriched summaries with canonical positions
CREATE OR REPLACE VIEW `${PROJECT}.${DATASET}.sensor_readings_daily_enriched` AS
SELECT
  d.day_ts,
  d.native_sensor_id,
  COALESCE(m.sensor_id, d.native_sensor_id) AS sensor_id,
  d.metric_name,
  d.metric_name AS metric,
  d.avg_value AS value,
  d.avg_value,
  d.min_value,
  d.max_value,
  d.samples,
  COALESCE(lc.latitude, NULL) AS latitude,
  COALESCE(lc.longitude, NULL) AS longitude,
  COALESCE(lc.geog, NULL) AS geog,
  lc.status AS status,
  lc.effective_date AS effective_date
FROM `${PROJECT}.${DATASET}.sensor_readings_daily` d
LEFT JOIN `${PROJECT}.${DATASET}.sensor_id_map` m
  ON d.native_sensor_id = m.native_sensor_id
 AND (m.effective_start_date IS NULL OR DATE(d.day_ts) >= m.effective_start_date)
 AND (m.effective_end_date   IS NULL OR DATE(d.day_ts) <= m.effective_end_date)
LEFT JOIN `${PROJECT}.${DATASET}.sensor_location_current` lc
  ON d.native_sensor_id = lc.native_sensor_id
WHERE lc.latitude IS NOT NULL AND lc.longitude IS NOT NULL AND lc.geog IS NOT NULL;

-- Long fact enriched with stable sensor_id mapping (if present)
CREATE OR REPLACE VIEW `${PROJECT}.${DATASET}.sensor_readings_long_enriched` AS
SELECT
  f.timestamp,
  f.native_sensor_id,
  COALESCE(m.sensor_id, f.native_sensor_id) AS sensor_id,
  f.metric_name,
  f.value,
  COALESCE(lc.latitude, NULL) AS latitude,
  COALESCE(lc.longitude, NULL) AS longitude,
  COALESCE(lc.geog, NULL) AS geog,
  lc.status,
  lc.effective_date
FROM `${PROJECT}.${DATASET}.sensor_readings_long` f
LEFT JOIN `${PROJECT}.${DATASET}.sensor_id_map` m
  ON f.native_sensor_id = m.native_sensor_id
 AND (m.effective_start_date IS NULL OR DATE(f.timestamp) >= m.effective_start_date)
 AND (m.effective_end_date   IS NULL OR DATE(f.timestamp) <= m.effective_end_date)
LEFT JOIN `${PROJECT}.${DATASET}.sensor_location_current` lc
  ON f.native_sensor_id = lc.native_sensor_id
WHERE lc.latitude IS NOT NULL AND lc.longitude IS NOT NULL AND lc.geog IS NOT NULL;
