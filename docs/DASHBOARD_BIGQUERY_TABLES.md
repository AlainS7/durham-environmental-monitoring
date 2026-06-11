# Dashboard BigQuery Tables (Residence-Scoped Queries)

## Problem

The Grafana views `residence_readings_hourly` and `residence_readings_daily` join all sensors in each date partition to `residence_sensor_assignments`. When an app filters only by `residence_id`, BigQuery still scans every sensor in those partitions (~200+ MiB for a 14-day window), exceeding the dashboard's 100 MiB `maximumBytesBilled` cap.

## Approach (Option A — materialized residence tables)

Physical tables pre-join facts with assignments and cluster on `residence_id`:

| Table | Partition | Cluster | Refresh |
|-------|-----------|---------|---------|
| `sensors.residence_hourly_by_residence` | `DATE(hour_ts)` | `residence_id, sensor_role, metric_name` | Daily transform (`10_residence_materialized_tables.sql`) |
| `sensors.residence_daily_by_residence` | `DATE(day_ts)` | `residence_id, sensor_role, metric_name` | Daily transform (`10_residence_materialized_tables.sql`) |

Grafana views are unchanged. Apps query the materialized tables directly.

## Recommended queries (dashboard)

Project: `durham-weather-466502`, dataset: `sensors` (or `sensors_shared` after sync).

### Live / overview — indoor hourly (48h window)

```sql
SELECT hour_ts, metric_name, avg_value
FROM `durham-weather-466502.sensors.residence_hourly_by_residence`
WHERE residence_id = @residenceId
  AND sensor_role = 'Indoor'
  AND hour_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR)
ORDER BY hour_ts ASC
```

### Live / overview — outdoor hourly (48h window)

```sql
SELECT hour_ts, sensor_name, metric_name, avg_value
FROM `durham-weather-466502.sensors.residence_hourly_by_residence`
WHERE residence_id = @residenceId
  AND sensor_role = 'Outdoor'
  AND hour_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR)
ORDER BY hour_ts ASC
```

### History — daily comparison (7–365 days)

Always include a partition filter on `day_ts`:

```sql
SELECT day_ts, metric_name, avg_value
FROM `durham-weather-466502.sensors.residence_daily_by_residence`
WHERE residence_id = @residenceId
  AND sensor_role = 'Indoor'
  AND DATE(day_ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL @comparisonDays DAY)
ORDER BY day_ts ASC
```

Use `DATE(day_ts) >= ...` (or `day_ts >= TIMESTAMP(...)`) so partition pruning applies.

## Verification (dry-run)

```bash
# Hourly — target < 20 MiB
bq query --project_id=durham-weather-466502 --use_legacy_sql=false --dry_run '
SELECT hour_ts, metric_name, avg_value
FROM `durham-weather-466502.sensors.residence_hourly_by_residence`
WHERE residence_id = "R1"
  AND sensor_role = "Indoor"
  AND hour_ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 48 HOUR)
'

# Daily 7-day — target < 50 MiB
bq query --project_id=durham-weather-466502 --use_legacy_sql=false --dry_run '
SELECT day_ts, metric_name, avg_value
FROM `durham-weather-466502.sensors.residence_daily_by_residence`
WHERE residence_id = "R1"
  AND sensor_role = "Indoor"
  AND DATE(day_ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
'
```

Test `R1`, `R7`, and one outdoor-heavy residence.

### Measured (2026-06-04, after backfill)

| Query | Bytes (upper bound) |
|-------|---------------------|
| Old: fact + assignment join, R1 indoor 48h | 366,236,764 (~349 MiB) |
| Old: `residence_readings_hourly` view, R1 48h | 366,236,764 (~349 MiB) |
| New: `residence_hourly_by_residence`, R1 indoor 48h | 1,557,826 (~1.5 MiB) |
| New: `residence_hourly_by_residence`, R7 indoor 48h | 1,557,826 (~1.5 MiB) |
| New: `residence_hourly_by_residence`, R12 outdoor 48h | 1,817,101 (~1.7 MiB) |
| New: `residence_daily_by_residence`, R1 indoor 7d | 196,965 (~192 KiB) |

## Backfill (one-time / ops)

Tables populate per `@proc_date` when transformations run. To backfill history:

```bash
# GitHub Actions: Backfill Transformation Tables (workflow_dispatch)
# Or locally:
cd durham-environmental-monitoring
uv run python scripts/backfill_transformations.py \
  --project durham-weather-466502 \
  --dataset sensors \
  --start 2025-07-07 \
  --end $(date -u -d yesterday +%F) \
  --execute
```

Then sync to Grafana dataset if needed:

```bash
GCP_PROJECT_ID=durham-weather-466502 python scripts/sync_to_grafana.py
```

## Column reference

Same as `residence_readings_hourly` / `residence_readings_daily` views:

- `hour_ts` / `day_ts`
- `residence_id` (e.g. `R1` … `R13`)
- `sensor_name`, `sensor_role` (`Indoor` / `Outdoor`)
- `native_sensor_id`, `metric_name`
- `avg_value`, `min_value`, `max_value`, `samples`
