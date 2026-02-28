UV?=uv
PY?=python
PKG_SRC=src

.PHONY: help lint test fmt run-collector load-bq run-transformations generate-sensor-assignments install create-external materialize e2e verify-outputs quality-check schema-validate sync-sharepoint-today sync-sharepoint-date sync-sharepoint-backfill

help:
	@echo "Targets:"
	@echo "  install                Create venv (uv) & sync deps"
	@echo "  lint                   Run ruff lint"
	@echo "  test                   Run pytest (unit & integration)"
	@echo "  fmt                    Run ruff format"
	@echo "  run-collector          Execute data collection (env controls)"
	@echo "  load-bq                Load a date partition to BigQuery"
	@echo "  run-transformations    Execute transformation SQL files"
	@echo "  generate-sensor-assignments  Generate gitignored residence assignment SQL with real sensor IDs"
	@echo "  create-external        Create or replace BQ external tables over GCS raw Parquet"
	@echo "  materialize            Materialize daily partitions from externals into native tables"
	@echo "  e2e                    End-to-end: collect -> materialize -> transformations"
	@echo "  verify-outputs         Print BigQuery counts per date for key tables"
	@echo "  quality-check          Run comprehensive data quality checks"
	@echo "  schema-validate        Validate TSI and WU schema definitions"
	@echo "  sync-sharepoint-today  Sync yesterday's parquet files to SharePoint"
	@echo "  sync-sharepoint-date   Sync specific date to SharePoint (requires DATE=YYYY-MM-DD)"
	@echo "  sync-sharepoint-backfill  Backfill date range to SharePoint (requires START & END)"

install:
	$(UV) venv
	$(UV) pip sync requirements.txt
	@if [ -f requirements-dev.txt ]; then $(UV) pip sync requirements-dev.txt; fi

lint:
	$(UV) run ruff check $(PKG_SRC) scripts

fmt:
	$(UV) run ruff format $(PKG_SRC) scripts

test:
	PYTHONPATH=$(PWD)/src $(UV) run pytest -q tests/unit tests/integration

run-collector:
	@# Example: make run-collector START=2025-08-01 END=2025-08-01 SOURCE=all SINK=gcs
	python -m src.data_collection.daily_data_collector --start $(START) --end $(END) --source $(SOURCE) --sink $(SINK) $(if $(AGG),--aggregate,) $(if $(AGG_INTERVAL),--agg-interval $(AGG_INTERVAL),)

load-bq:
	@# Required vars: DATE=YYYY-MM-DD SOURCE=all|WU|TSI AGG=raw|h
	$(UV) run python scripts/load_to_bigquery.py --date $(DATE) --source $(SOURCE) --agg $(AGG) --dataset $$BQ_DATASET --project $$BQ_PROJECT --bucket $$GCS_BUCKET --prefix $$GCS_PREFIX

run-transformations:
	@# Required vars: DATE=YYYY-MM-DD DATASET=sensors PROJECT overrides BQ_PROJECT if set
	$(UV) run python scripts/run_transformations.py --date $(DATE) --dataset $(DATASET) --project $${PROJECT:-$$BQ_PROJECT} --execute

generate-sensor-assignments:
	@# Generates transformations/sql/07_residence_sensor_assignments.sql (gitignored)
	@test -n "$${PROJECT:-$$BQ_PROJECT}" || (echo "PROJECT or BQ_PROJECT is required" && exit 1)
	@test -n "$${RAW_DATASET:-$$BQ_DATASET}" || (echo "RAW_DATASET or BQ_DATASET is required" && exit 1)
	$(UV) run python scripts/generate_residence_assignments.py --project $${PROJECT:-$$BQ_PROJECT} --raw-dataset $${RAW_DATASET:-$$BQ_DATASET} --execute

create-external:
	@# Uses env: BQ_PROJECT/BQ_DATASET/GCS_BUCKET/GCS_PREFIX
	$(UV) run python scripts/create_bq_external_tables.py --project $${PROJECT:-$$BQ_PROJECT} --dataset $${DATASET:-$$BQ_DATASET} --bucket $$GCS_BUCKET --prefix $${PREFIX:-$$GCS_PREFIX}

materialize:
	@# Required vars: START=YYYY-MM-DD END=YYYY-MM-DD DATASET (defaults to BQ_DATASET)
	$(UV) run python scripts/materialize_partitions.py --project $${PROJECT:-$$BQ_PROJECT} --dataset $${DATASET:-$$BQ_DATASET} --start $(START) --end $(END) --sources $${SOURCES:-all} --execute

e2e:
	@# Example: make e2e START=2025-09-13 END=2025-09-19 DATASET=sensors SOURCE=all SINK=gcs
	@test -n "$(START)" || (echo "START is required" && exit 1)
	@test -n "$(END)" || (echo "END is required" && exit 1)
	$(MAKE) run-collector START=$(START) END=$(END) SOURCE=$${SOURCE:-all} SINK=$${SINK:-gcs}
	$(MAKE) create-external PROJECT=$${PROJECT:-$$BQ_PROJECT} DATASET=$${DATASET:-$$BQ_DATASET}
	$(MAKE) materialize START=$(START) END=$(END) PROJECT=$${PROJECT:-$$BQ_PROJECT} DATASET=$${DATASET:-$$BQ_DATASET}
	# Run transformations for END date (use proc_date as END)
	$(MAKE) run-transformations DATE=$(END) DATASET=$${DATASET:-$$BQ_DATASET} PROJECT=$${PROJECT:-$$BQ_PROJECT}

verify-outputs:
	@# Required vars: START=YYYY-MM-DD END=YYYY-MM-DD DATASET (defaults from env)
	$(UV) run python scripts/verify_outputs.py --project $${PROJECT:-$$BQ_PROJECT} --dataset $${DATASET:-$$BQ_DATASET} --start $(START) --end $(END)

quality-check:
	@# Run data quality check locally
	$(UV) run python scripts/check_data_quality.py --days 1 --source both --dataset $${DATASET:-sensors}

schema-validate:
	@# Validate schema definitions
	$(UV) run python -c "from src.utils.schema_validation import TSI_EXPECTED_SCHEMA, WU_EXPECTED_SCHEMA; print(f'✓ Schemas valid: TSI={len(TSI_EXPECTED_SCHEMA)} fields, WU={len(WU_EXPECTED_SCHEMA)} fields')"

sync-sharepoint-today:
	@# Sync yesterday's data to SharePoint (auto-calculates date)
	@echo "Syncing yesterday's parquet files to SharePoint..."
	@DATE=$$(python3 -c "from datetime import datetime, timedelta, timezone; print((datetime.now(timezone.utc) - timedelta(days=1)).strftime('%Y-%m-%d'))") && \
	$(UV) run python scripts/sync_parquet_to_sharepoint.py --date $$DATE --sources TSI WU

sync-sharepoint-date:
	@# Sync specific date to SharePoint. Usage: make sync-sharepoint-date DATE=2026-02-11
	@test -n "$(DATE)" || (echo "DATE is required (format: YYYY-MM-DD)" && exit 1)
	@echo "$(DATE)" | grep -qE '^[0-9]{4}-[0-9]{2}-[0-9]{2}$$' || (echo "Invalid DATE format. Use YYYY-MM-DD." && exit 1)
	@echo "Syncing parquet files for $(DATE) to SharePoint..."
	$(UV) run python scripts/sync_parquet_to_sharepoint.py --date $(DATE) --sources $${SOURCES:-TSI WU}

sync-sharepoint-backfill:
	@# Backfill date range to SharePoint. Usage: make sync-sharepoint-backfill START=2025-07-07 END=2026-02-11
	@test -n "$(START)" || (echo "START is required (format: YYYY-MM-DD)" && exit 1)
	@test -n "$(END)" || (echo "END is required (format: YYYY-MM-DD)" && exit 1)
	@echo "Backfilling parquet files from $(START) to $(END) to SharePoint..."
	@echo "This may take a while for large date ranges..."
	$(UV) run python scripts/sync_parquet_to_sharepoint.py --start-date $(START) --end-date $(END) --sources $${SOURCES:-TSI WU}
