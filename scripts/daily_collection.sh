#!/usr/bin/env bash
# Daily automation: collect new data + refresh materialized tables
# Run this via Cloud Scheduler at 2 AM daily

set -euo pipefail

PROJECT_ID="durham-weather-466502"
JOB_NAME="weather-data-uploader"
REGION="us-east1"

# Get yesterday's date (data is available ~6 hours delayed)
# Cross-platform date helper
if date --version >/dev/null 2>&1; then
    # GNU date (Linux/GitHub Actions)
    YESTERDAY=$(date -u -d "yesterday" +%F)
    CURRENT_DATE=$(date -u +%F)
    YESTERDAY_DATE=$(date -u -d "yesterday" +%F)
else
    # BSD date (macOS)
    YESTERDAY=$(date -u -v-1d +%F)
    CURRENT_DATE=$(date -u +%F)
    YESTERDAY_DATE=$(date -u -v-1d +%F)
fi

echo "[$(date)] Starting daily collection for $YESTERDAY"

# 1. Collect data for yesterday
echo "Step 1/3: Collecting WU + TSI data..."
if gcloud run jobs execute "$JOB_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --args="--start=$YESTERDAY","--end=$YESTERDAY" \
    --wait; then
    echo "  ✓ Data collection complete"
else
    echo "  ✗ Data collection failed"
    exit 1
fi

# 2. Refresh TSI materialized table in sensors_shared
echo "Step 2/3: Refreshing TSI materialized table..."
if bash "$(dirname "$0")/refresh_tsi_shared.sh"; then
    echo "  ✓ TSI refresh complete"
else
    echo "  ✗ TSI refresh failed"
    exit 1
fi

# 3. Validate data freshness
echo "Step 3/3: Validating data freshness..."
TSI_MAX=$(bq --project_id="$PROJECT_ID" query --nouse_legacy_sql --format=csv --use_legacy_sql=false \
    "SELECT MAX(DATE(ts)) FROM \`$PROJECT_ID.sensors_shared.tsi_raw_materialized\`" | tail -1)

WU_MAX=$(bq --project_id="$PROJECT_ID" query --nouse_legacy_sql --format=csv --use_legacy_sql=false \
    "SELECT MAX(DATE(ts)) FROM \`$PROJECT_ID.sensors_shared.wu_raw_view\`" | tail -1)

echo "  TSI latest date: $TSI_MAX"
echo "  WU latest date: $WU_MAX"

# Check if we're up to date (allow 1 day lag)
if [[ "$TSI_MAX" == "$YESTERDAY_DATE" || "$TSI_MAX" == "$CURRENT_DATE" ]]; then
    echo "  ✓ TSI data is current"
else
    echo "  ⚠ TSI data may be behind (latest: $TSI_MAX, expected: $YESTERDAY_DATE)"
fi

if [[ "$WU_MAX" == "$YESTERDAY_DATE" || "$WU_MAX" == "$CURRENT_DATE" ]]; then
    echo "  ✓ WU data is current"
else
    echo "  ⚠ WU data may be behind (latest: $WU_MAX, expected: $YESTERDAY_DATE)"
fi

echo "[$(date)] Daily collection complete!"
