# Local Development Guide (with uv)

This project uses [uv](https://github.com/astral-sh/uv) for fast, reproducible Python workflows.

## 1. Initial Setup

### 1.1. Install uv

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 1.2. Create and Activate Virtual Environment

```sh
# Create the virtual environment
uv venv

# Activate the environment
source .venv/bin/activate
```

### 1.3. Install Dependencies

```sh
# Install development dependencies
uv pip sync requirements-dev.txt
```

## 2. Environment Configuration

### 2.1. Create `.env` File

The application uses a `.env` file to manage environment variables for local development. Create a `.env` file in the root of the project:

```
cp .env.example .env
```

### 2.2. Populate `.env` File

You will need to populate the `.env` file with the necessary credentials and configuration. The following variables are required:

```
# GCP Configuration
PROJECT_ID="your-gcp-project-id"
GCS_BUCKET="your-gcs-bucket-name"
GCS_PREFIX="sensor_readings"
BQ_PROJECT="your-gcp-project-id"
BQ_DATASET="sensors"
BQ_LOCATION="US"

# API Keys (store in a secure location, like GCP Secret Manager)
TSI_CLIENT_ID="your-tsi-client-id"
TSI_CLIENT_SECRET="your-tsi-client-secret"
WU_API_KEY="your-wu-api-key"

<!--- Deprecated: Local PostgreSQL/Cloud SQL setup is no longer required. All data operations use BigQuery. -->
DB_USER="your-db-user"
DB_PASSWORD="your-db-password"
DB_HOST="localhost"
DB_PORT="5432"
DB_NAME="durham_weather"
```

## 3. Running the Application

### 3.1. Data Collection

To run the data collection process locally, use the `make run-collector` command. You will need to provide the `START` and `END` dates, as well as the `SOURCE` and `SINK`.

```sh
# Example: Collect data for one day and save to GCS
make run-collector START=2025-10-06 END=2025-10-06 SOURCE=all SINK=gcs
```

### 3.2. Transformations

To run the data transformations locally, use the `make run-transformations` command. You will need to provide the `DATE` and `DATASET`.

```sh
# Example: Run transformations for one day
make run-transformations DATE=2025-10-06 DATASET=sensors
```

## 4. Local Database Setup (Deprecated)

**This section is deprecated.**

The project has migrated to a BigQuery-only pipeline. Local PostgreSQL or Cloud SQL setup is no longer required for development or testing. All data ingestion, transformation, and analytics are performed directly in BigQuery.

If you have legacy scripts or workflows referencing a local database, please update them to use BigQuery. See the main README and scripts for current usage patterns.

## 5. GCP Authentication

To access BigQuery and Cloud Storage locally, you need to authenticate with GCP.

### 5.1. Install the gcloud CLI

Follow the instructions [here](https://cloud.google.com/sdk/docs/install) to install the gcloud CLI.

### 5.2. Authenticate

Run the following command to authenticate with your GCP account:

```sh
gcloud auth application-default login
```

This will open a browser window to complete the authentication process.

## 6. Testing and Linting

To run tests and linting, use the following commands:

```sh
# Run pytest
uv run pytest

# Run ruff linter
uv run ruff check .

# Run ruff formatter
uv run ruff format .
```
