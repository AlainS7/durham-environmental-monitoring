#!/bin/bash
# Backfill daily summaries after fixing the 7-day window bug
# This will restore all historical data from sensor_readings_long

set -e

# Configuration
PROJECT="${BQ_PROJECT:-durham-weather-466502}"
DATASET="${BQ_DATASET:-sensors}"
START_DATE="${1:-2025-07-04}"  # Default to July 4, 2025 (3+ months ago)
END_DATE="${2:-2025-09-30}"     # Default to September 30, 2025

echo "=========================================="
echo "Daily Summary Backfill"
echo "=========================================="
echo "Project: $PROJECT"
echo "Dataset: $DATASET"
echo "Date Range: $START_DATE to $END_DATE"
echo "=========================================="
echo

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "Error: 'uv' command not found. Please install uv first."
    exit 1
fi

# Get list of dates to backfill
echo "Calculating dates to backfill..."
dates=$(python3 -c "
from datetime import datetime, timedelta
start = datetime.strptime('$START_DATE', '%Y-%m-%d')
end = datetime.strptime('$END_DATE', '%Y-%m-%d')
current = start
while current <= end:
    print(current.strftime('%Y-%m-%d'))
    current += timedelta(days=1)
")

# Count total dates
total=$(echo "$dates" | wc -l | tr -d ' ')
echo "Total dates to process: $total"
echo

# Process each date
count=0
failed=0
for date in $dates; do
    count=$((count + 1))
    echo "[$count/$total] Processing $date..."
    
    if uv run python scripts/run_transformations.py \
        --project "$PROJECT" \
        --dataset "$DATASET" \
        --date "$date" \
        --dir transformations/sql \
        --execute 2>&1 | grep -E "(Executed|Error)" || true; then
        echo "  ✓ Completed $date"
    else
        echo "  ✗ Failed $date"
        failed=$((failed + 1))
    fi
    
    # Brief pause to avoid rate limiting
    sleep 0.5
done

echo
echo "=========================================="
echo "Backfill Summary"
echo "=========================================="
echo "Total processed: $total"
echo "Failed: $failed"
echo "Success: $((total - failed))"
echo "=========================================="

if [ $failed -eq 0 ]; then
    echo "✓ All dates backfilled successfully!"
    exit 0
else
    echo "⚠ Some dates failed. Check logs above for details."
    exit 1
fi
