# Oura Rings Data Import and BigQuery Export

This folder contains utilities to collect Oura Ring data for multiple residents and optionally export daily summaries to BigQuery.

Safe by default:

- Access tokens are loaded from per-resident `.env` files stored OUTSIDE the repo (see `PATHS.env_files_dir`).
- Output directories for JSON/CSV are OUTSIDE the repo by default.
- BigQuery export is disabled by default and runs in dry-run mode unless explicitly enabled.

## Files

- `cli.py`: Command-line interface for batch processing with argument support
- `oura_client.py`: Oura API client for authenticated requests
- `oura_collector.py`: Core data collection and processing logic
- `oura_transforms.py`: Data transformation utilities for flattening API responses
- `oura_bigquery_loader.py`: BigQuery export with dry-run support
- `oura_import_options.py`: Configuration for residents, dates, paths, and BigQuery settings
- `oura_variable_inspection.ipynb`: Educational Jupyter notebook showing how to inspect variables and debug (uses dummy data only)
- `README.md`: This documentation
- `.env.sample`: Example environment variables
- `.gitignore`: Protection for secrets and outputs

## Configure

1. Create per-resident token files outside this repo, named `pat_r<RESIDENT>.env` (e.g., `pat_r3.env`) with:

```
PERSONAL_ACCESS_TOKEN=your_oura_pat_here
```

By default these are expected under a directory like `../../../../Secure Files` relative to this folder. You can change `PATHS.env_files_dir` in `oura_import_options.py`.

2. Optionally set BigQuery env vars (only needed for real export):

```
# .env or shell env (no secrets required for dry-run)
BQ_PROJECT=your-gcp-project-id
BQ_LOCATION=US
```

## Enable BigQuery export (optional)

In `oura_import_options.py`, set:

```
OPTIONS["export_to_bigquery"] = True
OPTIONS["bq_dry_run"] = True  # set to False to perform real uploads

# Configure dataset / naming
OURA_BQ["dataset"] = "oura"
OURA_BQ["table_prefix"] = "oura"  # results in oura_daily_sleep, oura_daily_activity, oura_daily_readiness
```

When `bq_dry_run=True`, no network calls are made; the script will log what it would upload. Set `bq_dry_run=False` to perform real uploads using Google Application Default Credentials.

## Run

From the repo root:

```bash
python -m oura_rings.cli --residents 1 2 3 --export-bq --dry-run
```

This will:

- Fetch data for specified residents
- Save JSON and CSV outside the repo
- Optionally export daily DataFrames to BigQuery if enabled

## Public repo safety

- No Oura tokens are committed; token files live outside the repository.
- Default output and secrets locations are outside the repository.
- BigQuery uploads are disabled by default and use dry-run by default when enabled.

## Testing

Unit tests cover the loader transformation and dry-run behavior. To run the test suite:

```
pytest -q
```

Note: The module path uses dynamic importing in tests because this directory name contains a hyphen (`oura-rings`).
