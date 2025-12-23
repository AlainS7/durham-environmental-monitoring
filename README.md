# Durham Environmental Monitoring System

**Status (October 2025):** Fully automated and operational. [![CodeScene general](https://codescene.io/images/analyzed-by-codescene-badge.svg)](https://codescene.io/projects/70050)

A comprehensive, cloud-native environmental monitoring system for Durham, NC. This project features a fully automated pipeline for collecting, processing, and analyzing high-resolution (15-minute interval) data from Weather Underground and TSI air quality sensors.

### 📎 Project Links

<p align="center">
  <a href="https://clausa.app.carto.com/map/abad0569-7066-48a1-b068-6da27fff21cb">
    <img src="https://img.shields.io/badge/🗺️_Interactive-Map-0088cc?style=for-the-badge" alt="View Interactive Map">
  </a>
  &nbsp;&nbsp;
  <a href="https://alains7.github.io/durham-environmental-monitoring/">
    <img src="https://img.shields.io/badge/📚_Documentation-Site-10b981?style=for-the-badge" alt="View Documentation Site">
  </a>
  &nbsp;&nbsp;
  <a href="https://deepnote.com/app/durham-weather/Durham-Environmental-Monitoring-01675d6c-334a-428e-9914-3106705b40c8?utm_content=01675d6c-334a-428e-9914-3106705b40c8&__run=true">
    <img src="https://img.shields.io/badge/📊_Analysis-Notebook-9333ea?style=for-the-badge" alt="View Deepnote Notebook">
  </a>
</p>

---

## 🌟 System Architecture & Features

For a comprehensive view of the entire system, including data flow, components, and monitoring, see **[SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md)**.

### Key Highlights

- **Fully Automated:** Data is collected, processed, and verified daily via a combination of Google Cloud Scheduler, Cloud Run, and GitHub Actions.
- **High-Resolution Data:** Research-grade 15-minute interval data from multiple sensor types.
- **Cloud-Native:** Leverages Google Cloud Storage (GCS) for raw data storage and BigQuery for warehousing and analytics.
- **Continuous Verification:** A daily GitHub Actions workflow (`daily-verify.yml`) runs a cloud pipeline verifier to ensure data integrity, schema consistency, and row count expectations.
- **Data Quality Monitoring:** An automated workflow (`tsi-data-quality.yml`) checks for NULLs in critical metrics, validates data coverage, and ensures consistency between raw and transformed data.
- **Secure & Auditable:** Uses Workload Identity Federation for secure, keyless authentication between GitHub Actions and GCP. All infrastructure is managed via Terraform.

---

## 🚀 Quick Start

This project uses `uv` for fast and efficient dependency management.

1.  **Install `uv`**:

    ```sh
    curl -LsSf https://astral.sh/uv/install.sh | sh
    source "$HOME/.cargo/bin/env"
    ```

2.  **Set up the environment**:

    ```sh
    uv venv
    source .venv/bin/activate
    uv pip install -e ".[dev]"
    ```

3.  **Configure Credentials**:

    - Authenticate with GCP for application-default credentials:
      ```sh
      gcloud auth application-default login
      ```
    - Ensure your GCP user has the necessary permissions or impersonate a service account.

4.  **Run Local Operations**:

    ```sh
    # Lint the codebase
    uv run ruff check .

    # Run unit tests
    uv run pytest -q

    # --- Example Scripts for Pipeline Interaction ---

    # Manually trigger the daily data collector for a specific date
    python -m src.data_collection.daily_data_collector --start-date 2025-10-06 --end-date 2025-10-06

    # Verify the cloud pipeline for a specific date
    python scripts/verify_cloud_pipeline.py --date 2025-10-06

    # Check data quality for a specific date
    python scripts/check_data_quality.py --start 2025-10-06 --end 2025-10-06
    ```

---

## 📊 Data Pipeline Overview

The data pipeline is designed for robustness and automation.

1.  **Collection (5:00 UTC):** A Cloud Scheduler job triggers a Cloud Run job that executes the `daily_data_collector.py` script. Data is fetched from WU and TSI APIs.
2.  **Storage (Raw):** Raw data is uploaded as Parquet files to a GCS bucket, partitioned by source and date.
3.  **Materialization:** The raw data is then materialized into partitioned BigQuery tables (`tsi_raw_materialized`, `wu_raw_materialized`).
4.  **Transformation (7:25 UTC):** A scheduled GitHub Actions workflow runs a series of SQL scripts to transform the raw data into analytics-ready tables (`sensor_readings_long`, `sensor_readings_hourly`, `sensor_readings_daily`).
5.  **Quality Checks (8:30 UTC):** Another GitHub Actions workflow runs quality checks against the BigQuery tables. Failures trigger alerts and create GitHub issues.
6.  **Visualization:** Looker Studio dashboards are connected to the BigQuery tables for visualization and analysis.

### Oura Data Pipeline

The Oura health metrics ingestion runs separately via the `oura-daily-collection.yml` workflow, exporting sleep/activity/readiness (and supplemental metrics) into the `oura` dataset. Coverage integrity across residents is validated by the `oura-integrity.yml` workflow (see Workflow Shortcuts table). Refer to `oura-rings/README.md` and `oura-rings/SECRETS_SETUP.md` for token management, security, and export configuration details.

---

## 🏗️ CI/CD Workflows

The project relies heavily on GitHub Actions for automation and verification.

| Workflow                      | Purpose                                               | Triggers                   |
| ----------------------------- | ----------------------------------------------------- | -------------------------- |
| `ci.yml`                      | Core linting and unit tests.                          | Push / PR                  |
| `daily-ingest.yml`            | Triggers the daily data collection Cloud Run job.     | Schedule (daily)           |
| `daily-verify.yml`            | Verifies the integrity of the cloud pipeline.         | Schedule (daily)           |
| `transformations-execute.yml` | Executes the dbt transformations.                     | Schedule (daily)           |
| `tsi-data-quality.yml`        | Runs data quality checks and sends alerts on failure. | Schedule (daily)           |
| `dbt-run-test.yml`            | Runs dbt tests and checks data freshness.             | Push (dbt paths), Schedule |
| `deploy.yml`                  | Deploys infrastructure changes via Terraform.         | Manual dispatch            |

---

## 📁 Project Structure

```text
├── config/                 # Project configuration files (paths, logging)
├── docs/                   # Detailed documentation
├── infra/                  # Terraform infrastructure as code
├── scripts/                # Standalone operational and utility scripts
├── src/                    # Python source code for data collection and utilities
│   ├── data_collection/    # Scripts and clients for fetching data
│   ├── storage/            # GCS and database interaction modules
│   └── utils/              # Common utilities
├── tests/                  # Unit and integration tests
└── transformations/        # SQL-based data transformations (dbt)
```

---

## 🔧 Key Scripts & Configuration

### Scripts

- `src/data_collection/daily_data_collector.py`: The main entry point for data collection. Fetches data and uploads to GCS.
- `scripts/verify_cloud_pipeline.py`: Verifies that data exists and is consistent across GCS and BigQuery.
- `scripts/check_data_quality.py`: Runs a battery of data quality checks against BigQuery data.
- `scripts/merge_backfill_range.py`: Merges data from staging tables into the main fact table for a range of dates.
- `scripts/run_merge_backfill.sh`: Helper wrapper for standardized backfill merges (see "Per-Source Dated Staging & Backfill Merge" below).

### Workflow Shortcuts

| Purpose                  | Workflow File                                 | Trigger            | Notes                                                 |
| ------------------------ | --------------------------------------------- | ------------------ | ----------------------------------------------------- |
| On-demand backfill merge | `.github/workflows/backfill-merge.yml`        | Manual (inputs)    | Uses `run_merge_backfill.sh` with date/source inputs  |
| Daily sensor merge       | `.github/workflows/daily-merge.yml`           | Scheduled          | Merges yesterday partitions (legacy auto-detect mode) |
| Oura collection          | `.github/workflows/oura-daily-collection.yml` | Scheduled / Manual | Collects Oura data and exports to BigQuery            |
| Staging presence check   | `.github/workflows/staging-presence.yml`      | Scheduled          | Ensures WU/TSI staging tables exist before transforms |
| Data freshness           | `.github/workflows/data-freshness.yml`        | Scheduled          | Validates latest sensor_readings timeliness           |
| Oura integrity check     | `.github/workflows/oura-integrity.yml`        | Scheduled / Manual | Validates resident-day coverage last N days           |
| Metric coverage          | `.github/workflows/metric-coverage.yml`       | Scheduled          | Confirms expected metric coverage ratios              |
| Row count threshold      | `.github/workflows/row-count-threshold.yml`   | Scheduled          | Flags abnormally low/high row volumes                 |

### Per-Source Dated Staging & Backfill Merge

Recent pipeline hardening introduced per-day, per-source staging tables in BigQuery:

```text
staging_wu_YYYYMMDD
staging_tsi_YYYYMMDD
```

Each table contains already "melted" long-form rows `(timestamp, deployment_fk, metric_name, value)` specific to one date and source. They are written by `daily_data_collector.py` and have a 30‑day expiration to remain compatible with BigQuery sandbox constraints.

#### Why this pattern?

- Enables incremental, idempotent recovery/backfill (re-running a date overwrites that day’s table with `WRITE_TRUNCATE`).
- Avoids complexity of managing partitions for short-lived staging.
- Decouples ingestion reliability from transformation (late source can be merged independently).

#### Merging a Backfill Range

Use `scripts/merge_backfill_range.py` with `--per-source-dated` to MERGE staging rows into the fact table (`sensor_readings`). Missing source tables for a day are skipped; existing sources still merge.

```sh
python scripts/merge_backfill_range.py \
  --project "$BQ_PROJECT" \
  --dataset sensors \
  --start 2025-10-05 \
  --end 2025-11-07 \
  --per-source-dated \
  --sources tsi,wu
```

Options:

- `--update-only-if-changed`: Update existing rows only if `value` differs (reduces DML).
- `--dry-run`: Show planned merges without executing.
- `--sources`: Comma list; narrow to a single source for late recovery (e.g. `tsi`).

#### Implementation Notes

- Merge script CASTs `timestamp` to TIMESTAMP to handle staging tables that loaded timestamps as STRING.
- Ingestion infers sensor type (WU / TSI) using config + heuristics to link sensor IDs to `deployment_fk`.
- Staging tables expire after ~30 days; re-run ingestion if a needed table has expired.

#### Troubleshooting

| Symptom                                                      | Likely Cause                            | Resolution                                                 |
| ------------------------------------------------------------ | --------------------------------------- | ---------------------------------------------------------- |
| `No matching signature for operator = for TIMESTAMP, STRING` | Old merge script version                | Pull latest; ensure CAST logic present.                    |
| Missing `staging_wu_YYYYMMDD` warning                        | No WU data or ingestion failed          | Re-run ingestion for that date; confirm source outage.     |
| Row counts unusually low                                     | Timestamp coercion dropped invalid rows | Inspect raw parquet & staging; verify normalization logic. |

#### Quick Verification

```sh
# Count merged rows for a sample date
bq query --nouse_legacy_sql "SELECT COUNT(*) c FROM \`${BQ_PROJECT}.sensors.sensor_readings\` WHERE DATE(timestamp)='2025-11-07'"

# Count staging rows (TSI) for same date
bq query --nouse_legacy_sql "SELECT COUNT(*) c FROM \`${BQ_PROJECT}.sensors.staging_tsi_20251107\`"
```

#### Least-Privilege Post-Backfill IAM (Summary)

#### Cost Estimation (Sensors)

Use the helper script `scripts/estimate_sensor_costs.py` to get an on-demand BigQuery query cost estimate (MERGE dry-run bytes) for a date range of per-source staging tables:

```sh
python scripts/estimate_sensor_costs.py \
  --project "$BQ_PROJECT" \
  --dataset sensors \
  --start 2025-11-01 \
  --end 2025-11-07 \
  --sources tsi,wu \
  --price-per-tb 6
```

Outputs per-day processed bytes and an estimated dollar cost (default: $6/TB). Adjust `--price-per-tb` to reflect your billing plan or committed price.

To also estimate storage growth, include `--storage-price-per-gb-month` and `--storage-days` (proration). Storage is approximated by summing logical bytes of the per-day staging tables used in the merge:

```sh
python scripts/estimate_sensor_costs.py \
  --project "$BQ_PROJECT" \
  --dataset sensors \
  --start 2025-11-01 \
  --end 2025-11-07 \
  --sources tsi,wu \
  --storage-price-per-gb-month 0.02 \
  --storage-days 30
```

Note: Storage estimate is an upper-bound approximation; actual table clustering/encoding, updates vs inserts, and retention policies influence final cost.

After completing a backfill, remove temporary `roles/bigquery.admin` from the ingestion service account (e.g. `data-runner@...`). Retain:

- `roles/bigquery.dataEditor` (or dataset-scoped WRITER)
- `roles/bigquery.jobUser`
- `roles/bigquery.readSessionUser` (if using Storage API)
- `roles/secretmanager.secretAccessor`

Example removal:

```sh
gcloud projects remove-iam-policy-binding "$BQ_PROJECT" \
  --member=serviceAccount:data-runner@${BQ_PROJECT}.iam.gserviceaccount.com \
  --role=roles/bigquery.admin
```

### Configuration

- `config/base/paths.py`: Defines key paths for data storage and other resources.
- `config/environments/*.py`: Environment-specific configurations (development vs. production).
- `transformations/sql/*.sql`: The SQL files that define the data transformation logic.

---

## 🔒 Security

This project includes automated security scanning for Python dependencies using `pip-audit`. The security audit runs as part of the CI pipeline to identify known vulnerabilities.

For detailed information about security audit configuration and current status, see **[SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md)**.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

## 🤝 Contributing

1. Fork the repository.
2. Create a feature branch.
3. Make your changes and add tests.
4. Ensure all checks in `ci.yml` pass.
5. Submit a pull request.
