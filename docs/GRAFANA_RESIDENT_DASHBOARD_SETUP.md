# Grafana: Resident Environment Dashboard — Setup Guide

**Dashboard file:** `dashboard/home_env_dashboard_import.json`  
**SQL reference:** `docs/GRAFANA_RESIDENT_ENVIRONMENT_QUERIES.sql`

---

## 1. Import the Dashboard

1. In Grafana, go to **Dashboards → Import**
2. Click **Upload JSON file** and select:
   `dashboard/home_env_dashboard_import.json`
3. In the `BigQuery` data source dropdown, pick your existing BigQuery data source
   (project: `durham-weather-466502`, dataset: `sensors_shared`).
4. Click **Import**.

---

## 2. Required security view (true resident isolation)

This resident dashboard queries:

- `durham-weather-466502.sensors_shared.residence_readings_daily_secure`

Create it with:

```sql
-- See full file in transformations/sql/09_resident_access_security.sql
CREATE TABLE IF NOT EXISTS `durham-weather-466502.sensors_shared.resident_user_access` (
  principal_email STRING NOT NULL,
  residence_id STRING NOT NULL,
  active BOOL NOT NULL,
  updated_at TIMESTAMP NOT NULL
);

CREATE OR REPLACE VIEW `durham-weather-466502.sensors_shared.residence_readings_daily_secure` AS
SELECT d.*
FROM `durham-weather-466502.sensors_shared.residence_readings_daily` d
JOIN `durham-weather-466502.sensors_shared.resident_user_access` a
  ON d.residence_id = a.residence_id
WHERE a.active = TRUE
  AND LOWER(a.principal_email) = LOWER(SESSION_USER());
```

For true isolation, map each resident credential principal to exactly one
`residence_id` in `resident_user_access`.

---

## 3. Dashboard Variables

The resident import keeps one template variable:

| Variable        | Type  | Default       | Purpose                                 |
| --------------- | ----- | ------------- | --------------------------------------- |
| `$metric_name`  | Query | `pm2_5_mv_corrected` | Metric shown in resident sensor panels |

Residents do not get a residence selector in this dashboard.

---

## 4. Panels Included

### Section — Individual Sensors per Network (resident scoped)

> Panels **"Air Assure (AA) Sensors"**, **"Bluesky (BS) Sensors"**, **"Ambient (AM) Sensors"**

- **Type:** Time Series
- One line per sensor in the resident's mapped home
- No cross-residence data appears when secure view mapping is configured correctly
- Change `$metric_name` to switch metric

### Section — Colocation network comparison (resident scoped)

> Panels **"AA vs BS vs AM — Daily Averages"**, **"Network Agreement Stats"**, **"AA − BS Delta"**, **"BS − AM Delta"**

- Shows agreement/divergence across network types for the mapped residence only
- Useful for quality checks and interpretation of harmonized metrics

### Section — Resident Daily Summary

> Panels **"Current State"** + **"Daily Metrics"**

- **Current State**: latest daily summary values
- **Daily Metrics**: trend view over time for core resident metrics
- **Within-Residence Daily Range**: daily spread (`max − min`) for selected metric
- **Pipeline Freshness**: quick lag status for TSI/WU/residence data sources

---

## 5. Adding More Metrics

The resident-limited dashboard intentionally constrains metric choices to:

`temperature` · `humidity` · `pm2_5_mv_corrected` · `co2_ppm` · `voc_mgm3`

If you want additional metrics for residents, update the metric variable query in
`dashboard/home_env_dashboard_import.json`.

---

## 6. Health Dashboard (Local HTML)

The **Oura Ring health dashboard** is separate and runs locally:

```bash
cd oura-rings/
../.venv/bin/python3 generate_health_dashboard.py --days 90
# Output: dashboard/resident_health_dashboard.html
open ../dashboard/resident_health_dashboard.html
```

**Options:**

```
--days N          History window in days (default: 90)
--residents 1,3,5 Only fetch specific residents (default: all)
--output PATH     Output HTML path
--no-bq           Skip BigQuery env correlation data
```

### Health Dashboard Charts

| Section            | Charts                                                        |
| ------------------ | ------------------------------------------------------------- |
| HRV                | Time series (all residents) + shaded cross-resident band      |
| HRV Variability    | 14-day rolling std per resident (within-person variability)   |
| HRV Distribution   | Box plot per resident                                         |
| Resting Heart Rate | Time series from lowest HR during sleep                       |
| Max Heart Rate     | Daily max HR from 5-min heart rate timeseries                 |
| HR Distribution    | Box plot per resident                                         |
| Sleep Score        | Time series + band                                            |
| Readiness Score    | Time series + band                                            |
| Sleep Duration     | Total sleep minutes per night                                 |
| Env Correlation    | HRV vs indoor temperature (coloured by thermal state)         |
| Env Correlation    | Sleep score vs indoor temperature (coloured by thermal state) |

> If a resident token is revoked or missing, that resident may return 403 or no data.
> Re-run with `--residents` to target specific residents.
