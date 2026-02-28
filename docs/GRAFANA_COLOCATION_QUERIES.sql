-- ============================================================================
-- GRAFANA COLOCATION ANALYSIS QUERIES
-- ============================================================================
--
-- ⚠️ IMPORTANT: Grafana can ONLY access sensors_shared dataset
-- These queries use sensors_shared, which syncs from sensors dataset
--
-- Key points:
-- 1. All tables are in sensors_shared (synced daily via scripts/sync_to_grafana.py)
-- 2. Uses pm2_5_mv_corrected (the available corrected metric, not pm2_5_calibrated which doesn't exist)
-- 3. sensor_name contains network ID (AA-10, BS-22, etc.)
-- 4. residence_id identifies the house (R1, R2, ... R13 - NOT RES-001)
-- 5. ALWAYS sort ASC for Grafana time series (not DESC) - required for visualization
-- 6. Supports Grafana variables for time filtering and sensor selection
--
-- ============================================================================

-- ============════════════════════════════════════════════════════════════════
-- QUERY 1: Time Series - Network Comparison (Air Assure vs Bluesky)
-- ============════════════════════════════════════════════════════════════════
-- Use: Time series graph in Grafana
-- Shows two lines: one for each network at the same residence
-- Uses corrected PM2.5 metric
--
SELECT
  day_ts AS time,
  CASE 
    WHEN sensor_name LIKE 'AA-%' THEN 'Air Assure'
    WHEN sensor_name LIKE 'BS-%' THEN 'Bluesky'
    WHEN sensor_name LIKE 'AM-%' THEN 'Ambient'
  END AS network,
  ROUND(avg_value, 2) AS pm2_5_avg
FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
WHERE residence_id = 'R1'  -- Change to target residence (R1-R13)
  AND metric_name = 'pm2_5_mv_corrected'  -- Using corrected metric
  AND sensor_role = 'Indoor'
  AND $__timeFilter(day_ts)
ORDER BY day_ts ASC;

-- ============════════════════════════════════════════════════════════════════
-- QUERY 2: Scatter Plot - Correlation Analysis (Air Assure vs Bluesky)
-- ============════════════════════════════════════════════════════════════════
-- Use: Scatter plot in Grafana (X: Air Assure, Y: Bluesky)
-- Shows correlation between two networks (uses corrected metric)
--
WITH aa_data AS (
  SELECT
    day_ts,
    avg_value AS aa_pm25
  FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'AA-%'
    AND sensor_role = 'Indoor'
    AND $__timeFilter(day_ts)
),
bs_data AS (
  SELECT
    day_ts,
    avg_value AS bs_pm25
  FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'BS-%'
    AND sensor_role = 'Indoor'
    AND $__timeFilter(day_ts)
)
SELECT
  COALESCE(aa.day_ts, bs.day_ts) AS time,
  ROUND(aa.aa_pm25, 2) AS air_assure_pm25,
  ROUND(bs.bs_pm25, 2) AS bluesky_pm25,
  ROUND(ABS(aa.aa_pm25 - bs.bs_pm25), 2) AS difference_ug_m3,
  ROUND(SAFE_DIVIDE(aa.aa_pm25, bs.bs_pm25), 3) AS aa_to_bs_ratio
FROM aa_data aa
FULL OUTER JOIN bs_data bs
  ON aa.day_ts = bs.day_ts
ORDER BY time ASC;

-- ============════════════════════════════════════════════════════════════════
-- QUERY 3: Statistical Comparison - Network Agreement Metrics
-- ============════════════════════════════════════════════════════════════════
-- Use: Stat panels in Grafana (shows mean diff, correlation, etc.)
-- Metrics comparing how well two networks agree (corrected metric)
--
WITH aa_data AS (
  SELECT
    day_ts,
    avg_value AS aa_pm25
  FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'AA-%'
    AND sensor_role = 'Indoor'
    AND $__timeFilter(day_ts)
),
bs_data AS (
  SELECT
    day_ts,
    avg_value AS bs_pm25
  FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'BS-%'
    AND sensor_role = 'Indoor'
    AND $__timeFilter(day_ts)
),
paired_data AS (
  SELECT
    aa.aa_pm25,
    bs.bs_pm25,
    ABS(aa.aa_pm25 - bs.bs_pm25) AS abs_difference
  FROM aa_data aa
  FULL OUTER JOIN bs_data bs
    ON aa.day_ts = bs.day_ts
  WHERE aa.aa_pm25 IS NOT NULL
    AND bs.bs_pm25 IS NOT NULL
)
SELECT
  'Air Assure vs Bluesky' AS comparison,
  ROUND(AVG(aa_pm25), 2) AS aa_mean,
  ROUND(AVG(bs_pm25), 2) AS bs_mean,
  ROUND(AVG(abs_difference), 2) AS mean_absolute_diff,
  ROUND(STDDEV(aa_pm25), 2) AS aa_stddev,
  ROUND(STDDEV(bs_pm25), 2) AS bs_stddev,
  COUNT(*) AS overlapping_days
FROM paired_data;

-- ============════════════════════════════════════════════════════════════════
-- QUERY 4: Bland-Altman Plot Data (Agreement Analysis)
-- ============════════════════════════════════════════════════════════════════
-- Use: Scatter plot - Shows bias and limits of agreement
-- X-axis: Average of two readings, Y-axis: Difference (corrected metric)
--
WITH aa_data AS (
  SELECT
    day_ts,
    avg_value AS aa_pm25
  FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'AA-%'
    AND sensor_role = 'Indoor'
),
bs_data AS (
  SELECT
    day_ts,
    avg_value AS bs_pm25
  FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'BS-%'
    AND sensor_role = 'Indoor'
),
paired_data AS (
  SELECT
    aa.day_ts,
    (aa.aa_pm25 + bs.bs_pm25) / 2 AS mean_reading,
    (aa.aa_pm25 - bs.bs_pm25) AS difference
  FROM aa_data aa
  INNER JOIN bs_data bs
    ON aa.day_ts = bs.day_ts
)
SELECT
  ROUND(mean_reading, 1) AS average_pm25,
  ROUND(difference, 2) AS difference_aa_minus_bs,
  COUNT(*) AS count_measurements
FROM paired_data
GROUP BY ROUND(mean_reading, 1), ROUND(difference, 2)
ORDER BY average_pm25 ASC;

-- ============════════════════════════════════════════════════════════════════
-- QUERY 5: Hourly Colocation - Network Response Time Comparison
-- ============════════════════════════════════════════════════════════════════
-- Use: Time series (hourly) - Shows sensor responsiveness
-- Better temporal resolution for comparing network speeds (corrected metric)
--
WITH aa_hourly AS (
  SELECT
    hour_ts,
    native_sensor_id,
    sensor_name,
    avg_value AS aa_pm25
  FROM `durham-weather-466502.sensors_shared.residence_readings_hourly`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'AA-%'
    AND sensor_role = 'Indoor'
    AND $__timeFilter(hour_ts)
},
bs_hourly AS (
  SELECT
    hour_ts,
    native_sensor_id,
    sensor_name,
    avg_value AS bs_pm25
  FROM `durham-weather-466502.sensors_shared.residence_readings_hourly`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'BS-%'
    AND sensor_role = 'Indoor'
    AND $__timeFilter(hour_ts)
)
SELECT
  aa.hour_ts AS time,
  ROUND(aa.aa_pm25, 2) AS air_assure_pm25,
  ROUND(bs.bs_pm25, 2) AS bluesky_pm25,
  ROUND(ABS(aa.aa_pm25 - bs.bs_pm25), 2) AS diff_ug_m3
FROM aa_hourly aa
FULL OUTER JOIN bs_hourly bs
  ON aa.hour_ts = bs.hour_ts
ORDER BY time ASC;

-- ============════════════════════════════════════════════════════════════════
-- QUERY 6: Indoor vs Outdoor - Cross-Network Comparison
-- ============════════════════════════════════════════════════════════════════
-- Use: Multi-series time chart
-- Shows if indoor/outdoor response differs by network (corrected metric)
--
SELECT
  day_ts AS time,
  CONCAT(
    CASE 
      WHEN sensor_name LIKE 'AA-%' THEN 'Air Assure'
      WHEN sensor_name LIKE 'BS-%' THEN 'Bluesky'
      WHEN sensor_name LIKE 'AM-%' THEN 'Ambient'
    END,
    ' - ',
    sensor_role
  ) AS network_location,
  ROUND(avg_value, 2) AS pm2_5_avg,
  sensor_role,
  CASE 
    WHEN sensor_name LIKE 'AA-%' THEN 'Air Assure'
    WHEN sensor_name LIKE 'BS-%' THEN 'Bluesky'
    WHEN sensor_name LIKE 'AM-%' THEN 'Ambient'
  END AS network
FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
WHERE residence_id = 'R1'
  AND metric_name = 'pm2_5_mv_corrected'
  AND $__timeFilter(day_ts)
ORDER BY day_ts ASC;

-- ============════════════════════════════════════════════════════════════════
-- QUERY 7: Three-Way Comparison Table (Air Assure vs Bluesky vs Ambient)
-- ============════════════════════════════════════════════════════════════════
-- Use: Table panel - Shows all three networks daily (corrected metric)
--
WITH aa_data AS (
  SELECT
    day_ts,
    'Air Assure' AS network,
    ROUND(avg_value, 2) AS pm2_5,
    sensor_name
  FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'AA-%'
    AND sensor_role = 'Indoor'
),
bs_data AS (
  SELECT
    day_ts,
    'Bluesky' AS network,
    ROUND(avg_value, 2) AS pm2_5,
    sensor_name
  FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'BS-%'
    AND sensor_role = 'Indoor'
),
am_data AS (
  SELECT
    day_ts,
    'Ambient' AS network,
    ROUND(avg_value, 2) AS pm2_5,
    sensor_name
  FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'AM-%'
    AND sensor_role = 'Indoor'
)
SELECT
  day_ts AS date,
  aa.pm2_5 AS air_assure,
  bs.pm2_5 AS bluesky,
  am.pm2_5 AS ambient,
  ROUND(ABS(aa.pm2_5 - bs.pm2_5), 2) AS aa_vs_bs_diff,
  ROUND(ABS(bs.pm2_5 - am.pm2_5), 2) AS bs_vs_am_diff,
  ROUND(ABS(aa.pm2_5 - am.pm2_5), 2) AS aa_vs_am_diff
FROM aa_data aa
FULL OUTER JOIN bs_data bs ON aa.day_ts = bs.day_ts
FULL OUTER JOIN am_data am ON aa.day_ts = am.day_ts
ORDER BY day_ts ASC;

-- ============════════════════════════════════════════════════════════════════
-- QUERY 8: Equipment Performance Heatmap Data
-- ============════════════════════════════════════════════════════════════════
-- Use: Heatmap - Shows how sensor readings vary by network over day-of-week
-- Uses corrected metric
--
SELECT
  FORMAT_TIMESTAMP('%A', day_ts) AS day_of_week,
  EXTRACT(DAYOFWEEK FROM day_ts) AS dow,
  CASE 
    WHEN sensor_name LIKE 'AA-%' THEN 'Air Assure'
    WHEN sensor_name LIKE 'BS-%' THEN 'Bluesky'
    WHEN sensor_name LIKE 'AM-%' THEN 'Ambient'
  END AS network,
  ROUND(AVG(avg_value), 2) AS avg_pm25,
  ROUND(STDDEV(avg_value), 2) AS stddev_pm25
FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
WHERE residence_id = 'R1'
  AND metric_name = 'pm2_5_mv_corrected'
  AND sensor_role = 'Indoor'
  AND $__timeFilter(day_ts)
GROUP BY day_of_week, dow, network
ORDER BY dow ASC;

-- ============════════════════════════════════════════════════════════════════
-- QUERY 9: Rolling Correlation - Network Agreement Over Time
-- ============════════════════════════════════════════════════════════════════
-- Use: Time series - Shows if networks are drifting apart or closer
-- 30-day rolling correlation (corrected metric)
--
WITH aa_data AS (
  SELECT
    day_ts,
    avg_value AS aa_pm25
  FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'AA-%'
    AND sensor_role = 'Indoor'
),
bs_data AS (
  SELECT
    day_ts,
    avg_value AS bs_pm25
  FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
  WHERE residence_id = 'R1'
    AND metric_name = 'pm2_5_mv_corrected'
    AND sensor_name LIKE 'BS-%'
    AND sensor_role = 'Indoor'
),
paired_data AS (
  SELECT
    aa.day_ts,
    aa.aa_pm25,
    bs.bs_pm25
  FROM aa_data aa
  INNER JOIN bs_data bs ON aa.day_ts = bs.day_ts
)
SELECT
  day_ts AS time,
  ROUND(
    CORR(aa_pm25, bs_pm25) OVER (
      ORDER BY day_ts
      ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
    ),
    3
  ) AS rolling_30day_correlation
FROM paired_data
ORDER BY day_ts ASC;

-- ============════════════════════════════════════════════════════════════════
-- QUERY 10: Daily Min/Max Range - Network Consistency
-- ============════════════════════════════════════════════════════════════════
-- Use: Area chart - Shows range of readings, narrower = more consistent
-- Uses corrected metric
--
SELECT
  day_ts AS time,
  CASE 
    WHEN sensor_name LIKE 'AA-%' THEN 'Air Assure'
    WHEN sensor_name LIKE 'BS-%' THEN 'Bluesky'
    WHEN sensor_name LIKE 'AM-%' THEN 'Ambient'
  END AS network,
  ROUND(min_value, 2) AS min_pm25,
  ROUND(avg_value, 2) AS avg_pm25,
  ROUND(max_value, 2) AS max_pm25,
  ROUND(max_value - min_value, 2) AS daily_range
FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
WHERE residence_id = 'R1'
  AND metric_name = 'pm2_5_mv_corrected'
  AND sensor_role = 'Indoor'
  AND $__timeFilter(day_ts)
ORDER BY day_ts ASC;
