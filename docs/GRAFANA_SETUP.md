# Grafana Data Source Configuration & Test Queries

## BigQuery Data Source Setup

### Connection Details

- **Type**: BigQuery
- **Project ID**: `durham-weather-466502`
- **Processing Location**: `US`
- **Authentication**: Default Service Account (if running on GCP) or Service Account Key JSON

### Enable BigQuery API

```bash
gcloud services enable bigquery.googleapis.com --project=durham-weather-466502
```

---

## Test Queries

### 1. TSI PM2.5 Last 7 Days (Time Series)

```sql
SELECT
  ts AS time,
  native_sensor_id AS metric,
  pm2_5 AS value
FROM `durham-weather-466502.sensors_shared.tsi_raw_materialized`
WHERE $__timeFilter(ts)
  AND pm2_5 IS NOT NULL
ORDER BY ts
```

**Grafana Settings:**

- Format: Time series
- Time column: `time`
- Metric column: `metric`
- Value column: `value`

---

### 2. WU Temperature Last 7 Days (Time Series)

```sql
SELECT
  ts AS time,
  native_sensor_id AS metric,
  temperature AS value
FROM `durham-weather-466502.sensors_shared.wu_raw_view`
WHERE $__timeFilter(ts)
  AND temperature IS NOT NULL
ORDER BY ts
```

---

### 3. TSI + WU Combined (Latest Values - Table)

```sql
WITH tsi_latest AS (
  SELECT
    native_sensor_id,
    MAX(ts) AS last_seen,
    AVG(pm2_5) AS avg_pm25,
    AVG(temperature) AS avg_temp
  FROM `durham-weather-466502.sensors_shared.tsi_raw_materialized`
  WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  GROUP BY native_sensor_id
),
wu_latest AS (
  SELECT
    native_sensor_id,
    MAX(ts) AS last_seen,
    AVG(temperature) AS avg_temp,
    AVG(humidity) AS avg_humidity
  FROM `durham-weather-466502.sensors_shared.wu_raw_view`
  WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
  GROUP BY native_sensor_id
)
SELECT 'TSI' AS source, * FROM tsi_latest
UNION ALL
SELECT 'WU' AS source, native_sensor_id, last_seen, NULL AS avg_pm25, avg_temp FROM wu_latest
ORDER BY last_seen DESC
```

**Grafana Settings:**

- Format: Table

---

### 4. Daily Data Freshness Check

```sql
SELECT
  'TSI' AS source,
  MAX(DATE(ts)) AS latest_date,
  DATE_DIFF(CURRENT_DATE(), MAX(DATE(ts)), DAY) AS days_behind
FROM `durham-weather-466502.sensors_shared.tsi_raw_materialized`
UNION ALL
SELECT
  'WU' AS source,
  MAX(DATE(ts)) AS latest_date,
  DATE_DIFF(CURRENT_DATE(), MAX(DATE(ts)), DAY) AS days_behind
FROM `durham-weather-466502.sensors_shared.wu_raw_view`
```

---

### 5. Sensor Count by Day (Last 30 Days)

```sql
SELECT
  DATE(ts) AS time,
  COUNT(DISTINCT native_sensor_id) AS sensor_count
FROM `durham-weather-466502.sensors_shared.tsi_raw_materialized`
WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY time
ORDER BY time
```

**Grafana Settings:**

- Format: Time series
- Time column: `time`
- Value column: `sensor_count`

---

## Troubleshooting

### "No data" in Grafana

1. Check time range picker (default may be "Last 6 hours")
2. Verify table has recent data:
   ```bash
   bq query --nouse_legacy_sql "SELECT MAX(ts) FROM \`durham-weather-466502.sensors_shared.tsi_raw_materialized\`"
   ```
3. Check partition pruning - queries with `WHERE ts >= ...` are much faster and cheaper

### Query too slow

- Always filter on `ts` column (partitioned)
- Add `native_sensor_id` filter when possible (clustered)
- Use aggregations (AVG, MAX) for large time ranges
- Consider pre-aggregated tables for dashboards (hourly/daily rollups)

---

## Daily Update Verification

### Check if data is updating daily:

```sql
SELECT
  DATE(ts) AS date,
  COUNT(*) AS tsi_rows,
  COUNT(DISTINCT native_sensor_id) AS tsi_sensors
FROM `durham-weather-466502.sensors_shared.tsi_raw_materialized`
WHERE DATE(ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY date
ORDER BY date DESC
```

Expected: New rows appear each day (after daily collection runs).
