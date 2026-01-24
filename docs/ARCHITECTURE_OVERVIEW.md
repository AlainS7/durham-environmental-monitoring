# Durham Environmental Monitoring - Architecture Overview

## System Architecture

### Data Collection Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                        GITHUB ACTIONS                           │
│                  (.github/workflows/daily-ingest.yml)           │
│                                                                 │
│  Cron: 06:45 UTC daily                                         │
│  Trigger: schedule / workflow_dispatch                         │
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
│  • tsi_raw_materialized (1.3M rows, partitioned/clustered)    │
│  • wu_raw_materialized (31k rows)                             │
│                                                                 │
│  Dataset: sensors_shared (Grafana layer)                       │
│  • tsi_raw_view → sensors.tsi_raw_materialized                │
│  • tsi_raw_materialized (daily refresh from view)             │
│  • wu_raw_view (enriched with location/sensor_id)             │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             │ Query via BigQuery connector
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                         GRAFANA                                 │
│                                                                 │
│  Data Source: BigQuery (sensors_shared dataset)                │
│  Queries: Time series format (ts AS time, metric, value)      │
│  Dashboards: Air quality, weather trends                       │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. GitHub Actions (Daily Orchestrator)

**File:** [.github/workflows/daily-ingest.yml](.github/workflows/daily-ingest.yml)

- **Schedule:** 06:45 UTC daily (cron)
- **Manual Trigger:** workflow_dispatch with custom date ranges
- **Actions:**
  - Authenticate to GCP
  - Execute Cloud Run job `weather-data-uploader`
  - Optional: Rebuild/redeploy container image
  - Optional: Run backfill merge for date ranges
  - Optional: Data quality checks (freshness, staging presence)
  - Upload logs as artifacts

**Environment Variables:**
```bash
PROJECT_ID=durham-weather-466502
JOB_NAME=weather-data-uploader
REGION=us-east1
BQ_PROJECT=durham-weather-466502
BQ_DATASET=sensors
GCS_BUCKET=sensor-data-to-bigquery
```

### 2. Cloud Run Job (Data Collector)

**Name:** `weather-data-uploader`  
**Region:** `us-east1`  
**Container:** Built from [Dockerfile](../Dockerfile) via [cloudbuild-cr-job.yaml](../cloudbuild-cr-job.yaml)

**Runtime Behavior:**
- Accepts `--start` and `--end` date arguments
- Fetches data from TSI API and Weather Underground API
- Writes Parquet files to GCS with schema enforcement
- Loads Parquet → BigQuery external tables → MERGE into production tables

**Key Code:**
- Entry point: `src/daily_data_collector.py`
- GCS writer: `src/storage/gcs_uploader.py` (FLOAT64 coercion)
- BigQuery loader: `src/storage/bigquery_loader.py`

### 3. BigQuery (Data Warehouse)

**Project:** `durham-weather-466502`  
**Location:** `US`

#### Production Dataset: `sensors`

| Table | Type | Partitioning | Clustering | Rows | Date Range |
|-------|------|--------------|------------|------|------------|
| `tsi_raw_materialized` | Materialized | DATE(ts) | native_sensor_id | 1.3M | 2025-07-07 to 2025-11-16 |
| `wu_raw_materialized` | Materialized | DATE(ts) | - | 31k | 2025-07-07 to 2025-11-16 |
| `staging_tsi_YYYYMMDD` | Staging | - | - | Varies | Daily drops |
| `staging_wu_YYYYMMDD` | Staging | - | - | Varies | Daily drops |

#### Grafana Dataset: `sensors_shared`

| Object | Type | Definition |
|--------|------|------------|
| `tsi_raw_view` | View | `SELECT * FROM sensors.tsi_raw_materialized` |
| `tsi_raw_materialized` | Materialized | Refreshed daily from `tsi_raw_view` |
| `wu_raw_view` | View | Enriched WU data with location/sensor_id |

**Why Cross-Dataset Views?**
- Partition pruning preserved (no storage duplication)
- Grafana isolated from production schema changes
- Daily refresh ensures Grafana sees latest data

### 4. Storage Layer (GCS)

**Bucket:** `sensor-data-to-bigquery`  
**Region:** `US` (multi-region)

**Directory Structure:**
```
raw/
  tsi/
    2025-11-17/
      part-00000.parquet
      part-00001.parquet
  wu/
    2025-11-17/
      part-00000.parquet
```

**Schema Enforcement:** [src/storage/gcs_uploader.py](../src/storage/gcs_uploader.py)
- TSI numeric columns coerced to FLOAT64 before Parquet write
- WU numeric columns coerced to FLOAT64
- Prevents INT32 → FLOAT64 schema drift errors in BigQuery

## Oura Ring Integration

**Status:** **ISOLATED - NOT IN PRODUCTION PIPELINE**

**Location:** [oura-rings/](../oura-rings/) directory

**Files:**
- `oura_collector.py` - Standalone Python collector
- `cli.py` - CLI interface
- `oura_bigquery_loader.py` - Manual BigQuery upload

**No GitHub Actions Integration:** grep search confirmed no Oura references in workflows

**Recommendation:** Keep Oura separate for manual/exploratory use. If needed for production, create dedicated workflow.

## Data Gap & Backfill

### Current Status

**Gap Identified:** November 17, 2025 → January 21, 2026 (66 days)

**Last Data:**
- TSI: 2025-11-16 (1,319,879 rows)
- WU: 2025-11-16 (31,422 rows)

**Current Date:** 2026-01-22

### Backfill Process

**Script:** [scripts/backfill_catchup.sh](../scripts/backfill_catchup.sh)

**Fixed for macOS:** Cross-platform date command compatibility added

**Usage:**
```bash
bash scripts/backfill_catchup.sh
# Prompts: Continue? (y/N)
# Executes: gcloud run jobs execute for each day
# Logs: /tmp/backfill_YYYY-MM-DD.log
```

**Duration:** ~66 days × 5 seconds/day = ~5.5 minutes (with 3s delay between jobs)

**Post-Backfill:**
```bash
# 1. Refresh materialized table
bash scripts/refresh_tsi_shared.sh

# 2. Verify in BigQuery
bq query --nouse_legacy_sql \
  'SELECT MAX(DATE(ts)) FROM `durham-weather-466502.sensors.tsi_raw_materialized`'

# 3. Check Grafana dashboard
```

## Daily Automation

### Current Setup

**Method:** GitHub Actions workflow [daily-ingest.yml](.github/workflows/daily-ingest.yml)

**Schedule:** 06:45 UTC daily

**Workflow:**
1. Execute Cloud Run job for yesterday's data
2. Optional: Merge backfill if `backfill_merge=true`
3. Optional: Run data quality checks if `run_checks=true`
4. Create GitHub issue if monitoring fails (on schedule trigger only)
5. Upload logs as artifacts

### Alternative: Local Daily Script

**Script:** [scripts/daily_collection.sh](../scripts/daily_collection.sh)

**Fixed for macOS:** Date command compatibility added

**Usage:**
```bash
bash scripts/daily_collection.sh
# 1. Collects yesterday's data via Cloud Run
# 2. Refreshes sensors_shared.tsi_raw_materialized
# 3. Validates data freshness
```

**Cloud Scheduler (Optional):**
```bash
gcloud scheduler jobs create http daily-tsi-collection \
  --schedule="45 6 * * *" \
  --uri="https://github.com/AlainS7/durham-environmental-monitoring/actions/workflows/daily-ingest.yml/dispatches" \
  --http-method=POST \
  --oidc-service-account-email=<service-account>@durham-weather-466502.iam.gserviceaccount.com \
  --location=us-east1
```

**Recommendation:** Keep GitHub Actions as primary (free, logs visible, issue creation on failure)

## Grafana Setup

**Documentation:** [docs/GRAFANA_SETUP.md](GRAFANA_SETUP.md)

**Data Source:**
- Type: BigQuery
- Project: `durham-weather-466502`
- Dataset: `sensors_shared`
- Authentication: Service account JSON key

**Sample Query:**
```sql
SELECT
  ts AS time,
  native_sensor_id AS metric,
  pm2_5 AS value
FROM `durham-weather-466502.sensors_shared.tsi_raw_materialized`
WHERE
  DATE(ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
  AND pm2_5 IS NOT NULL
ORDER BY ts
```

**Dashboard Features:**
- Time series: PM2.5, PM10, temperature trends
- Heatmap: Sensor coverage by location
- Table: Latest readings per sensor

## Next Steps

### 1. Run Backfill (Immediate)

```bash
# Verify gcloud authentication
gcloud auth list

# Run backfill for 66 days
bash scripts/backfill_catchup.sh
# Type 'y' when prompted

# Wait ~5-10 minutes for completion

# Refresh Grafana table
bash scripts/refresh_tsi_shared.sh
```

### 2. Verify Data (Post-Backfill)

```bash
# Check latest TSI date
bq query --nouse_legacy_sql \
  'SELECT MAX(DATE(ts)) as latest_date, COUNT(*) as total_rows 
   FROM `durham-weather-466502.sensors.tsi_raw_materialized`'

# Expected: latest_date = 2026-01-21, total_rows ~1.7M

# Check Grafana table
bq query --nouse_legacy_sql \
  'SELECT MAX(DATE(ts)) as latest_date, COUNT(*) as total_rows 
   FROM `durham-weather-466502.sensors_shared.tsi_raw_materialized`'
```

### 3. Configure Grafana Dashboard

1. Add BigQuery data source (see [GRAFANA_SETUP.md](GRAFANA_SETUP.md))
2. Import sample queries
3. Create dashboards for:
   - PM2.5 time series by sensor
   - Temperature trends
   - Data freshness monitoring

### 4. Monitor Daily Automation

**GitHub Actions:**
- Check workflow runs: https://github.com/AlainS7/durham-environmental-monitoring/actions/workflows/daily-ingest.yml
- Review logs in "Artifacts" section
- Issues auto-created on failure (schedule trigger only)

**BigQuery:**
```sql
-- Check if today's data arrived
SELECT
  DATE(ts) as collection_date,
  COUNT(*) as rows
FROM `durham-weather-466502.sensors.tsi_raw_materialized`
WHERE DATE(ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY)
GROUP BY 1
ORDER BY 1 DESC
```

### 5. Optional Enhancements

- **Alerting:** Configure Cloud Monitoring alerts for job failures
- **Retention:** Set TTL for staging tables (auto-delete after 7 days)
- **Metrics:** Export pipeline metrics to Cloud Monitoring
- **Backups:** Enable BigQuery table snapshots for disaster recovery

## Troubleshooting

### Cloud Run Job Fails

```bash
# Check recent executions
gcloud run jobs executions list \
  --job=weather-data-uploader \
  --region=us-east1 \
  --project=durham-weather-466502 \
  --limit=5

# View logs for failed execution
gcloud logging read "resource.type=cloud_run_job 
  AND resource.labels.job_name=weather-data-uploader" \
  --limit=50 \
  --project=durham-weather-466502
```

### BigQuery Schema Errors

**Symptom:** "Schema mismatch: INT32 vs FLOAT64"

**Fix:** Already applied in `src/storage/gcs_uploader.py`
- All numeric sensor columns coerced to FLOAT64 before Parquet write
- Verify `TSI_NUMERIC_COLS` and `WU_NUMERIC_COLS` sets are complete

### Grafana Not Showing Data

**Check:**
1. BigQuery data source authentication (service account key)
2. Dataset access: `sensors_shared` must be visible
3. Query format: Ensure `ts AS time`, `native_sensor_id AS metric`, `value AS value`
4. Refresh materialized table: `bash scripts/refresh_tsi_shared.sh`

### macOS Date Command Errors

**Symptom:** "date: illegal option -- d"

**Fix:** Already applied in `scripts/backfill_catchup.sh` and `scripts/daily_collection.sh`
- Detects OS and uses appropriate date command (GNU vs BSD)
- Test: `bash scripts/backfill_catchup.sh <<< "N"`

## References

- [GRAFANA_SETUP.md](GRAFANA_SETUP.md) - Grafana configuration guide
- [DAILY_AUTOMATION.md](DAILY_AUTOMATION.md) - Automation setup details
- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) - Original architecture overview
- [TSI-Data-Quality-Monitoring.md](TSI-Data-Quality-Monitoring.md) - Data quality checks

## Contact

For issues or questions, create a GitHub issue or check the monitoring alerts in Cloud Console.
