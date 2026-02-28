# Sensor Calibration Implementation Guide

**Date**: January 29, 2026  
**Status**: ✅ Implementation Ready

---

## Overview

You now have a full calibration system in place that:

- ✅ Keeps raw sensor data untouched (data lineage preserved)
- ✅ Applies calibration transformations in the pipeline (step 1)
- ✅ Uses a lookup table for easy management
- ✅ Automatically flows through to hourly/daily summaries
- ✅ Works with Grafana without additional changes

---

## How It Works

### Architecture

```
tsi_raw_materialized (raw data)
         ↓
calibration_config (lookup table)
         ↓
01_sensor_readings_long.sql (applies calibration formula)
         ↓
sensor_readings_long (raw + calibrated metrics)
         ↓
02_hourly_summary.sql (aggregates)
         ↓
sensor_readings_hourly
         ↓
Grafana (queries with metric_name='pm2_5_calibrated')
```

### Calibration Formula

For each sensor, the calibration applies:

```
pm2_5_calibrated = (pm2_5_raw × slope) + intercept
```

**Example**: If sensor `d14rfblfk2973f196c5g` has:

- slope = 0.91
- intercept = 0.5

Then for a raw reading of PM2.5 = 20 μg/m³:

```
pm2_5_calibrated = (20 × 0.91) + 0.5 = 18.7 + 0.5 = 19.2 μg/m³
```

---

## Setup Steps

### Step 1: Create the Calibration Config Table

```bash
bash scripts/create_calibration_config.sh
```

This creates table `sensors.calibration_config` with:

- `native_sensor_id` (string)
- `metric_name` (string, e.g., 'pm2_5')
- `slope` (float, multiply factor)
- `intercept` (float, offset)
- `effective_date` (date, when rule applies from)
- `end_date` (date, when rule expires - NULL = ongoing)
- `description` (text notes)

### Step 2: Add Your Calibration Rules

Insert calibration rules into the table:

```sql
INSERT INTO `durham-weather-466502.sensors.calibration_config`
(native_sensor_id, metric_name, slope, intercept, effective_date, end_date, description, created_at)
VALUES
  -- Example: Sensor that drifted starting Nov 17
  ('curotklveott0jmp5agg', 'pm2_5', 0.95, 0.2, DATE('2025-11-17'), NULL, 'PM2.5 calibration after drift', CURRENT_TIMESTAMP()),

  -- Example: Different calibration for a specific date range
  ('curp515veott0jmp5ajg', 'pm2_5', 0.88, 1.0, DATE('2025-11-17'), DATE('2025-12-31'), 'Temporary humidity bias correction', CURRENT_TIMESTAMP()),

  -- You can have multiple metrics per sensor
  ('d10a64s5n0vb5ljnncig', 'no2_ppb', 1.05, 0.0, DATE('2025-11-01'), NULL, 'NOx sensor gain adjustment', CURRENT_TIMESTAMP());
```

### Step 3: Backfill Historical Data

```bash
# Activate venv
source .venv/bin/activate

# Run transformations for date range
python scripts/run_transformations_batch.sh 2025-07-01 2026-01-29
```

This will:

1. Delete sensor_readings_long for those dates
2. Re-apply calibration using current rules
3. Regenerate hourly/daily summaries
4. Update views

**Time estimate**: ~30 minutes for 200 days

### Step 4: Refresh Grafana Dataset

```bash
bash scripts/refresh_tsi_shared.sh
```

This syncs the Grafana dataset with calibrated data.

---

## Using Calibrated Data in Grafana

### Query Calibrated PM2.5

```sql
SELECT
  timestamp,
  native_sensor_id,
  value as pm2_5_calibrated
FROM `durham-weather-466502.sensors_shared.sensor_readings_hourly`
WHERE metric_name = 'pm2_5_calibrated'
  AND native_sensor_id = 'curotklveott0jmp5agg'
  AND DATE(timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
ORDER BY timestamp DESC
```

### Create a Grafana Panel

1. **Data Source**: BigQuery (`durham-weather-466502`)
2. **Query**:

```sql
SELECT $__time(timestamp), value
FROM sensor_readings_hourly
WHERE metric_name = 'pm2_5_calibrated'
  AND native_sensor_id = '$sensor_id'
```

3. **Variables**: `$sensor_id` (select from dropdown)
4. **Display**: Time series chart

### Compare Raw vs Calibrated

```sql
SELECT
  DATE_TRUNC(timestamp, HOUR) as hour,
  native_sensor_id,
  SUM(CASE WHEN metric_name = 'pm2_5' THEN value ELSE 0 END) / COUNT(DISTINCT CASE WHEN metric_name = 'pm2_5' THEN 1 END) as raw_avg,
  SUM(CASE WHEN metric_name = 'pm2_5_calibrated' THEN value ELSE 0 END) / COUNT(DISTINCT CASE WHEN metric_name = 'pm2_5_calibrated' THEN 1 END) as calibrated_avg,
  ROUND(
    (SUM(CASE WHEN metric_name = 'pm2_5_calibrated' THEN value ELSE 0 END) / COUNT(DISTINCT CASE WHEN metric_name = 'pm2_5_calibrated' THEN 1 END)) -
    (SUM(CASE WHEN metric_name = 'pm2_5' THEN value ELSE 0 END) / COUNT(DISTINCT CASE WHEN metric_name = 'pm2_5' THEN 1 END)),
    2
  ) as difference_ug_m3
FROM sensor_readings_hourly
WHERE native_sensor_id IN ('curotklveott0jmp5agg', 'curp515veott0jmp5ajg')
  AND DATE(timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY hour, native_sensor_id
ORDER BY hour DESC
```

---

## Managing Calibration Rules

### Add a New Sensor Calibration

```sql
INSERT INTO calibration_config
(native_sensor_id, metric_name, slope, intercept, effective_date, end_date, description, created_at)
VALUES (
  'd1ok78tlveq94soark30',  -- sensor ID
  'pm2_5',                 -- metric
  0.92,                    -- slope
  0.3,                     -- intercept
  DATE('2026-01-29'),      -- effective from today
  NULL,                    -- no end date = ongoing
  'Humidity-corrected PM2.5',
  CURRENT_TIMESTAMP()
);
```

### Update Existing Calibration

**Option A: Change the rule (affects all historical data)**

```sql
UPDATE calibration_config
SET slope = 0.93,
    intercept = 0.4,
    description = 'Updated after lab recalibration'
WHERE native_sensor_id = 'd14rfblfk2973f196c5g'
  AND metric_name = 'pm2_5'
  AND effective_date = DATE('2025-01-01');

-- Then backfill affected dates:
python scripts/run_transformations_batch.sh 2025-01-01 2026-01-29
```

**Option B: Create a new rule with new effective date (keeps history)**

```sql
INSERT INTO calibration_config
(native_sensor_id, metric_name, slope, intercept, effective_date, end_date, description, created_at)
VALUES (
  'd14rfblfk2973f196c5g',
  'pm2_5',
  0.93,     -- new slope
  0.4,      -- new intercept
  DATE('2026-01-15'),  -- effective from this date
  NULL,
  'Post-maintenance recalibration',
  CURRENT_TIMESTAMP()
);

-- Then only backfill from Jan 15 onwards:
python scripts/run_transformations_batch.sh 2026-01-15 2026-01-29
```

### Expire a Calibration Rule

```sql
UPDATE calibration_config
SET end_date = DATE('2026-01-14')
WHERE native_sensor_id = 'd14rfblfk2973f196c5g'
  AND metric_name = 'pm2_5'
  AND effective_date = DATE('2025-01-01');

-- Then re-run that date range to apply new/default rules
python scripts/run_transformations_batch.sh 2026-01-14 2026-01-29
```

### Query Current Active Rules

```sql
SELECT
  native_sensor_id,
  metric_name,
  slope,
  intercept,
  effective_date,
  end_date,
  description
FROM calibration_config
WHERE effective_date <= CURRENT_DATE()
  AND (end_date IS NULL OR end_date >= CURRENT_DATE())
ORDER BY native_sensor_id, metric_name, effective_date DESC;
```

---

## Data Lineage & Auditing

### See Which Calibration Was Applied to a Row

```sql
SELECT
  sl.timestamp,
  sl.native_sensor_id,
  sl.metric_name,
  sl.value,
  cc.slope,
  cc.intercept,
  cc.effective_date,
  cc.description
FROM sensor_readings_long sl
LEFT JOIN calibration_config cc
  ON sl.native_sensor_id = cc.native_sensor_id
  AND cc.metric_name = 'pm2_5'
  AND DATE(sl.timestamp) >= cc.effective_date
  AND (cc.end_date IS NULL OR DATE(sl.timestamp) <= cc.end_date)
WHERE sl.native_sensor_id = 'd14rfblfk2973f196c5g'
  AND sl.metric_name = 'pm2_5_calibrated'
  AND DATE(sl.timestamp) = '2025-11-20'
LIMIT 100;
```

---

## Troubleshooting

### Calibrated values look wrong

**Check 1: Verify calibration rule exists**

```sql
SELECT * FROM calibration_config
WHERE native_sensor_id = 'YOUR_SENSOR_ID'
  AND effective_date <= CURRENT_DATE()
  AND (end_date IS NULL OR end_date >= CURRENT_DATE());
```

**Check 2: Verify transformation ran**

```sql
-- Check if pm2_5_calibrated metric exists
SELECT DISTINCT metric_name
FROM sensor_readings_long
WHERE native_sensor_id = 'YOUR_SENSOR_ID'
ORDER BY metric_name;
```

**Check 3: Manual calculation**

```sql
SELECT
  CAST(pm2_5 AS FLOAT64) as raw,
  CAST(pm2_5 AS FLOAT64) * 0.91 + 0.5 as expected_calibrated,
  (SELECT value FROM sensor_readings_long src2
   WHERE src2.timestamp = src1.timestamp
   AND src2.native_sensor_id = src1.native_sensor_id
   AND src2.metric_name = 'pm2_5_calibrated') as actual_calibrated
FROM sensor_readings_long src1
WHERE src1.native_sensor_id = 'YOUR_SENSOR_ID'
  AND src1.metric_name = 'pm2_5'
  AND DATE(src1.timestamp) = '2025-11-20'
LIMIT 5;
```

### Backfill is slow

- Backfill processes one date at a time
- For 200 days: ~30-40 minutes
- If stuck, check: `bq ls -j | head -5` for running jobs
- Kill stuck job: `bq kill JOB_ID`

### Grafana still shows old data

1. Verify refresh completed: Check `sensor_readings_hourly` has `pm2_5_calibrated` rows
2. Manually refresh Grafana: Dashboard → Refresh (Ctrl+Shift+R)
3. Clear Grafana cache: Settings → Data Sources → BigQuery → Clear Cache
4. Re-run: `bash scripts/refresh_tsi_shared.sh`

---

## Performance Considerations

### Query Speed

- **Raw + Calibrated side-by-side**: ~2-3 seconds (reads 2 metric_name values)
- **Calibrated only**: ~1 second (reads 1 metric_name value)
- **By sensor**: Add `AND native_sensor_id = ?` to speed up 10x

### Storage Impact

- Original: `sensor_readings_long` with N metrics per sensor
- After calibration: N+1 metrics (new `pm2_5_calibrated` added)
- **Impact**: +1-2% table size (one new column per row)

### Cost Impact

- One-time backfill: ~$0.50 (200 days of transformations)
- Ongoing: No additional cost (same transformation pipeline)
- Querying: Slightly higher (reading 2 metrics instead of 1) but negligible

---

## Next Steps

1. ✅ **Identify sensors needing calibration**
   - Document which sensors and what calibration values

2. ✅ **Add rules to calibration_config**

   ```bash
   source .venv/bin/activate
   bq query --project_id=durham-weather-466502 --nouse_legacy_sql \
     < INSERT_YOUR_RULES_HERE.sql
   ```

3. ✅ **Run backfill**

   ```bash
   source .venv/bin/activate
   python scripts/run_transformations_batch.sh 2025-07-01 2026-01-29
   ```

4. ✅ **Test in Grafana**
   - Create panel with `metric_name = 'pm2_5_calibrated'`
   - Compare with raw values
   - Verify calibration is correct

5. ✅ **Monitor going forward**
   - Daily transformations automatically apply current rules
   - Add new rules as sensors drift/age
   - Keep documentation of why each calibration exists
