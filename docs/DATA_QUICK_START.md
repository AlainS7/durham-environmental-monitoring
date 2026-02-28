# Guide — Pulling TSI (indoor) and WU (outdoor) data

Purpose: fast, copy-paste queries and a short decision map for common TSI (indoor air quality) and WU (Weather Underground) use cases.

## How to tell which table needs to be accessed

- Need building-level indoor metrics (PM2.5, CO2, VOC, temp)? → `sensors_shared.sensor_readings_daily` (filter `network='TSI'`)
- Need outdoor weather (temp, wind, rain, solar, UV)? → `sensors_shared.sensor_readings_daily` or `sensors.wu_daily_enriched` (filter `network='WU'`)
- Need high-frequency raw data → `tsi_raw_materialized` (TSI) or `wu_raw_materialized` (WU)

---

## Minimal examples (copy/paste)

TSI — one building, last 7 days

```sql
SELECT day_ts, metric_name, avg_value
FROM `durham-weather-466502.sensors_shared.sensor_readings_daily`
WHERE residence_id='R1' AND network='TSI' AND day_ts >= CURRENT_DATE()-7
ORDER BY day_ts DESC
```

WU — one outdoor station, last 7 days

```sql
SELECT day_ts, native_sensor_id, metric_name, avg_value
FROM `durham-weather-466502.sensors_shared.sensor_readings_daily`
WHERE native_sensor_id='KNCDURHA634' AND network='WU' AND day_ts >= CURRENT_DATE()-7
ORDER BY day_ts DESC
```

Correlate indoor PM2.5 with outdoor temperature (30 days)

```sql
SELECT DATE(t.day_ts) AS day, t.residence_id,
  AVG(CASE WHEN t.metric_name='pm2_5_mv_corrected' THEN t.avg_value END) AS pm25_indoor,
  AVG(CASE WHEN w.metric_name='temperature' THEN w.avg_value END) AS temp_outdoor
FROM `durham-weather-466502.sensors_shared.sensor_readings_daily` t
JOIN `durham-weather-466502.sensors_shared.sensor_readings_daily` w
  ON t.day_ts = w.day_ts
WHERE t.network='TSI' AND w.network='WU'
  AND t.metric_name='pm2_5_mv_corrected' AND w.metric_name='temperature'
  AND t.day_ts >= CURRENT_DATE()-30
GROUP BY day, t.residence_id
ORDER BY day DESC
```

Freshness check (both networks)

```sql
SELECT network, MAX(day_ts) AS latest_day, COUNT(DISTINCT CASE WHEN network='TSI' THEN residence_id ELSE native_sensor_id END) AS sensors
FROM `durham-weather-466502.sensors_shared.sensor_readings_daily`
GROUP BY network
```

TSI — enriched daily (name & location included)

```sql
SELECT day_ts, sensor_id, metric_name, avg_value
FROM `durham-weather-466502.sensors.tsi_daily_enriched`
WHERE day_ts >= CURRENT_DATE()-30
ORDER BY day_ts DESC
```

WU — enriched daily (station location included)

```sql
SELECT day_ts, native_sensor_id, metric_name, avg_value, latitude, longitude
FROM `durham-weather-466502.sensors.wu_daily_enriched`
WHERE day_ts >= CURRENT_DATE()-14
ORDER BY day_ts DESC
```

---

## Short reference — where to look

- Best-for-most: `sensors_shared.sensor_readings_daily` (both networks; daily aggregates)
- Enriched TSI daily: `sensors.tsi_daily_enriched` (TSI daily aggregates with sensor metadata)
- Raw / higher-frequency: production raw is `sensors.tsi_raw_materialized` (partitioned); a synced copy is available as `sensors_shared.tsi_raw_materialized` for Grafana. WU high-frequency: `sensors_shared.wu_raw_materialized`.
- Weather with location: `sensors.wu_daily_enriched` (adds lat/lon and station metadata)
- Sensor metadata: `sensors.sensors` and `sensors.sensor_deployment`

## Compact cheat sheet (metric examples)

- TSI (indoor): `pm2_5_mv_corrected`, `temperature`, `humidity`, `co2`, `voc`
- WU (outdoor): `temperature`, `humidity`, `precip_total`, `wind_speed_avg`, `wind_gust_avg`, `solar_radiation`, `uv_high`, `pressure_max`

## How to run

- BigQuery UI: open console → BigQuery → New query → paste → Run
- CLI (bq): `bq query --use_legacy_sql=false "<SQL>"`
- Python: use `google.cloud.bigquery.Client` then `client.query(...).to_dataframe()`

## Quick troubleshooting

- No rows: check `MAX(day_ts)` for the network.
- Missing column/metric: try `SELECT * LIMIT 1` from the table to inspect column names.
- Wrong network: add `WHERE network='TSI'` or `network='WU'` as appropriate.

---

If you want, I can also:

- produce a 1-page PDF with these examples for coworker onboarding
- add a short list of recommended saved queries (BigQuery)

File: [docs/DATA_QUICK_START.md](docs/DATA_QUICK_START.md)

---

## All tables & dataset structure

Use this when you need to decide which table to query. Prefer `sensor_readings_daily` for most analyses.

`durham-weather-466502` (top-level)

- `sensors_shared` (Grafana layer / daily summaries)
  - `sensor_readings_daily` — daily aggregates for all sensors (TSI + WU). Best starting point.
  - `sensor_readings_long` — long/raw daily rows (unaggregated)
  - `tsi_raw_materialized` — 15-min TSI raw (high-frequency)
  - `tsi_raw_view` — live TSI view used by apps/dashboards
  - `wu_raw_materialized` — hourly/raw WU weather data
  - `wu_raw_view` — enriched WU view (sensor_id/location)
  - `residence_readings_daily` — TSI aggregated by residence (useful for Grafana)

- `sensors` (metadata & enriched views)
  - `sensors` — sensor names, deployment, lat/lon, sensor type
  - `calibration_config` — TSI calibration settings
  - `wu_daily_enriched` — WU daily with location and station metadata (good for maps)
  - `all_sensors_daily_enriched` — enriched union of sensor metadata + daily values
    - `tsi_daily_enriched` — TSI daily aggregates + sensor metadata (view; useful when you want daily TSI with location/name)

Notes:

- Grafana queries should stick to `sensors_shared` where possible (dataset is synced daily).
- If you need per-minute or raw hourly trends, use the `_raw_materialized` tables but beware of size/cost.

### **Quick Troubleshooting**

- **"I don't see any data"** → Check the date range with: `SELECT MAX(day_ts) FROM ... WHERE network = 'TSI'` (or 'WU')
- **"Wrong network"** → Make sure you're filtering by `network = 'TSI'` or `network = 'WU'`
- **"Table not found"** → Check the dataset (is it in `sensors_shared` or `sensors`?)
- **"Column doesn't exist"** → Check the metric name spelling or use `SELECT * LIMIT 1` to see available columns
- **"Need multiple metrics"** → Use `IN ('metric1', 'metric2', 'metric3')` to filter multiple at once

### **The Two Networks Explained**

- **TSI** = Indoor air quality sensors (PM2.5, CO2, VOC, temp, humidity) in ~13 residences
- **WU** = Outdoor weather stations (temperature, wind, rain, solar, UV, pressure) in ~13 locations across Durham
- Both update daily; join them to correlate indoor and outdoor conditions
