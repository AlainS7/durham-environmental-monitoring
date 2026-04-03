# Durham Environmental Monitoring - Operations Runbook

This runbook is the reproducible companion to [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md). Use it for local setup, one-off runs, backfills, shared-table refreshes, and pipeline verification.

## Prerequisites

- Python 3.11 recommended
- `gcloud` configured for the target GCP project
- `bq` CLI available
- access to the required BigQuery datasets, GCS bucket, Cloud Run job, and Secret Manager secrets
- local `.env` populated from `.env.example` when running scripts outside GitHub Actions

## Environment

Most scripts and workflows assume these values or equivalents:

```bash
export GCP_PROJECT_ID=durham-weather-466502
export PROJECT_ID="$GCP_PROJECT_ID"
export BQ_PROJECT="$GCP_PROJECT_ID"
export BQ_DATASET=sensors
export BQ_SHARED_DATASET=sensors_shared
export REGION=us-east1
export JOB_NAME=weather-data-uploader
export GCS_BUCKET=sensor-data-to-bigquery
```

Authenticate before running cloud operations:

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project "$GCP_PROJECT_ID"
```

## Reproducible Paths

### Option A: Reproduce the pipeline through GitHub Actions

This is the best path when you want parity with production orchestration.

1. Run [`.github/workflows/daily-ingest.yml`](../.github/workflows/daily-ingest.yml) with `workflow_dispatch`.
2. Supply either `date` or `start_date` plus `end_date`.
3. Leave `backfill_merge=true` and `run_checks=true` unless you are isolating a failure.
4. Run [`.github/workflows/daily-refresh-shared.yml`](../.github/workflows/daily-refresh-shared.yml) if you need Grafana-facing tables refreshed immediately.
5. Run [`.github/workflows/transformations-execute.yml`](../.github/workflows/transformations-execute.yml) to force an immediate transformed-table refresh window (intraday fast lane).
6. Run [`.github/workflows/data-freshness.yml`](../.github/workflows/data-freshness.yml), [`.github/workflows/row-count-threshold.yml`](../.github/workflows/row-count-threshold.yml), or [`.github/workflows/metric-coverage.yml`](../.github/workflows/metric-coverage.yml) to validate transformed/shared results.

### Concurrency behavior in workflow runs

Core production workflows define GitHub Actions `concurrency` groups so the same workflow family does not run in parallel on the same branch.

- Shared group workflows (for example `prod-data-pipeline-${{ github.ref }}`) queue in order and prevent overlapping writes across ingest/merge/transform/refresh.
- Check workflows use workflow-specific groups (for example `metric-coverage-${{ github.ref }}`) to avoid duplicate simultaneous checks.
- `cancel-in-progress: false` keeps active runs alive and queues later runs, preserving deterministic processing.

### Option B: Reproduce the pipeline locally from the repo

This is the best path when you want step-by-step control or need to debug a specific stage.

## Local Setup

Create the environment and install dependencies:

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Run basic checks before touching cloud resources:

```bash
uv run ruff check .
uv run pytest -q
```

## Common Procedures

### 1. Trigger ingestion for a single day

Use the Cloud Run wrapper:

```bash
PROJECT_ID="$GCP_PROJECT_ID" \
REGION="$REGION" \
JOB_NAME="$JOB_NAME" \
DATE=2026-03-29 \
bash scripts/run_cr_job.sh
```

Or execute the collector directly for local debugging:

```bash
python -m src.data_collection.daily_data_collector --start 2026-03-29 --end 2026-03-29 --source all
```

Use the direct collector only when you specifically want local execution behavior. Use `run_cr_job.sh` when you want parity with the deployed Cloud Run job.

### 2. Materialize native raw tables after ingestion

```bash
python scripts/materialize_partitions.py \
  --project "$BQ_PROJECT" \
  --dataset "$BQ_DATASET" \
  --start 2026-03-29 \
  --end 2026-03-29 \
  --sources all \
  --bucket "$GCS_BUCKET" \
  --prefix raw \
  --execute
```

This populates or updates native partitioned raw tables such as `tsi_raw_materialized` and `wu_raw_materialized`.

### 3. Run transformations

**Primary Method (SQL runner used by production workflow):**

```bash
python scripts/run_transformations.py \
  --project "$BQ_PROJECT" \
  --dataset "$BQ_DATASET" \
  --dir transformations/sql \
  --date 2026-03-29 \
  --execute
```

**Validation / Migration Path (dbt scaffold):**

```bash
cd transformations/dbt
dbt run --target dev
dbt test --target dev
```

For multi-day SQL backfill runs, use:

```bash
bash scripts/run_transformations_batch.sh
```

### 4. Refresh shared BigQuery tables for Grafana

```bash
bash scripts/refresh_tsi_shared.sh
bash scripts/refresh_wu_shared.sh
```

If you need the wider shared dataset sync path:

```bash
python scripts/sync_to_grafana.py
```

### 5. Run a one-command daily collection flow

```bash
bash scripts/daily_collection.sh
```

This is the fastest local operational path when you want ingestion, shared refresh, and basic freshness validation in sequence.

### 6. Backfill a historical window

For a guided backfill:

```bash
bash scripts/backfill_catchup.sh
```

Source-specific examples:

```bash
bash scripts/backfill_catchup.sh --source tsi
bash scripts/backfill_catchup.sh --source wu
```

After a backfill, refresh shared tables and rerun verification:

```bash
bash scripts/refresh_tsi_shared.sh
bash scripts/refresh_wu_shared.sh
python scripts/verify_cloud_pipeline.py \
  --project "$BQ_PROJECT" \
  --dataset "$BQ_DATASET" \
  --bucket "$GCS_BUCKET" \
  --prefix raw \
  --date 2026-03-29 \
  --show-tables \
  --check-rows
```

## Verification

### Script-based verification

Run the core verification scripts directly:

```bash
python scripts/verify_cloud_pipeline.py \
  --project "$BQ_PROJECT" \
  --dataset "$BQ_DATASET" \
  --bucket "$GCS_BUCKET" \
  --prefix raw \
  --date 2026-03-29 \
  --show-tables \
  --check-rows
python scripts/check_freshness.py --project "$BQ_PROJECT" --dataset "$BQ_SHARED_DATASET" --table tsi_raw_materialized
python scripts/check_staging_presence.py --project "$BQ_PROJECT" --dataset "$BQ_DATASET" --date 2026-03-29
python scripts/check_row_thresholds.py --project "$BQ_PROJECT" --dataset "$BQ_DATASET" --date 2026-03-29
python scripts/check_data_quality.py --start 2026-03-29 --end 2026-03-29
python scripts/check_residence_freshness_parity.py --project "$BQ_PROJECT" --prod-dataset sensors --shared-dataset sensors_shared --table residence_readings_daily --max-lag-days 0
```

### BigQuery spot checks

Check latest raw dates:

```bash
bq query --nouse_legacy_sql \
  "SELECT 'TSI' AS source, MAX(DATE(ts)) AS latest_date FROM \`$BQ_PROJECT.$BQ_DATASET.tsi_raw_materialized\`
   UNION ALL
   SELECT 'WU' AS source, MAX(DATE(ts)) AS latest_date FROM \`$BQ_PROJECT.$BQ_DATASET.wu_raw_materialized\`"
```

Check shared-table freshness:

```bash
bq query --nouse_legacy_sql \
  "SELECT 'TSI' AS source, MAX(DATE(ts)) AS latest_date FROM \`$BQ_PROJECT.$BQ_SHARED_DATASET.tsi_raw_materialized\`
   UNION ALL
   SELECT 'WU' AS source, MAX(DATE(ts)) AS latest_date FROM \`$BQ_PROJECT.$BQ_SHARED_DATASET.wu_raw_materialized\`"
```

Check recent row arrivals:

```bash
bq query --nouse_legacy_sql \
  "SELECT DATE(ts) AS collection_date, COUNT(*) AS rows
   FROM \`$BQ_PROJECT.$BQ_DATASET.tsi_raw_materialized\`
   WHERE DATE(ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 3 DAY)
   GROUP BY 1
   ORDER BY 1 DESC"
```

## Troubleshooting

### Cloud Run job fails

List recent executions:

```bash
gcloud run jobs executions list \
  --job="$JOB_NAME" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --limit=5
```

Read recent logs:

```bash
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=$JOB_NAME" \
  --project="$PROJECT_ID" \
  --limit=50
```

### Materialization or schema issues

Symptoms usually show up as load failures, missing stage tables, or type mismatches.

Checks:

- confirm the raw Parquet landed in the expected `raw/source=.../agg=raw/dt=.../` path
- rerun [`scripts/materialize_partitions.py`](../scripts/materialize_partitions.py) for the affected dates
- inspect [`src/storage/gcs_uploader.py`](../src/storage/gcs_uploader.py) when numeric coercion is involved

### Grafana is behind production data

Run:

```bash
bash scripts/refresh_tsi_shared.sh
bash scripts/refresh_wu_shared.sh
```

Then confirm `sensors_shared` freshness with the BigQuery checks above.

### macOS date command differences

Use the repo scripts instead of ad hoc date arithmetic where possible. The backfill and daily collection scripts already account for cross-platform date behavior.

## Related Docs

- [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
- [GRAFANA_SETUP.md](GRAFANA_SETUP.md)
- [DATA_QUICK_START.md](DATA_QUICK_START.md)
- [DAILY_AUTOMATION.md](DAILY_AUTOMATION.md)
