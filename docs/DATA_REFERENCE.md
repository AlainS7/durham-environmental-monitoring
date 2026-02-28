# Data Reference — Key tables and safe query patterns

This reference is for analysts who need more detail than the quick-start. It lists the important tables/views (TSI and WU), where they live, a short purpose, and one-line safe query tips.

---

## Where tables live

- `sensors` — production dataset (source of truth for sensor metadata and materialized raw tables)
- `sensors_shared` — synced dataset used by Grafana and shared access (daily sync from `sensors`)

---

## Key tables / views

### TSI (Indoor air quality)

- `sensors.tsi_raw_materialized` — partitioned raw 15-min TSI readings (production). Use for high-frequency analysis.
  - Safe tip: always filter by `DATE(ts)` or `_PARTITIONTIME`.
  - Example: `SELECT device_id, ts, pm2_5 FROM \`durham-weather-466502.sensors.tsi_raw_materialized\` WHERE DATE(ts) = '2026-02-01' LIMIT 100`

- `sensors_shared.tsi_raw_materialized` — synced copy for Grafana/limited-access users. Smaller window depending on sync.
  - Safe tip: prefer `sensors_shared` for dashboards; still filter by date.

- `sensors.tsi_daily_enriched` — view with TSI daily aggregates joined to sensor metadata (names/lat/lon).
  - Good for: quick daily reports with sensor names/locations.
  - Example: `SELECT day_ts, sensor_id, avg_value FROM \`durham-weather-466502.sensors.tsi_daily_enriched\` WHERE day_ts >= CURRENT_DATE()-7`

- `sensors_shared.sensor_readings_daily` — canonical daily aggregates for both networks (TSI + WU). Best-for-most analyses and Grafana panels.
  - Tip: filter `network='TSI'` or `network='WU'` to narrow results.

- `sensors_all_sensors_daily_enriched` / `all_sensors_daily_enriched` — enriched union (if present) with metadata + daily values. Use when you need a combined table.

### WU (Weather Underground)

- `sensors.wu_raw_materialized` — production hourly/raw WU weather data (source of truth).
  - Safe tip: always filter by `DATE(timestamp)` or the table partition when querying.

- `sensors_shared.wu_raw_materialized` — synced copy used by dashboards and shared users (refreshed from `sensors` by daily sync scripts).

- `sensors.wu_daily_enriched` — WU daily aggregates enriched with lat/lon and station metadata (good for maps). This view is created by `scripts/create_sensor_type_views.sql`.
  - Example: `SELECT day_ts, native_sensor_id, metric_name, avg_value, latitude, longitude FROM \`durham-weather-466502.sensors.wu_daily_enriched\` WHERE day_ts >= CURRENT_DATE()-14`

- `sensors_shared.sensor_readings_daily` — canonical daily aggregates covering WU when `network='WU'`; preferred for dashboards and quick lookups.

---

## Safe query patterns (to avoid high cost)

- Always select explicit columns instead of `SELECT *`.
- Always filter by a date range, e.g. `WHERE DATE(day_ts) BETWEEN '2026-02-01' AND '2026-02-07'`.
- When querying partitioned tables, prefer `_PARTITIONTIME` or `DATE(ts)` to hit specific partitions.
- Add `LIMIT` when exploring for column names or sampling rows.

Example safe exploratory pattern:

```sql
SELECT device_id, ts, pm2_5
FROM `durham-weather-466502.sensors.tsi_raw_materialized`
WHERE DATE(ts) BETWEEN '2026-02-01' AND '2026-02-03'
LIMIT 100
```

---

## Notes & recommendations

- For dashboards and non-technical use, prefer `sensors_shared.sensor_readings_daily` and `sensors.tsi_daily_enriched` (daily view with metadata).
- Reserve raw/materialized tables for analysts and automated jobs; document any heavy queries and consider caching or materializing results.
- If you want, I can add a short set of saved query files (SQL) in `/queries/` with examples for each table above.
