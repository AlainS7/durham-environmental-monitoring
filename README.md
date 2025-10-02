# Durham Environmental Monitoring System

> A daily GitHub Actions workflow (`daily-verify.yml`) runs the cloud pipeline verifier against the previous day's partition. It enforces:
>
> * GCS round-trip write/read
> * BigQuery dataset & table presence
> * Adaptive row counts per table
> * Schema normalization (canonical `ts` TIMESTAMP + float latitude/longitude copies)
> * Epoch diagnostics (detects seconds/millis/micros/nanos integer time columns)

[![CodeScene general](https://codescene.io/images/analyzed-by-codescene-badge.svg)](https://codescene.io/projects/70050)

A comprehensive environmental monitoring system for Durham, NC, featuring **high-resolution 15-minute interval** data collection from Weather Underground and TSI air quality sensors for accurate research and analysis.

## 🔐 Image Versioning & Deployment (Tag → Digest)

Promote clarity (human-friendly tags) first, then lock production to immutable digests.

Workflow:

1. Build images with a semantic tag (date + short commit):

```bash
TAG="$(date +%Y%m%d-%H%M)-$(git rev-parse --short HEAD)"
gcloud builds submit --config=cloudbuild.multi.yaml --substitutions=_TAG=$TAG
```

1. Deploy Terraform referencing the tag (easy rollback):

```bash
./scripts/deploy_with_tag.sh -p $PROJECT_ID -b $GCS_BUCKET -t $TAG
```

1. Validate Cloud Run job executions & BigQuery partitions.

1. Pin to digests for immutability:

```bash
./scripts/pin_image_digests.sh $PROJECT_ID us-central1 weather-maintenance-images $TAG
# Copy the terraform apply command with @sha256 digests and run it
```

1. Subsequent release: repeat; rollback = redeploy previous tag then (optionally) re-pin.

Rationale: tags improve traceability; digests guarantee immutability and reproducibility.

## 🌟 Features

### Continuous Verification

A daily GitHub Actions workflow (`daily-verify.yml`) runs the cloud pipeline verifier against the previous day's partition. It enforces:

* GCS round-trip write/read
* BigQuery dataset & table presence
* Adaptive row counts per table
* Schema normalization (canonical `ts` TIMESTAMP + float latitude/longitude copies)
* Epoch diagnostics (detects seconds/millis/micros/nanos integer time columns)

Failures surface directly in the Actions tab and block unnoticed schema drift.

### IAM Hardening

See `docs/IAM_HARDENING.md` for least-privilege roles, service account layout, and Workload Identity Federation (GitHub → GCP) guidance.

### Secrets & Local Credentials

- **Never commit service account keys, `.env`, or Cloud Run export snapshots.** Files such as `gcp-creds.json`, `gha-creds.json`, `job_full.yaml`, and Terraform state are ignored by default—keep real values in a private location (for example, `./secrets/`).
- Populate secrets with `scripts/create_secrets.sh` or Terraform so that Cloud Run jobs read from Secret Manager instead of static files.
- Copy `.env.example` to `.env` for local work, but store the real `.env` outside the repository or load it via a secrets manager.
- If you need reference manifests for Cloud Run, regenerate sanitized exports with `gcloud run jobs describe ...` and scrub project-specific metadata before sharing.

## 📡 Data Collection Specifications

### High-Resolution Research-Grade Data

* **Temporal Resolution**: 15-minute intervals
* **Data Processing**: Daily aggregations (no weekly averaging)
* **Quality Standards**: Research-grade accuracy and credibility
* **Collection Frequency**: Automated daily pulls at 6:00 AM
* **Data Preservation**: All 15-minute measurements retained for analysis

### Sensor Coverage

* **TSI Air Quality Sensors**: PM2.5, PM10, Temperature, Humidity
* **Weather Underground Stations**: Temperature, Humidity, Wind, Solar Radiation
* **Update Frequency**: Every 15 minutes for all sensors
* **Data Validation**: Continuous quality monitoring and anomaly detection

## 🚀 Quick Start (with uv)

1. **Install uv** (if not already):

   ```sh
   curl -LsSf https://astral.sh/uv/install.sh | sh
   export PATH="$HOME/.cargo/bin:$PATH"
   ```

2. **Create a virtual environment** (recommended):

   ```sh
   uv venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:

   ```sh
   uv pip sync requirements.txt
   uv pip sync requirements-dev.txt
   ```

4. **Configure Credentials**:
   * Add Google API credentials to `creds/google_creds.json`
   * Add Weather Underground API key to `creds/wu_api_key.json`
   * Add TSI credentials to `creds/tsi_creds.json`

5. **Run Data Collection**:

   ```sh
   python src/data_collection/faster_wu_tsi_to_sheets_async.py
   ```

6. **System Management**:

   ```sh
   # Lint
   uv run ruff check .

   # Tests
   uv run pytest -q

   # Row thresholds & metric coverage (example date)
   python scripts/check_row_thresholds.py --date 2025-08-20
   python scripts/check_metric_coverage.py --date 2025-08-20

   # Verify cloud pipeline (yesterday by default if omitted)
   python scripts/verify_cloud_pipeline.py --date 2025-08-27

   # Load a processed day to BigQuery
   python scripts/load_to_bigquery.py --date 2025-08-20 --source all --agg raw

   # Merge staging into canonical fact (example)
   python scripts/merge_sensor_readings.py --date 2025-08-20 \
      --staging-table staging_sensor_readings_raw \
      --target-table sensor_readings --update-only-if-changed --cleanup
   ```

**Note:** The CI/CD pipeline and Docker build use `uv` for all dependency management. For more info, see: [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv)

## 📁 Project Structure

```text
├── config/                 # Configuration files
├── src/                   # Source code
│   ├── core/              # Core functionality
│   ├── data_collection/   # Data collection scripts
│   └── automation/        # Automation systems
├── data/                  # Data storage
├── docs/                  # Documentation
├── tests/                 # Test files
└── scripts/               # Utility scripts
```

## 🛠️ System Components

### Data Collection

* **Weather Underground**: Meteorological data collection
* **TSI Sensors**: Air quality monitoring
* **Automated Scheduling**: Configurable data collection intervals

### Data Management

* **Master Data System**: Historical data aggregation
* **Google Drive Sync**: Cloud backup and sharing
* **Test Data Isolation**: Separate handling of test vs production data

### Automation

* **Daily Sheets**: Automated daily reports
* **Master Data Updates**: Weekly data consolidation
* **Alert System**: Anomaly detection and notifications

## 📊 Data Flow

1. **Collection**: Sensors → Raw Data
2. **Processing**: Raw Data → Processed Data
3. **Storage**: Processed Data → Master Files
4. **Reporting**: Master Files → Visualizations & Reports
5. **Distribution**: Reports → Google Drive & Dashboard

## 🛠️ Troubleshooting

### If Test Sensors Appear in Google Sheets

The system is designed to exclude test sensors from Google Sheets. If test sensors appear:

1. **Check Sheet Date**: Ensure you're looking at recently created sheets
2. **Verify Configuration**: Confirm test sensor IDs are in `config/test_sensors_config.py`
3. **Generate Fresh Sheet**: Run data collection to create new clean sheets
4. **Review Data Sources**: Check if additional sensors should be classified as test sensors

### Common Issues

* **KeyError: 'Device Name'**: Fixed in current version with proper column handling
* **Mixed Test/Production Data**: Resolved with enhanced separation logic
* **Chart Data Issues**: Now uses production-only data sources

### Validation

Run the system with recent date ranges to verify clean separation:

```bash
python src/data_collection/faster_wu_tsi_to_sheets_async.py
# Select date range within last 7 days for best results
```

## 🔧 Configuration

Main configuration files:

* `config/improved_google_drive_config.py` - Google Drive paths
* `config/test_sensors_config.py` - Test sensor management
* `config/master_data_config.json` - Master data system settings

## 🏗️ CI / Automation Workflows

| Workflow | Purpose | Triggers |
|----------|---------|----------|
| `daily-verify.yml` | Cloud pipeline verification (GCS + BigQuery integrity) | Scheduled daily |
| `dbt-compile.yml` | Compile & dependency check of dbt project | PR (dbt paths), schedule |
| `dbt-run-test.yml` | dbt run + test + freshness + artifacts upload | Push (dbt paths), schedule |
| `metric-coverage.yml` | Ensures expected metrics present in facts | Schedule / manual |
| `row-count-threshold.yml` | Adaptive row volume anomaly detection | Schedule / manual |
| `transformations-dry-run.yml` | Safe dry run of transformation wrapper | PR / manual |
| `transformations-execute.yml` | Execute transformations (controlled) | Manual dispatch |
| `maintenance.yml` | Cleanup & periodic maintenance | Schedule |
| `ci.yml` | Core lint / unit tests | Push / PR |

Artifacts (dbt manifest & run results) are uploaded by `dbt-run-test.yml` for inspection.

## ❗ Removed Legacy References

Older docs referenced `scripts/production_manager.py` and a web dashboard module (`src.monitoring.dashboard`). These components are not present; operational entry points live under `scripts/` (collection, loading, verification, quality checks).

## 📋 Maintenance

* **Daily**: Automated data collection and basic reporting
* **Weekly**: Master data updates and system health checks
* **Monthly**: Comprehensive system verification and cleanup

## 🧪 Test Sensor Management

### Current Configuration

* **27 Test Sensors Configured**: 14 WU + 13 TSI test sensors

### Quick Raw Sample Fetch (Diagnostics)

Use `scripts/fetch_sample_raw.py` to pull a single day's raw data directly from a source API and inspect non-null coverage before it enters the pipeline.

Examples:

```sh
WU_API_KEY=yourkey \
python scripts/fetch_sample_raw.py --source WU --date 2025-08-20 --stations STATIONID123 --verbose --validated-out /tmp/wu_20250820.parquet
```

```sh
TSI_CLIENT_ID=cid TSI_CLIENT_SECRET=secret TSI_AUTH_URL=https://auth.example/token \
python scripts/fetch_sample_raw.py --source TSI --date 2025-08-20 --devices DEVICE123 --validated-out /tmp/tsi_20250820.parquet
```

Output includes a JSON summary with row counts and per-column non-null counts for fast gap analysis.

* **Production Data Only**: Google Sheets contain only production sensor data
* **Separate Storage**: Test data isolated for internal analysis

### Test Sensor IDs

**Weather Underground Test Sensors:**

* KNCDURHA634 through KNCDURHA648 (MS-09 through MS-22)

**TSI Test Sensors:**

* AA-2 (Burch) through AA-14 (clustered test deployment)

### Data Separation

```text
🧪 TEST SENSORS → Local storage (/test_data/)
🏭 PRODUCTION SENSORS → Google Sheets & reporting
```

## 🎯 System Status (June 2025)

### ✅ Production Ready Features

* **Clean Google Sheets**: Production sensor data only
* **Test Sensor Exclusion**: All test sensors properly filtered from external reports
* **Data Integrity**: Robust separation logic with comprehensive validation
* **Professional Output**: Production-ready visualizations and reports

### Key Technical Implementations

* **Enhanced Separation Logic**: `separate_sensor_data_by_type()` with comprehensive error handling
* **Google Sheets Integration**: Production-only data flow with proper column handling
* **Configuration Validation**: Pre-collection validation prevents common errors
* **Smart TSI Detection**: Automatic detection of available sensor ID fields

## Cloud storage and BigQuery

This project writes raw sensor data to Google Cloud Storage (GCS) as Parquet, then materializes into native BigQuery tables for modeling (safer than direct loads when timestamps are INT epochs).

Recommended flow:

1) Create external tables over GCS Parquet (WU/TSI)
2) Materialize per-day into native tables with TIMESTAMP `ts` (partitioned by DATE(ts))
3) Run SQL transformations to build `sensor_readings_long`, `sensor_readings_hourly`, and `sensor_readings_daily`.

Notes:

* The analytics tables include `latitude`, `longitude`, and a `geog` GEOGRAPHY point when coordinates are available, enabling direct mapping in Looker Studio without joins.

Make targets:

* `create-external` — build external tables
* `materialize` — per-day materialization from externals
* `run-transformations` — execute SQL
* `e2e` — end-to-end for a date range
* `verify-outputs` — quick counts per date

Direct loads are retained for troubleshooting (`scripts/load_to_bigquery.py`) but deprecated for routine ops.

Environment variables:

* GCS_BUCKET: Target GCS bucket (required for GCS uploads)
* GCS_PREFIX: Prefix within the bucket (default: sensor_readings)
* BQ_PROJECT: BigQuery project (optional; defaults to ADC project)
* BQ_DATASET: BigQuery dataset (required by the loader)
* BQ_LOCATION: BigQuery location (default: US)
* GOOGLE_APPLICATION_CREDENTIALS: Path to a service account key (if not using ADC)

Example (zsh):

```sh
export GCS_BUCKET="my-bucket"
export GCS_PREFIX="sensor_readings"
export BQ_PROJECT="my-project"
export BQ_DATASET="env_readings"
export BQ_LOCATION="US"
# export GOOGLE_APPLICATION_CREDENTIALS="$PWD/sa.json"  # if needed
```

## Scripts overview

### daily_data_collector.py

Path: `src/data_collection/daily_data_collector.py`

Purpose: Fetch Weather Underground (WU) and TSI data and write to configured sinks.

Defaults: raw (no aggregation), sink=gcs.

Key flags:

* `--aggregate/--no-aggregate` (default: no-aggregate)
* `--agg-interval <pandas offset>` (e.g. `h`, `15min`) when aggregating
* `--sink {gcs,db,both}`
* `--source {WU,TSI,all}`
* `--start-date / --end-date` (ISO date) for bounded backfill

Example:

```sh
python -m src.data_collection.daily_data_collector \
   --no-aggregate \
   --sink gcs \
   --source all \
   --start-date 2025-01-01 \
   --end-date 2025-01-02
```

### load_to_bigquery.py (deprecated path)

Path: `scripts/load_to_bigquery.py`

Purpose: Batch load Parquet files directly into BigQuery. Deprecated in favor of external→materialize flow that normalizes epoch integers to TIMESTAMP.

Table naming: `sensor_readings_{source}_{agg}` (e.g. `sensor_readings_wu_raw`).

Partitioning: by `timestamp`; clustering: `native_sensor_id` (default). Beware: if `timestamp` is an INT epoch in Parquet, partitioning will fail. Use materialize flow instead.

Requirements: `BQ_DATASET` and `GCS_BUCKET` (env or flags), ADC credentials.

### Quick usage: BigQuery loader

With env vars:

```sh
export GCS_BUCKET="my-bucket"
export GCS_PREFIX="sensor_readings"
export BQ_PROJECT="my-project"
export BQ_DATASET="env_readings"
export BQ_LOCATION="US"

python scripts/load_to_bigquery.py \
  --date 2025-01-01 \
  --source all \
  --agg raw
```

Via flags:

```sh
python scripts/load_to_bigquery.py \
  --project my-project \
  --dataset env_readings \
  --location US \
  --bucket my-bucket \
  --prefix sensor_readings \
  --date 2025-01-01 \
  --source WU \
  --agg raw \
  --table-prefix sensor_readings \
  --partition-field timestamp \
  --cluster-by native_sensor_id
```

Notes:

* Authenticate locally first: `gcloud auth application-default login` or set GOOGLE_APPLICATION_CREDENTIALS.
* The loader creates the dataset if needed and appends rows by default (WRITE_APPEND).

### Idempotent Reload Features

To safely re-run a day's ingestion without creating duplicates:

* GCS Uploads: `GCSUploader` now skips existing blobs by default. Use `--force` (or `force=True` in code) to overwrite.
* Partition Replace: `scripts/load_to_bigquery.py` adds `--replace-date` which deletes existing rows for the date partition before appending new data.

Example reprocessing a date with overwrite:

```sh
python scripts/load_to_bigquery.py \
   --date 2025-08-20 \
   --source all \
   --agg raw \
   --replace-date
```

### MERGE-Based Upserts (Advanced)

For fully idempotent corrections with field-level updates, use the merge script after landing data into a staging table.

Workflow:

1. Land raw parquet to a staging table (use a staging prefix or separate table name when loading).
2. Run `scripts/merge_sensor_readings.py` to upsert into the canonical fact (default key: `(timestamp, deployment_fk, metric_name)`).
3. Optionally clean the staging partition with `--cleanup`.

Flags:

* `--update-only-if-changed`: Only UPDATE when any non-key column differs (reduces slot usage & preserves modified time semantics).
* `--cleanup`: DELETE staging rows for the processed date on success.

Example end-to-end:

```sh
# Load to staging (choose a distinct target table name)
python scripts/load_to_bigquery.py \
   --date 2025-08-20 --source all --agg raw \
   --table-prefix staging_sensor_readings_raw --replace-date

# Merge into canonical
python scripts/merge_sensor_readings.py \
   --date 2025-08-20 \
   --staging-table staging_sensor_readings_raw \
   --target-table sensor_readings \
   --update-only-if-changed \
   --cleanup
```

Benefits:

* Safe reprocessing without full partition DELETE when only a subset changed.
* Minimizes churn and potential race conditions with downstream readers.
* Explicit, auditable change set via MERGE semantics.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 📞 Support

For questions or support, please check the documentation in the `docs/` directory or create an issue in the repository.

---

### Last updated: August 2025

### Ingestion Recovery (Staging Tables Missing)

If freshness or staging presence checks fail (no `staging_<source>_YYYYMMDD` tables for recent dates):

1. Manually execute the Cloud Run ingestion job for each missing date (oldest first) or run the local collector to GCS.
1. Verify raw Parquet objects exist at `gs://$GCS_BUCKET/$GCS_PREFIX/source=<SRC>/agg=raw/dt=<DATE>/` for each source.
1. Load to BigQuery staging-style tables (partitioned) if using unified loader pattern:

```bash
python scripts/load_to_bigquery.py --project "$BQ_PROJECT" --dataset sensors \
   --bucket "$GCS_BUCKET" --date 2025-08-21 --source all --agg raw --replace-date
```

1. For per-source dated table pattern, confirm ingest creates `staging_<src>_<YYYYMMDD>`; if absent, re-run ingestion.
1. After all staging tables present, merge into fact:

```bash
python scripts/merge_backfill_range.py --project "$BQ_PROJECT" --dataset sensors \
   --start 2025-08-21 --end 2025-08-28 --sources tsi,wu
```

1. Re-check freshness:

```bash
python scripts/check_freshness.py --project "$BQ_PROJECT" --dataset sensors --table sensor_readings --max-lag-days 1
```

1. Ensure daily ingestion trigger exists (schedule Cloud Run job or add a workflow) before 07:05 UTC so downstream checks pass.

