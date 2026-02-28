#!/usr/bin/env bash
# Backfill TSI and/or WU data from Nov 17, 2025 to current date
# Usage:
#   bash backfill_catchup.sh              # Backfill both TSI and WU (default)
#   bash backfill_catchup.sh --source tsi # Backfill only TSI
#   bash backfill_catchup.sh --source wu  # Backfill only WU
#   bash backfill_catchup.sh tsi          # Backward-compatible positional source

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-durham-weather-466502}"
JOB_NAME="weather-data-uploader"
REGION="us-east1"
SOURCE="all"

usage() {
    cat >&2 <<EOF
Usage:
  $(basename "$0")                    # Backfill both TSI and WU (default)
  $(basename "$0") --source tsi       # Backfill only TSI
  $(basename "$0") --source wu        # Backfill only WU
  $(basename "$0") [all|tsi|wu]       # Backward-compatible positional source
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --source)
            if [[ $# -lt 2 ]]; then
                echo "Error: --source requires a value (all|tsi|wu)" >&2
                usage
                exit 1
            fi
            SOURCE="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        all|tsi|wu)
            SOURCE="$1"
            shift
            ;;
        *)
            echo "Error: Unknown argument: $1" >&2
            usage
            exit 1
            ;;
    esac
done

SOURCE="$(printf '%s' "$SOURCE" | tr '[:upper:]' '[:lower:]')"
case "$SOURCE" in
    all|tsi|wu) ;;
    *)
        echo "Error: Invalid source '$SOURCE' (expected all|tsi|wu)" >&2
        usage
        exit 1
        ;;
esac

# Cross-platform date command helper
get_date_unix() {
    # Returns Unix timestamp for a date
    if date --version >/dev/null 2>&1; then
        # GNU date
        date -u -d "$1" +%s
    else
        # BSD date (macOS)
        date -j -u -f "%Y-%m-%d" "$1" +%s
    fi
}

format_date_from_unix() {
    # Converts Unix timestamp to YYYY-MM-DD
    if date --version >/dev/null 2>&1; then
        # GNU date
        date -u -d @"$1" +%F
    else
        # BSD date (macOS)
        date -j -u -r "$1" +%F
    fi
}

get_yesterday() {
    # Returns yesterday's date in YYYY-MM-DD
    if date --version >/dev/null 2>&1; then
        # GNU date
        date -u -d "yesterday" +%F
    else
        # BSD date (macOS)
        date -u -v-1d +%F
    fi
}

# Start from day after last data (Nov 17, 2025) to yesterday
START_DATE="2025-11-17"
END_DATE=$(get_yesterday)

echo "======================================"
echo "Backfill ($SOURCE): $START_DATE to $END_DATE"
echo "======================================"
echo ""

# Calculate days to backfill
start_ts=$(get_date_unix "$START_DATE")
end_ts=$(get_date_unix "$END_DATE")
days=$(( (end_ts - start_ts) / 86400 + 1 ))

echo "Total days to backfill: $days"
echo ""
read -p "Continue? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted"
    exit 0
fi

# Run backfill
cur_ts=$start_ts
count=0
while [ "$cur_ts" -le "$end_ts" ]; do
    d=$(format_date_from_unix "$cur_ts")
    count=$((count + 1))
    
    echo "[$count/$days] Executing job for $d..."
    
    # Pass per-day arguments directly to execution to avoid mutating job
    # definition on every loop iteration.
    
    if timeout 900 gcloud run jobs execute "$JOB_NAME" \
        --region "$REGION" \
        --project "$PROJECT_ID" \
        --args="src/data_collection/daily_data_collector.py,--start=$d,--end=$d,--source=$SOURCE" \
        --wait 2>&1 | tee /tmp/backfill_${d}.log; then
        echo "  ✓ Success: $d"
    else
        echo "  ✗ Failed: $d (check /tmp/backfill_${d}.log)"
    fi
    
    cur_ts=$((cur_ts + 86400))
    
    # Small delay to avoid rate limits
    if [ "$cur_ts" -le "$end_ts" ]; then
        sleep 2
    fi
done

echo ""
echo "======================================"
echo "Backfill complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Refresh materialized table: bash scripts/refresh_tsi_shared.sh"
echo "2. Verify in BigQuery:"
echo "   bq query --nouse_legacy_sql 'SELECT MAX(DATE(ts)) FROM \`durham-weather-466502.sensors.tsi_raw_materialized\`'"
echo "3. Check Grafana dashboard for updated data"
