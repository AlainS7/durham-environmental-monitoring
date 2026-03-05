#!/bin/bash
set -euo pipefail
# Batch run transformations for a date range

PROJECT="${GCP_PROJECT_ID:-durham-weather-466502}"
DATASET="${BQ_DATASET:-sensors}"
SQL_DIR="transformations/sql"
START_DATE="2025-07-04"
END_DATE="2025-10-02"

echo "=========================================="
echo "Running transformations for date range:"
echo "  Start: $START_DATE"
echo "  End:   $END_DATE"
echo "  Project: $PROJECT"
echo "  Dataset: $DATASET"
echo "=========================================="
echo ""

# Convert dates to epoch for iteration
start_epoch=$(date -d "$START_DATE" +%s)
end_epoch=$(date -d "$END_DATE" +%s)
current_epoch=$start_epoch

success_count=0
error_count=0
errors_file="/tmp/transformation_errors.log"
> "$errors_file"  # Clear errors file

while [ $current_epoch -le $end_epoch ]; do
    current_date=$(date -d "@$current_epoch" +%Y-%m-%d)
    
    echo "[$(date '+%H:%M:%S')] Processing $current_date..."
    
    if python scripts/run_transformations.py \
        --project "$PROJECT" \
        --dataset "$DATASET" \
        --dir "$SQL_DIR" \
        --date "$current_date" \
        --execute 2>&1 | tee -a /tmp/transformation_batch.log | grep -q "ERROR"; then
        echo "  ❌ Error processing $current_date"
        echo "$current_date - ERROR" >> "$errors_file"
        ((error_count++))
    else
        echo "  ✅ Completed $current_date"
        ((success_count++))
    fi
    
    # Move to next day
    current_epoch=$((current_epoch + 86400))
done

echo ""
echo "=========================================="
echo "TRANSFORMATION BATCH COMPLETE"
echo "  Success: $success_count dates"
echo "  Errors:  $error_count dates"
echo "=========================================="

if [ $error_count -gt 0 ]; then
    echo ""
    echo "Dates with errors:"
    cat "$errors_file"
fi

# Final verification
echo ""
echo "Verifying final table counts..."
bq query --use_legacy_sql=false --format=pretty '
SELECT 
    "sensor_readings_long" as table_name,
    MIN(DATE(ts)) as min_date,
    MAX(DATE(ts)) as max_date,
    COUNT(DISTINCT DATE(ts)) as days,
    COUNT(*) as total_rows
FROM `'$PROJECT'.'$DATASET'.sensor_readings_long`
UNION ALL
SELECT 
    "sensor_readings_hourly",
    MIN(DATE(ts)),
    MAX(DATE(ts)),
    COUNT(DISTINCT DATE(ts)),
    COUNT(*)
FROM `'$PROJECT'.'$DATASET'.sensor_readings_hourly`
UNION ALL
SELECT 
    "sensor_readings_daily",
    MIN(reading_date),
    MAX(reading_date),
    COUNT(DISTINCT reading_date),
    COUNT(*)
FROM `'$PROJECT'.'$DATASET'.sensor_readings_daily`
ORDER BY table_name'
