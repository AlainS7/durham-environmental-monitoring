# Sensor Calibration - Quick Reference

## Setup (One-time)

```bash
# 1. Create calibration config table
bash scripts/create_calibration_config.sh

# 2. Add your calibration rules (SQL)
INSERT INTO sensors.calibration_config
(native_sensor_id, metric_name, slope, intercept, effective_date, end_date, description, created_at)
VALUES
  ('curotklveott0jmp5agg', 'pm2_5', 0.95, 0.2, DATE('2025-11-17'), NULL, 'PM2.5 calibration', CURRENT_TIMESTAMP());

# 3. Backfill historical data
source .venv/bin/activate
python scripts/run_transformations_batch.sh 2025-07-01 2026-01-29

# 4. Refresh Grafana
bash scripts/refresh_tsi_shared.sh
```

## Calibration Formula

```
pm2_5_calibrated = (pm2_5_raw × slope) + intercept
```

## Query Calibrated Data

```sql
SELECT timestamp, native_sensor_id, value
FROM sensor_readings_hourly
WHERE metric_name = 'pm2_5_calibrated'
AND native_sensor_id = 'curotklveott0jmp5agg'
```

## Manage Rules

### Add new calibration

```sql
INSERT INTO calibration_config
(native_sensor_id, metric_name, slope, intercept, effective_date, end_date, description, created_at)
VALUES ('sensor_id', 'pm2_5', 0.9, 0.5, DATE('2026-01-29'), NULL, 'Description', CURRENT_TIMESTAMP());
```

### View active rules

```sql
SELECT * FROM calibration_config
WHERE effective_date <= CURRENT_DATE()
AND (end_date IS NULL OR end_date >= CURRENT_DATE())
```

### Update existing rule

```sql
UPDATE calibration_config
SET slope = 0.92, intercept = 0.3
WHERE native_sensor_id = 'sensor_id' AND metric_name = 'pm2_5';
-- Then re-run: python scripts/run_transformations_batch.sh DATE1 DATE2
```

### Expire a rule

```sql
UPDATE calibration_config
SET end_date = DATE('2026-01-28')
WHERE native_sensor_id = 'sensor_id' AND metric_name = 'pm2_5';
```

## In Grafana

- Query: `metric_name = 'pm2_5_calibrated'`
- Compare: Run query with both `pm2_5` (raw) and `pm2_5_calibrated` side-by-side
- No other changes needed - automatically includes calibrated metrics

## Backfill Time Estimates

- 7 days: ~2 minutes
- 30 days: ~8 minutes
- 90 days: ~20 minutes
- 200 days: ~40 minutes

## Cost

- One-time setup & backfill: ~$0.50
- Ongoing: No additional cost (same pipeline)

## Files Modified

- `transformations/sql/01_sensor_readings_long.sql` - Added calibration logic
- `scripts/create_calibration_config.sh` - Create config table
- `docs/SENSOR_CALIBRATION_GUIDE.md` - Full documentation
