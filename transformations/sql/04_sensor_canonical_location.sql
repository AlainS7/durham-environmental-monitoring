-- Compute a per-sensor canonical location to stabilize mapping when minor jitter occurs.
-- Strategy:
--  - Consider the last 90 days (rolling window updated daily)
--  - For each sensor, derive daily distinct rounded positions (ROUND to 5 decimals ~1m)
--  - Choose the most frequent rounded position (mode); tie-breaker = most recent day seen
--  - Output canonical_latitude/longitude and a GEOGRAPHY point
-- 
-- NOTE: This is now a VIEW (not a table) to avoid expensive daily full-table rewrites.
-- It uses CURRENT_DATE() for a rolling 90-day window instead of the @proc_date parameter.

CREATE OR REPLACE VIEW `${PROJECT}.${DATASET}.sensor_canonical_location` AS
WITH windowed AS (
  -- Source directly from materialized raw tables to avoid dependency on long table schema
  SELECT
    native_sensor_id,
    ts AS timestamp,
    COALESCE(CAST(lat_f AS FLOAT64), CAST(lat AS FLOAT64)) AS latitude,
    COALESCE(CAST(lon_f AS FLOAT64), CAST(lon AS FLOAT64)) AS longitude
  FROM `${PROJECT}.${DATASET}.wu_raw_materialized`
  WHERE ts IS NOT NULL
    AND DATE(ts) BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 89 DAY) AND CURRENT_DATE()
    AND COALESCE(CAST(lat_f AS FLOAT64), CAST(lat AS FLOAT64)) IS NOT NULL
    AND COALESCE(CAST(lon_f AS FLOAT64), CAST(lon AS FLOAT64)) IS NOT NULL
  UNION ALL
  SELECT
    native_sensor_id,
    ts AS timestamp,
    COALESCE(CAST(latitude_f AS FLOAT64), CAST(latitude AS FLOAT64)) AS latitude,
    COALESCE(CAST(longitude_f AS FLOAT64), CAST(longitude AS FLOAT64)) AS longitude
  FROM `${PROJECT}.${DATASET}.tsi_raw_materialized`
  WHERE ts IS NOT NULL
    AND DATE(ts) BETWEEN DATE_SUB(CURRENT_DATE(), INTERVAL 89 DAY) AND CURRENT_DATE()
    AND COALESCE(CAST(latitude_f AS FLOAT64), CAST(latitude AS FLOAT64)) IS NOT NULL
    AND COALESCE(CAST(longitude_f AS FLOAT64), CAST(longitude AS FLOAT64)) IS NOT NULL
),
daily_positions AS (
  SELECT
    native_sensor_id,
    DATE(timestamp) AS day,
    ROUND(latitude, 5) AS lat_r,
    ROUND(longitude, 5) AS lon_r
  FROM windowed
  GROUP BY 1,2,3,4
),
coord_stats AS (
  SELECT
    native_sensor_id,
    lat_r,
    lon_r,
    COUNT(*) AS days_count,
    MAX(day) AS last_day
  FROM daily_positions
  GROUP BY 1,2,3
),
mode_coord AS (
  SELECT native_sensor_id, lat_r, lon_r, days_count, last_day
  FROM (
    SELECT
      native_sensor_id, lat_r, lon_r, days_count, last_day,
      ROW_NUMBER() OVER (
        PARTITION BY native_sensor_id
        ORDER BY days_count DESC, last_day DESC
      ) AS rn
    FROM coord_stats
  )
  WHERE rn = 1
),
sensor_window_stats AS (
  SELECT
    native_sensor_id,
    COUNT(DISTINCT day) AS days_observed,
    COUNT(DISTINCT CONCAT(CAST(lat_r AS STRING), ',', CAST(lon_r AS STRING))) AS distinct_locations
  FROM daily_positions
  GROUP BY 1
)
SELECT
  m.native_sensor_id,
  m.lat_r AS canonical_latitude,
  m.lon_r AS canonical_longitude,
  ST_GEOGPOINT(m.lon_r, m.lat_r) AS canonical_geog,
  CURRENT_DATE() AS as_of_date,
  s.days_observed,
  s.distinct_locations,
  m.days_count AS coord_mode_count,
  m.last_day AS coord_mode_last_day
FROM mode_coord m
LEFT JOIN sensor_window_stats s USING (native_sensor_id);
