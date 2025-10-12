# Durham Environmental Monitoring System

**Status (October 2025):** Fully automated and operational.

[![CodeScene general](https://codescene.io/images/analyzed-by-codescene-badge.svg)](https://codescene.io/projects/70050)

A comprehensive, cloud-native environmental monitoring system for Durham, NC. This project features a fully automated pipeline for collecting, processing, and analyzing high-resolution (15-minute interval) data from Weather Underground and TSI air quality sensors.

---

## 🌟 System Architecture & Features

For a comprehensive view of the entire system, including data flow, components, and monitoring, see **[SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md)**.

### Key Highlights

*   **Fully Automated:** Data is collected, processed, and verified daily via a combination of Google Cloud Scheduler, Cloud Run, and GitHub Actions.
*   **High-Resolution Data:** Research-grade 15-minute interval data from multiple sensor types.
*   **Cloud-Native:** Leverages Google Cloud Storage (GCS) for raw data storage and BigQuery for warehousing and analytics.
*   **Continuous Verification:** A daily GitHub Actions workflow (`daily-verify.yml`) runs a cloud pipeline verifier to ensure data integrity, schema consistency, and row count expectations.
*   **Data Quality Monitoring:** An automated workflow (`tsi-data-quality.yml`) checks for NULLs in critical metrics, validates data coverage, and ensures consistency between raw and transformed data.
*   **Secure & Auditable:** Uses Workload Identity Federation for secure, keyless authentication between GitHub Actions and GCP. All infrastructure is managed via Terraform.

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
    uv pip sync requirements.txt
    uv pip sync requirements-dev.txt
    ```

3.  **Configure Credentials**:
    *   Authenticate with GCP for application-default credentials:
        ```sh
        gcloud auth application-default login
        ```
    *   Ensure your GCP user has the necessary permissions or impersonate a service account.

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

---

## 🏗️ CI/CD Workflows

The project relies heavily on GitHub Actions for automation and verification.

| Workflow                    | Purpose                                                 | Triggers                |
| --------------------------- | ------------------------------------------------------- | ----------------------- |
| `ci.yml`                    | Core linting and unit tests.                            | Push / PR               |
| `daily-ingest.yml`          | Triggers the daily data collection Cloud Run job.       | Schedule (daily)        |
| `daily-verify.yml`          | Verifies the integrity of the cloud pipeline.           | Schedule (daily)        |
| `transformations-execute.yml` | Executes the dbt transformations.                       | Schedule (daily)        |
| `tsi-data-quality.yml`      | Runs data quality checks and sends alerts on failure.   | Schedule (daily)        |
| `dbt-run-test.yml`          | Runs dbt tests and checks data freshness.               | Push (dbt paths), Schedule |
| `deploy.yml`                | Deploys infrastructure changes via Terraform.           | Manual dispatch         |

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

*   `src/data_collection/daily_data_collector.py`: The main entry point for data collection. Fetches data and uploads to GCS.
*   `scripts/verify_cloud_pipeline.py`: Verifies that data exists and is consistent across GCS and BigQuery.
*   `scripts/check_data_quality.py`: Runs a battery of data quality checks against BigQuery data.
*   `scripts/merge_backfill_range.py`: Merges data from staging tables into the main fact table for a range of dates.

### Configuration

*   `config/base/paths.py`: Defines key paths for data storage and other resources.
*   `config/environments/*.py`: Environment-specific configurations (development vs. production).
*   `transformations/sql/*.sql`: The SQL files that define the data transformation logic.

---

## 🔒 Security

This project includes automated security scanning for Python dependencies using `pip-audit`. The security audit runs as part of the CI pipeline to identify known vulnerabilities.

For detailed information about security audit configuration and current status, see **[SECURITY_AUDIT.md](docs/SECURITY_AUDIT.md)**.

---

## 🤝 Contributing

1.  Fork the repository.
2.  Create a feature branch.
3.  Make your changes and add tests.
4.  Ensure all checks in `ci.yml` pass.
5.  Submit a pull request.
