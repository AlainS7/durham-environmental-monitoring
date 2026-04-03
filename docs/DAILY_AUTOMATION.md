# Daily Automation Schedule & Flow

This document details the exact schedules, commands, and data paths for the automated daily ingestion pipeline. For the high-level system architecture, see [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md).

## 1. Daily Ingestion Pipeline Flow

The core ingestion runs hourly. Below is the detailed trace of how a single run executes and where the data lands:

```text
┌─────────────────────────────────────────────────────────────────┐
│              GITHUB ACTIONS / CLOUD SCHEDULER                   │
│                                                                 │
│  Cron: Hourly (05 * * * *)                                     │
│  Trigger: schedule / workflow_dispatch / HTTP POST             │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ gcloud run jobs execute
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CLOUD RUN JOB                              │
│                  (weather-data-uploader)                        │
│                                                                 │
│  Region: us-east1                                              │
│  Container: weather-data-uploader:latest                       │
│  Runtime: Executes src/collectors/* Python code                │
│                                                                 │
│  Sources:                                                      │
│  • Triangle Sensors (TSI API)                                  │
│  • Weather Underground (WU API)                                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ Write Parquet files
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GOOGLE CLOUD STORAGE                         │
│                                                                 │
│  Bucket: sensor-data-to-bigquery                               │
│  Path: raw/{source}/{date}/                                    │
│                                                                 │
│  Schema: FLOAT64 enforcement via gcs_uploader.py               │
│  • TSI_NUMERIC_COLS: pm2_5, pm10, temperature, etc.           │
│  • WU_NUMERIC_COLS: temperature, humidity, etc.               │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ Load as external table → MERGE
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        BIGQUERY                                 │
│                  (durham-weather-466502)                        │
│                                                                 │
│  Dataset: sensors (production)                                 │
│  • staging_tsi_{YYYYMMDD} (temporary)                          │
│  • tsi_raw_materialized (Partitioned on DATE(ts))              │
└─────────────────────────────────────────────────────────────────┘
```

## 2. Secondary Schedules

Once the raw data is landed by the pipeline above, secondary automated workflows run to process and serve the data:

| Workflow / Tool                 | Trigger / Schedule                                                           | Purpose                                                                                                     |
| ------------------------------- | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `daily-ingest.yml`              | `5 * * * *`                                                                  | Ingests raw data and runs merge/check for the current-day fast lane (scheduled runs), with manual date overrides available. |
| `daily-merge.yml`               | `10 7 * * *`                                                                 | Merges yesterday staged partitions into consolidated production tables.                                     |
| `transformations-execute.yml`   | `25 07 * * *` (stable lane) + `40 * * * *` (fast lane) + manual (`workflow_dispatch`) | Rebuilds transformed partitions for intraday freshness while keeping a dedicated daily stabilization run. |
| `daily-refresh-shared.yml`      | `45 * * * *`                                                                 | Refreshes Grafana-facing shared tables and runs residence parity check.                                     |
| `metric-coverage.yml`           | `5 8 * * *` + `workflow_run` after `Execute Transformations` (success/main)  | Validates transformed metric coverage and raises SLA alerts on streaks.                                     |
| `row-count-threshold.yml`       | `15 8 * * *` + `workflow_run` after `Execute Transformations` (success/main) | Validates key table row thresholds and raises SLA alerts on streaks.                                        |
| `data-freshness.yml`            | `35 8 * * *` + `workflow_run` after `Daily Refresh Shared Tables (Grafana)`  | Runs freshness + prod/shared residence parity checks with final fail gate.                                  |
| `weekly-self-heal-backfill.yml` | `20 9 * * 0` (Sunday)                                                        | Re-merges + re-transforms recent days and syncs shared tables to self-heal.                                 |
| `sync-to-sharepoint.yml`        | Manual (`workflow_dispatch`)                                                 | Bundles recent data and pushes to external researchers.                                                     |

### Concurrency guardrails

Workflows use GitHub Actions `concurrency` to prevent overlapping runs for the same branch.

- `group` defines which runs are mutually exclusive (for example, `prod-data-pipeline-${{ github.ref }}`).
- `cancel-in-progress: false` means new runs **queue** instead of canceling active runs.

This protects shared tables from concurrent writes and keeps execution order deterministic.

---

## 3. Quick Start (Run Backfill First)

If the pipeline has been paused or you are deploying to a fresh environment, run a backfill before relying on the automation.

### A. Backfill Missing Data (Nov 17, 2025 → Current)

```bash
cd /Users/Projects/Developer/work/[github.com/AlainS7/durham-environmental-monitoring](https://github.com/AlainS7/durham-environmental-monitoring)
bash scripts/backfill_catchup.sh
```

This will:

- Collect data for all missing days (~67 days)
- Take ~3-4 hours (3 seconds per day + API time)
- Log progress to `/tmp/backfill_YYYY-MM-DD.log`

### B. Refresh Materialized Table

```bash
bash scripts/refresh_tsi_shared.sh
```

### C. Verify Data in BigQuery

```bash
bq query --nouse_legacy_sql "
SELECT 'TSI' AS source, COUNT(*) AS rows, MAX(DATE(ts)) AS latest_date
FROM \`durham-weather-466502.sensors_shared.tsi_raw_materialized\`
UNION ALL
SELECT 'WU' AS source, COUNT(*) AS rows, MAX(DATE(ts)) AS latest_date
FROM \`durham-weather-466502.sensors_shared.wu_raw_materialized\`"
```

Expected output: `latest_date` should be yesterday or today.

---

## 4. Automation Setup (Primary & Alternatives)

### Option A: GitHub Actions (Primary)

The preferred method is to allow `.github/workflows/daily-ingest.yml` to trigger the Cloud Run job on its predefined cron schedule. This ensures logs are visible in the repository and provides automatic issue creation on failure.

### Option B: Cloud Scheduler (Production Alternative)

If you prefer GCP-native scheduling over GitHub Actions:

```bash
gcloud scheduler jobs create http daily-data-collection-trigger \
  --project=durham-weather-466502 \
  --location=us-east1 \
  --schedule="0 * * * *" \
  --time-zone="America/New_York" \
  --uri="[https://run.googleapis.com/v2/projects/durham-weather-466502/locations/us-east1/jobs/weather-data-uploader:run](https://run.googleapis.com/v2/projects/durham-weather-466502/locations/us-east1/jobs/weather-data-uploader:run)" \
  --http-method=POST \
  --message-body='{}' \
  --headers="Content-Type=application/json" \
  --oauth-service-account-email=github-actions-deployer@durham-weather-466502.iam.gserviceaccount.com \
  --oauth-token-scope="[https://www.googleapis.com/auth/cloud-platform](https://www.googleapis.com/auth/cloud-platform)" \
  --attempt-deadline=1800s
```

_(If the job already exists, use `gcloud scheduler jobs update http ...` with the same flags.)_

### Option C: Cron Job (Local/VM)

Add to crontab (`crontab -e`):

```cron
# Hourly
0 * * * * cd /Users/Projects/Developer/work/[github.com/AlainS7/durham-environmental-monitoring](https://github.com/AlainS7/durham-environmental-monitoring) && bash scripts/daily_collection.sh >> /tmp/daily_collection.log 2>&1
```

### Option D: Manual Run

To manually force an ingestion run for yesterday's data without waiting for a schedule:

```bash
bash scripts/daily_collection.sh
```

Or execute the Cloud Run job directly:

```bash
gcloud run jobs execute weather-data-uploader \
  --region=us-east1 \
  --project=durham-weather-466502 \
  --args="src/data_collection/daily_data_collector.py" \
  --args="--start=$(date -u -d yesterday +%F)" \
  --args="--end=$(date -u -d yesterday +%F)" \
  --wait
```

---

## 5. Verification & Monitoring

### Grafana Data Freshness Panel

Add this query to your Grafana dashboard to monitor freshness and ensure the automated runs are succeeding:

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
FROM `durham-weather-466502.sensors_shared.wu_raw_materialized`
```

**Alert recommendation:** Set an alert threshold for `days_behind > 1`.

---

## 6. Troubleshooting

### Data Not Updating in Grafana

1. Check BigQuery has new data:
   ```bash
   bq query --nouse_legacy_sql "SELECT MAX(ts) FROM \`durham-weather-466502.sensors_shared.tsi_raw_materialized\`"
   ```
2. Refresh Grafana dashboard (browser refresh or click refresh icon).
3. Check Grafana time range (ensure it is not set to static dates).
4. Verify partition pruning works:
   ```sql
   -- Add this WHERE clause to all custom queries
   WHERE ts >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
   ```

### Cloud Run Job Fails

Check the execution logs directly in GCP:

```bash
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=weather-data-uploader" \
  --project=durham-weather-466502 \
  --limit=50 \
  --format=json
```

### Backfill Takes Too Long

- Run in batches (1 week at a time).
- Increase `--wait` timeout if jobs timeout.
- Check API quotas/limits for WU and TSI.

---

## 7. Cost Optimization

### BigQuery Costs

- **Partition pruning**: Always filter on `ts` column.
- **Clustering**: Queries filtering on `native_sensor_id` are faster/cheaper.
- **Fast-lane transforms**: Rebuilding only the current partition intraday keeps hourly refresh feasible and cost-bounded.
- **Materialized/shared refresh**: Hourly refresh remains low-cost at current scale in this project.
- **View queries**: Free if under 1TB scanned/month.

### Cloud Run Job Costs

- Cost scales roughly linearly with run frequency; hourly cadence is typically still modest at current workload, but verify with Billing export.
- Backfill: ~$3.50 one-time (67 days × $0.05).
