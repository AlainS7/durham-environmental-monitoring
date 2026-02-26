# Daily Data Collection & Grafana Update Setup

## Overview

This guide sets up automated daily data collection for TSI and WU sensors, ensuring Grafana always shows fresh data.

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

## Daily Automation Setup

### Option A: Cloud Scheduler (Recommended for Production)

#### 1. Create Cloud Scheduler Job

```bash
gcloud scheduler jobs create http tsi-wu-daily-collection \
  --project=durham-weather-466502 \
  --location=us-east1 \
  --schedule="0 2 * * *" \
  --time-zone="America/New_York" \
  --uri="https://YOUR-CLOUD-RUN-URL/collect" \
  --http-method=POST \
  --message-body='{"start":"yesterday","end":"yesterday"}' \
  --oidc-service-account-email=SCHEDULER_SA@durham-weather-466502.iam.gserviceaccount.com \
  --attempt-deadline=1800s
```

**Note**: Replace `YOUR-CLOUD-RUN-URL` with your actual Cloud Run service URL.

#### 2. Set Up TSI Refresh (after collection)

```bash
gcloud scheduler jobs create http tsi-refresh-daily \
  --project=durham-weather-466502 \
  --location=us-east1 \
  --schedule="0 3 * * *" \
  --time-zone="America/New_York" \
  --uri="https://YOUR-CLOUD-RUN-URL/refresh" \
  --http-method=POST \
  --oidc-service-account-email=SCHEDULER_SA@durham-weather-466502.iam.gserviceaccount.com
```

**Schedule**: Runs at 3 AM (1 hour after collection).

---

### Option B: Cron Job (Local/VM)

Add to crontab (`crontab -e`):

```cron
# Daily data collection at 2 AM ET
0 2 * * * cd /Users/Projects/Developer/work/github.com/AlainS7/durham-environmental-monitoring && bash scripts/daily_collection.sh >> /tmp/daily_collection.log 2>&1
```

---

### Option C: Manual Daily Run

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

### Check Daily Updates

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
- **Materialized table**: Refreshing daily costs ~$0.01/day (1.3M rows × $5/TB)
- **View queries**: Free if under 1TB scanned/month

### Cloud Run Job Costs

- ~$0.05 per day (3 minutes runtime × $0.00002400/vCPU-second)
- Backfill: ~$3.50 one-time (67 days × $0.05)

---

## Next Steps

1. Run backfill: `bash scripts/backfill_catchup.sh`
2. Verify Grafana queries work (see [GRAFANA_SETUP.md](GRAFANA_SETUP.md))
3. Set up Cloud Scheduler or cron for daily automation
4. Add data freshness monitoring panel to Grafana
5. Optional: Set up alerts via Grafana or Cloud Monitoring
