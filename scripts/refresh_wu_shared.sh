#!/bin/bash
# Refresh WU raw materialized table in sensors_shared (Grafana dataset)
# Part of daily Grafana data refresh pipeline
# Should run at 01:00 UTC after production data has been finalized

set -euo pipefail

PROJECT_ID="${BQ_PROJECT:-durham-weather-466502}"
DATASET_SHARED="${BQ_SHARED_DATASET:-sensors_shared}"
DATASET_PROD="${BQ_PROD_DATASET:-sensors}"

echo "Refreshing WU materialized view in ${PROJECT_ID}.${DATASET_SHARED}..."

if bq query \
  --project_id="$PROJECT_ID" \
  --nouse_legacy_sql \
  --quiet \
  << EOF
CREATE OR REPLACE TABLE \`${PROJECT_ID}.${DATASET_SHARED}.wu_raw_materialized\`
PARTITION BY DATE(ts)
AS
SELECT * FROM \`${PROJECT_ID}.${DATASET_PROD}.wu_raw_materialized\`
EOF
then
  echo "✓ WU shared materialized table refreshed successfully"
  echo "Completed at: $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
  exit 0
else
  echo "✗ Failed to refresh WU shared materialized table"
  exit 1
fi
