# Daily Data Collection & Grafana Update Setup

## Overview

This guide sets up automated scheduled data collection for TSI and WU sensors, with a recommended 6-hour cadence for fresher Grafana monitoring.

---

## Quick Start (Run Backfill First)

### 1. Backfill Missing Data (Nov 17, 2025 → Current)

```bash
cd /Users/Projects/Developer/work/github.com/AlainS7/durham-environmental-monitoring
bash scripts/backfill_catchup.sh
```

This will:

- Collect data for all missing days (~67 days)
- Take ~3-4 hours (3 seconds per day + API time)
- Log progress to `/tmp/backfill_YYYY-MM-DD.log`

### 2. Refresh Materialized Table

```bash
bash scripts/refresh_tsi_shared.sh
```

### 3. Verify Data in BigQuery

```bash
bq query --nouse_legacy_sql "
SELECT 'TSI' AS source, COUNT(*) AS rows, MAX(DATE(ts)) AS latest_date
FROM \`durham-weather-466502.sensors_shared.tsi_raw_materialized\`
UNION ALL
SELECT 'WU' AS source, COUNT(*) AS rows, MAX(DATE(ts)) AS latest_date
FROM \`durham-weather-466502.sensors_shared.wu_raw_view\`"
```

Expected output: `latest_date` should be yesterday or today.

---

## Automation Setup (Recommended: Every 6 Hours)

### Option A: Cloud Scheduler (Production)

#### 1. Create or Update Cloud Scheduler Job (Cloud Run Jobs API)

```bash
gcloud scheduler jobs create http daily-data-collection-trigger \
  --project=durham-weather-466502 \
  --location=us-east1 \
  --schedule="0 */6 * * *" \
  --time-zone="America/New_York" \
  --uri="https://run.googleapis.com/v2/projects/durham-weather-466502/locations/us-east1/jobs/weather-data-uploader:run" \
  --http-method=POST \
  --message-body='{}' \
  --headers="Content-Type=application/json" \
  --oauth-service-account-email=github-actions-deployer@durham-weather-466502.iam.gserviceaccount.com \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --attempt-deadline=1800s
```

If the job already exists, use `gcloud scheduler jobs update http ...` with the same flags.

#### 2. Refresh shared Grafana tables via GitHub Actions

```bash
Workflow: `.github/workflows/daily-refresh-shared.yml`
- Recommended schedule: every 6 hours (staggered after ingestion).
- Current default in repo: `45 */6 * * *`.
```

**Rollback to daily mode**: set cron back to `45 6 * * *` (ingest) and `0 1 * * *` (shared refresh).

---

### Option B: Cron Job (Local/VM)

Add to crontab (`crontab -e`):

```cron
# Every 6 hours
0 */6 * * * cd /Users/Projects/Developer/work/github.com/AlainS7/durham-environmental-monitoring && bash scripts/daily_collection.sh >> /tmp/daily_collection.log 2>&1
```

---

### Option C: Manual Run

Run this command each day:

```bash
bash scripts/daily_collection.sh
```

Or just collect data (without refresh):

```bash
gcloud run jobs execute weather-data-uploader \
  --region=us-east1 \
  --project=durham-weather-466502 \
  --args="--start=$(date -u -d yesterday +%F)","--end=$(date -u -d yesterday +%F)" \
  --wait
```

---

## Verification & Monitoring

### Check Update Freshness

```bash
# Run this each morning to verify yesterday's data loaded
bash scripts/daily_collection.sh
```

### Grafana Data Freshness Panel

Add this query to your Grafana dashboard to monitor freshness:

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

Set alert threshold: `days_behind > 1`

---

## Troubleshooting

### Data Not Updating in Grafana

1. Check BigQuery has new data:

   ```bash
   bq query --nouse_legacy_sql "SELECT MAX(ts) FROM \`durham-weather-466502.sensors_shared.tsi_raw_materialized\`"
   ```

2. Refresh Grafana dashboard (browser refresh or click refresh icon)

3. Check Grafana time range (not set to static dates)

4. Verify partition pruning works:
   ```sql
   -- Add this WHERE clause to all queries
   WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
   ```

### Cloud Run Job Fails

```bash
# Check job logs
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=weather-data-uploader" \
  --project=durham-weather-466502 \
  --limit=50 \
  --format=json
```

### Backfill Takes Too Long

- Run in batches (1 week at a time)
- Increase `--wait` timeout if jobs timeout
- Check API quotas/limits for WU and TSI

---

## Cost Optimization

### BigQuery Costs

- **Partition pruning**: Always filter on `ts` column
- **Clustering**: Queries filtering on `native_sensor_id` are faster/cheaper
- **Materialized table**: Refreshing every 6 hours is still low-cost (~$0.42/month observed scale)
- **View queries**: Free if under 1TB scanned/month

### Cloud Run Job Costs

- ~$0.05 per day (3 minutes runtime × $0.00002400/vCPU-second)
- Backfill: ~$3.50 one-time (67 days × $0.05)

---

## Next Steps

1. Run backfill: `bash scripts/backfill_catchup.sh`
2. Verify Grafana queries work (see [GRAFANA_SETUP.md](GRAFANA_SETUP.md))
3. Set up Cloud Scheduler or cron for 6-hour automation
4. Add data freshness monitoring panel to Grafana
5. Optional: Set up alerts via Grafana or Cloud Monitoring
