# Durham Environmental Monitoring System

**Status:** Active cloud-native pipeline with automated ingestion, transformations, shared-table refresh, and verification workflows. [![CodeScene general](https://codescene.io/images/analyzed-by-codescene-badge.svg)](https://codescene.io/projects/70050)

A comprehensive, cloud-native environmental monitoring system for Durham, NC. This project features a fully automated pipeline for collecting, processing, and analyzing high-resolution (15-minute interval) data from Weather Underground and TSI air quality sensors.

## Project Links

<p align="center">
  <a href="https://research-study-dashboard.appwrite.network/">
    <img src="https://img.shields.io/badge/🖥️_Participant-Demo_Dashboard-f97316?style=for-the-badge" alt="View Participant Demo Dashboard">
  </a>
  &nbsp;&nbsp;
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

## System Architecture & Features

For a comprehensive view of the entire system, including data flow, components, and monitoring, see **[ARCHITECTURE_OVERVIEW.md](docs/ARCHITECTURE_OVERVIEW.md)**. For reproducible operational steps, see **[OPERATIONS_RUNBOOK.md](docs/OPERATIONS_RUNBOOK.md)**.

### Key Highlights

- **Fully Automated:** Data is collected hourly and processed through fast/stable orchestration via Cloud Run and GitHub Actions, with optional Cloud Scheduler triggering.
- **High-Resolution Data:** Research-grade 15-minute interval data from multiple sensor types.
- **Cloud-Native:** Leverages Google Cloud Storage (GCS) for raw data storage and BigQuery for warehousing and analytics.
- **Continuous Verification:** A daily GitHub Actions workflow (`daily-verify.yml`) runs a cloud pipeline verifier to ensure data integrity, schema consistency, and row count expectations.
- **Data Quality Monitoring:** An automated workflow (`tsi-data-quality.yml`) checks for NULLs in critical metrics, validates data coverage, and ensures consistency between raw and transformed data.
- **Secure & Auditable:** Uses Workload Identity Federation for secure, keyless authentication between GitHub Actions and GCP. All infrastructure is managed via Terraform.

---

## Prerequisites

Before setup, ensure you have:

- Python 3.9+
- [`uv`](https://docs.astral.sh/uv/)
- Google Cloud SDK (`gcloud`)
- Access to a GCP project with BigQuery and Cloud Storage permissions

---

## Quick Start

This project uses `uv` for fast and efficient dependency management.

1. **Install `uv`**:

   ```sh
   curl -LsSf https://astral.sh/uv/install.sh | sh
   source "$HOME/.cargo/bin/env"
   ```

2. **Set up the environment**:

   ```sh
   uv venv
   source .venv/bin/activate
   uv pip install -e ".[dev]"
   ```

3. **Create local environment file**:

   ```sh
   cp .env.example .env
   ```

   Update `.env` with your own cloud resources and API credentials.

4. **Configure Credentials**:
   - Authenticate with GCP for application-default credentials:

     ```sh
     gcloud auth application-default login
     ```

   - GCP project IDs are not secrets; keep placeholders in committed files and use real values only in your local `.env`/secrets manager.
   - Ensure your GCP user has the necessary permissions or impersonate a service account.

5. **Run Local Operations**:

   ```sh
   # Lint the codebase
   uv run ruff check .

   # Run unit tests
   uv run pytest -q

   # --- Example Scripts for Pipeline Interaction ---

    # Manually trigger the daily data collector for a specific date
    python -m src.data_collection.daily_data_collector --start 2025-10-06 --end 2025-10-06

   # Verify the cloud pipeline for a specific date
   python scripts/verify_cloud_pipeline.py --date 2025-10-06

   # Check data quality for a specific date
   python scripts/check_data_quality.py --start 2025-10-06 --end 2025-10-06
   ```

---

## Data Pipeline Overview

The data pipeline is designed for robustness and automation.

1. **Collection (Hourly at :05 UTC):** The `daily-ingest.yml` GitHub Actions workflow triggers the Cloud Run job that executes `daily_data_collector.py`. Cloud Scheduler is also supported as an optional trigger path.
2. **Storage (Raw):** Raw data is uploaded as Parquet files to a GCS bucket, partitioned by source and date.
3. **Materialization:** The raw data is then materialized into partitioned BigQuery tables (`tsi_raw_materialized`, `wu_raw_materialized`).
4. **Transformation (fast + stable lanes):** SQL transformations run hourly for dashboard freshness and also on a daily stabilization run to keep finalized daily analytics tables current.
5. **Quality Checks (7:45–8:30 UTC):** Scheduled workflows run freshness and quality checks against BigQuery tables. Failures trigger alerts and create GitHub issues.
6. **Visualization:** Looker Studio dashboards are connected to the BigQuery tables for visualization and analysis.

---

## CI/CD Workflows

The project relies heavily on GitHub Actions for automation and verification.

### Core Pipeline (Scheduled)

| Workflow                      | Purpose                                            | Triggers                           |
| ----------------------------- | -------------------------------------------------- | ---------------------------------- |
| `daily-ingest.yml`            | Triggers the Cloud Run data collection job.        | Schedule (hourly)                  |
| `daily-merge.yml`             | Merges staged sensor readings into the fact table. | Schedule (7:10 UTC daily)          |
| `transformations-execute.yml` | Executes SQL transformation models.                | Schedule (7:25 UTC daily + hourly) |
| `daily-refresh-shared.yml`    | Refreshes Grafana-facing shared BigQuery tables.   | Schedule (hourly)                  |

### Verification & Quality (Scheduled)

| Workflow                  | Purpose                                                       | Triggers                                                   |
| ------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------- |
| `e2e-nightly.yml`         | Nightly end-to-end pipeline integrity test.                   | Schedule (7:05 UTC daily)                                  |
| `staging-presence.yml`    | Confirms staging tables are populated before transforms run.  | Schedule (7:05 UTC daily)                                  |
| `row-count-threshold.yml` | Validates row counts against expected thresholds.             | Schedule (8:15 UTC) + `workflow_run` after transformations |
| `metric-coverage.yml`     | Validates metric field coverage across sensor sources.        | Schedule (8:05 UTC) + `workflow_run` after transformations |
| `data-freshness.yml`      | Checks data freshness and prod/shared residence parity.       | Schedule (8:35 UTC) + `workflow_run` after shared refresh  |
| `data-quality-check.yml`  | Runs full data quality assertions against BigQuery tables.    | Schedule (8:00 UTC daily)                                  |
| `tsi-data-quality.yml`    | TSI-specific quality checks; sends Teams alert on failure.    | Schedule (8:30 UTC daily)                                  |
| `daily-verify.yml`        | Verifies cloud pipeline integrity (GCS presence, row counts). | Schedule (6:15 UTC daily)                                  |

### CI & Build

| Workflow           | Purpose                                           | Triggers                   |
| ------------------ | ------------------------------------------------- | -------------------------- |
| `ci.yml`           | Core linting and unit tests.                      | Push / PR                  |
| `dbt-compile.yml`  | Compiles dbt models to catch errors before merge. | PR (dbt paths), Schedule   |
| `dbt-run-test.yml` | Runs dbt tests and checks data freshness.         | Push (dbt paths), Schedule |

### Infrastructure & Manual Operations

| Workflow                        | Purpose                                                        | Triggers                             |
| ------------------------------- | -------------------------------------------------------------- | ------------------------------------ |
| `deploy.yml`                    | Deploys infrastructure changes via Terraform.                  | Manual dispatch                      |
| `sync-to-sharepoint.yml`        | Exports curated data packs to SharePoint.                      | Manual dispatch                      |
| `execute-job.yml`               | Ad-hoc Cloud Run job trigger for any date or range.            | Manual dispatch                      |
| `verify-compare.yml`            | Compare-mode verification of pipeline output.                  | Manual dispatch                      |
| `backfill-transformations.yml`  | Backfills historical transformation tables.                    | Manual dispatch                      |
| `weekly-self-heal-backfill.yml` | Re-merges/rebuilds a recent window and re-syncs shared tables. | Schedule (Sunday 09:20 UTC) + manual |

---

## Workflow Toggles (Temporary)

To avoid permission-related failures while SharePoint/Teams access is being provisioned, the related workflow paths are gated by repository variables.

- `ENABLE_SHAREPOINT_WORKFLOWS`: set to `true` to allow SharePoint sync/backfill jobs to run.
- `ENABLE_TEAMS_NOTIFICATIONS`: set to `true` to allow Teams failure notifications to be sent.

If these variables are unset (or not `true`), SharePoint jobs and Teams notifications remain disabled.

Repository settings path: `Settings -> Secrets and variables -> Actions -> Variables`.

---

## Project Structure

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
└── transformations/        # SQL transformations plus dbt validation scaffolding
```

Additional standalone sub-projects in this repository:

- `hot_durham_project/` — map application with its own setup and runtime.
- `oura-rings/` — Oura import/export utilities with separate credential requirements.

These are optional and independent from the core ingestion/transformation pipeline.

---

## Key Scripts & Configuration

### Scripts

- `src/data_collection/daily_data_collector.py`: The main entry point for data collection. Fetches data and uploads to GCS.
- `scripts/verify_cloud_pipeline.py`: Verifies that data exists and is consistent across GCS and BigQuery.
- `scripts/check_data_quality.py`: Runs a battery of data quality checks against BigQuery data.
- `scripts/merge_backfill_range.py`: Merges data from staging tables into the main fact table for a range of dates.

### Configuration

- `config/base/paths.py`: Defines key paths for data storage and other resources.
- `config/environments/*.py`: Environment-specific configurations (development vs. production).
- `transformations/sql/*.sql`: The SQL files that define the data transformation logic.

---

## Security

This project includes automated security scanning for Python dependencies using `pip-audit`. The security audit runs as part of the CI pipeline to identify known vulnerabilities.

For detailed information about security audit configuration and current status, see **[SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md)**.

---

## License

This project is licensed under the [MIT License](LICENSE).

## Contributing

1. Fork the repository.
2. Create a feature branch.
3. Make your changes and add tests.
4. Ensure all checks in `ci.yml` pass.
5. Submit a pull request.
