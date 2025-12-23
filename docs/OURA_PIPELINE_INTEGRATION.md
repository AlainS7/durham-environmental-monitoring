# Oura Pipeline Integration Guide

## Overview

The Oura Ring data collection has been integrated into the main Durham Environmental Monitoring pipeline, running alongside the environmental sensor data collection.

## Pipeline Architecture

### Timeline (All times UTC)

```
05:00 UTC → Environmental Data Collection (TSI + WU)
07:25 UTC → Environmental Data Transformations
09:00 UTC → Oura Health Data Collection ⭐ NEW
```

### Why 09:00 UTC?

- Runs after environmental data is fully processed
- Gives time for all residents to sync their Oura data overnight
- Non-critical timing (health data updates less frequently than sensors)
- Avoids resource contention with high-priority environmental pipeline

## Automated Workflow

### Schedule

**Workflow:** `.github/workflows/oura-daily-collection.yml`
**Schedule:** 09:00 UTC daily (3:00 AM CST / 4:00 AM EST)
**Status:** ✅ AUTOMATED

### What It Does

1. **Authenticates** with GCP using GitHub Secrets
2. **Creates token files** from GitHub Secrets (OURA_PAT_R1-R14)
3. **Collects data** for all residents
4. **Exports to BigQuery** in dataset `oura`
5. **Tracks costs** and logs metrics
6. **Creates alerts** on failure

### Data Collected

For each resident, the following data types are collected:

| Data Type          | Table Name                      | Update Frequency | Records/Day |
| ------------------ | ------------------------------- | ---------------- | ----------- |
| Sleep              | `oura_daily_sleep`              | Daily            | ~1          |
| Activity           | `oura_daily_activity`           | Daily            | ~1          |
| Readiness          | `oura_daily_readiness`          | Daily            | ~1          |
| SpO2               | `oura_daily_spo2`               | Daily            | ~1          |
| Stress             | `oura_daily_stress`             | Daily            | ~1          |
| Cardiovascular Age | `oura_daily_cardiovascular_age` | Daily            | ~1          |
| Sleep Periods      | `oura_sleep_periods`            | Daily            | ~1–2        |
| Sessions           | `oura_sessions`                 | Event-based      | 0–2         |
| Workouts           | `oura_workouts`                 | Event-based      | 0–1         |
| Heart Rate (daily) | `oura_daily_heart_rate`         | Daily            | ~1          |

**Total:** ~100+ records/day (at least 10 residents × 10 tables; sessions/workouts vary)

## BigQuery Cost Tracking

### Real-Time Tracking

Every upload includes cost metrics:

```json
{
  "tables": {
    "oura_daily_sleep": 13,
    "oura_daily_activity": 13,
    ...
  },
  "cost_metrics": {
    "total_bytes_processed": 45678,
    "estimated_cost_usd": 0.000228
  }
}
```

### Historical Cost Analysis

Use the cost tracking script:

```bash
# View current month costs
python scripts/track_oura_costs.py --dataset oura

# Analyze specific date range
python scripts/track_oura_costs.py \
  --dataset oura \
  --start-date 2025-11-01 \
  --end-date 2025-11-07

# JSON output for automation
python scripts/track_oura_costs.py --dataset oura --json
```

### Expected Costs

**Storage:**

- ~6 tables × ~5 KB/row × 13 residents × 365 days = ~140 MB/year
- Cost: ~$0.003/month ($0.02 per GB/month)

**Queries:**

- Typical analysis: 1-2 queries/day × 100 MB scanned
- Cost: ~$0.015/month ($5 per TB)

**Total: ~$0.02/month** (negligible)

## Manual Operations

### Trigger Workflow Manually

1. Go to **Actions** → **Oura Daily Collection**
2. Click **Run workflow**
3. Configure options:
   - **residents**: Comma-separated (e.g., `1,2,3`) or `all`
   - **start_date**: Optional YYYY-MM-DD
   - **end_date**: Optional YYYY-MM-DD
   - **export_bq**: `true` to upload to BigQuery
   - **dry_run**: `true` to test without uploading

### Backfill Historical Data

```bash
# Test with one resident first (dry-run)
python -m oura-rings.cli \
  --residents 1 \
  --start-date 2025-10-01 \
  --end-date 2025-10-31 \
  --export-bq \
  --dry-run

# Run for all residents (real upload)
python -m oura-rings.cli \
  --residents 1 2 3 4 5 6 7 8 9 10 11 13 14 \
  --start-date 2025-10-01 \
  --end-date 2025-10-31 \
  --export-bq
```

### Check Pipeline Status

```bash
# View recent workflow runs
gh run list --workflow=oura-daily-collection.yml --limit 10

# View specific run details
gh run view <run-id>

# Download collection logs
gh run download <run-id> --name oura-collection-log
```

## Monitoring & Alerts

### Success Indicators

✅ Workflow completes successfully
✅ All residents collected
✅ ~78 records uploaded to BigQuery
✅ Cost metrics logged

### Failure Handling

When the scheduled run fails:

1. **GitHub Issue Created** automatically with:

   - Error details
   - Workflow run link
   - Troubleshooting steps
   - Quick fix commands

2. **Labels Applied:**
   - `automated-alert`
   - `oura-pipeline`
   - `data-collection`

### Common Issues

| Issue                      | Cause                         | Solution                        |
| -------------------------- | ----------------------------- | ------------------------------- |
| Token expired              | Oura PAT needs refresh        | Update GitHub Secret            |
| No data for resident       | Ring not synced               | Check Oura app sync             |
| BigQuery permission denied | Service account missing roles | Add `roles/bigquery.dataEditor` |
| Cost spike                 | Unusual query pattern         | Review with cost tracker        |

## Data Access

### BigQuery Queries

```sql
-- View latest sleep data for all residents
SELECT
  resident,
  day,
  sleep_score,
  deep_sleep,
  rem_sleep,
  efficiency
FROM `durham-weather-466502.oura.oura_daily_sleep`
ORDER BY day DESC, resident
LIMIT 100;

-- Average SpO2 by resident (last 7 days)
SELECT
  resident,
  AVG(spo2_average) as avg_spo2,
  AVG(breathing_disturbance_index) as avg_disturbance,
  COUNT(*) as days_measured
FROM `durham-weather-466502.oura.oura_daily_spo2`
WHERE day >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY resident
ORDER BY resident;

-- Stress patterns by day of week
SELECT
  FORMAT_DATE('%A', day) as day_of_week,
  AVG(stress_high) / 3600 as avg_stress_hours,
  AVG(recovery_high) / 3600 as avg_recovery_hours
FROM `durham-weather-466502.oura.oura_daily_stress`
GROUP BY day_of_week
ORDER BY
  CASE FORMAT_DATE('%A', day)
    WHEN 'Monday' THEN 1
    WHEN 'Tuesday' THEN 2
    WHEN 'Wednesday' THEN 3
    WHEN 'Thursday' THEN 4
    WHEN 'Friday' THEN 5
    WHEN 'Saturday' THEN 6
    WHEN 'Sunday' THEN 7
  END;
```

### Cross-Source Analysis

```sql
-- Correlate air quality with sleep quality
WITH daily_air_quality AS (
  SELECT
    DATE(timestamp) as day,
    AVG(pm25) as avg_pm25,
    AVG(pm10) as avg_pm10
  FROM `durham-weather-466502.sensors.sensor_readings_long`
  WHERE metric IN ('pm25', 'pm10')
  GROUP BY day
),
daily_sleep AS (
  SELECT
    day,
    AVG(sleep_score) as avg_sleep_score,
    AVG(efficiency) as avg_efficiency,
    COUNT(*) as num_residents
  FROM `durham-weather-466502.oura.oura_daily_sleep`
  GROUP BY day
)
SELECT
  s.day,
  s.avg_sleep_score,
  s.avg_efficiency,
  aq.avg_pm25,
  aq.avg_pm10,
  s.num_residents
FROM daily_sleep s
JOIN daily_air_quality aq ON s.day = aq.day
WHERE s.day >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
ORDER BY s.day DESC;
```

## Configuration

### GitHub Secrets Required

All tokens must be uploaded to GitHub Secrets:

```bash
# Upload all tokens at once
./scripts/add_github_secrets.sh
```

**Secrets:**

- `OURA_PAT_R1` through `OURA_PAT_R14` (excluding R12)
- `GCP_SA_KEY_JSON` (for BigQuery access)

### Environment Variables

Set in workflow or locally:

```bash
export BQ_PROJECT=durham-weather-466502
export BQ_LOCATION=US
export BQ_DATASET=oura
```

## Development & Testing

### Local Testing

```bash
# Activate virtual environment
source .venv/bin/activate

# Test with one resident (dry-run)
python -m oura-rings.cli \
  --residents 1 \
  --export-bq \
  --dry-run

# Check what would be uploaded
python test_bigquery_pipeline.py
```

### Cost Tracking During Development

```bash
# Check current costs before making changes
python scripts/track_oura_costs.py --dataset oura

# Make your changes...

# Verify costs haven't spiked
python scripts/track_oura_costs.py --dataset oura --json | \
  jq '.monthly_estimates.total_monthly_usd_estimated'
```

## Next Steps

### Phase 2: Additional Data Types (Future)

Not yet automated but available:

- `sleep_periods` - Detailed sleep stage transitions
- `workouts` - Exercise sessions
- `sessions` - Structured activities
- `heart_rate` - High-frequency time series (⚠️ high volume)

### Phase 3: Analysis Pipeline

1. Create dbt models for Oura data
2. Add data quality checks
3. Build correlation analysis views
4. Create Looker dashboards

### Phase 4: Research Applications

- Air quality impact on sleep
- Temperature correlation with stress
- Pollution effects on cardiovascular age
- Weather influence on activity levels

## Support

### Documentation

- **Main README**: `/README.md`
- **Oura Setup**: `/oura-rings/README.md`
- **System Architecture**: `/docs/SYSTEM_ARCHITECTURE.md`
- **BigQuery Guide**: `/oura-rings/BIGQUERY_UPDATE_COMPLETE.md`

### Troubleshooting

If you encounter issues:

1. Check workflow logs in GitHub Actions
2. Review cost metrics for anomalies
3. Verify token validity with test script
4. Check BigQuery table schemas
5. Create an issue with logs attached
