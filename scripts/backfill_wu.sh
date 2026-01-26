#!/usr/bin/env bash
# Backfill Weather Underground data for missing date ranges
# Missing: Nov 4-6, 2025 (3 days) and Nov 17, 2025 - Jan 21, 2026 (66 days)

set -euo pipefail

PROJECT_ID="durham-weather-466502"
JOB_NAME="weather-data-uploader"
REGION="us-east1"

# Cross-platform date command helpers
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

# Function to backfill a date range
backfill_range() {
    local START_DATE="$1"
    local END_DATE="$2"
    local RANGE_NAME="$3"
    
    echo ""
    echo "======================================"
    echo "WU Backfill $RANGE_NAME: $START_DATE to $END_DATE"
    echo "======================================"
    echo ""
    
    # Calculate days to backfill
    start_ts=$(get_date_unix "$START_DATE")
    end_ts=$(get_date_unix "$END_DATE")
    days=$(( (end_ts - start_ts) / 86400 + 1 ))
    
    echo "Total days to backfill: $days"
    echo ""
    read -p "Continue with $RANGE_NAME? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Skipped $RANGE_NAME"
        return 0
    fi
    
    # Run backfill
    cur_ts=$start_ts
    count=0
    failed_count=0
    while [ "$cur_ts" -le "$end_ts" ]; do
        d=$(format_date_from_unix "$cur_ts")
        count=$((count + 1))
        
        echo "[$count/$days] Executing job for $d..."
        
        # Update Cloud Run job with date-specific args
        gcloud run jobs update "$JOB_NAME" \
            --region "$REGION" \
            --project "$PROJECT_ID" \
            --args="src/data_collection/daily_data_collector.py","--start=$d","--end=$d" \
            --quiet >/dev/null 2>&1
        
        if timeout 900 gcloud run jobs execute "$JOB_NAME" \
            --region "$REGION" \
            --project "$PROJECT_ID" \
            --wait 2>&1 | tee /tmp/wu_backfill_${d}.log; then
            echo "  ✓ Success: $d"
        else
            echo "  ✗ Failed: $d (check /tmp/wu_backfill_${d}.log)"
            failed_count=$((failed_count + 1))
        fi
        
        cur_ts=$((cur_ts + 86400))
        
        # Small delay to avoid rate limits
        if [ "$cur_ts" -le "$end_ts" ]; then
            sleep 2
        fi
    done
    
    echo ""
    if [ "$failed_count" -eq 0 ]; then
        echo "✓ $RANGE_NAME: All $count dates succeeded!"
    else
        echo "⚠ $RANGE_NAME: $failed_count / $count dates failed"
    fi
    
    return 0
}

echo "======================================"
echo "WU Data Backfill - Missing Ranges"
echo "======================================"
echo ""
echo "This will backfill Weather Underground data for:"
echo "  1. Nov 4-6, 2025 (3 days)"
echo "  2. Nov 17, 2025 - Jan 21, 2026 (66 days)"
echo ""
echo "Total: 69 days"
echo ""

# Backfill first range (3 days)
backfill_range "2025-11-04" "2025-11-06" "Range 1"

# Backfill second range (66 days)  
backfill_range "2025-11-17" "2026-01-21" "Range 2"

# Restore job to default args
echo ""
echo "Restoring job default configuration..."
gcloud run jobs update "$JOB_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --args="src/data_collection/daily_data_collector.py" \
    --quiet >/dev/null 2>&1

echo ""
echo "======================================"
echo "WU Backfill Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Verify WU data in BigQuery:"
echo "   python3 /tmp/check_wu_gaps.py"
echo "2. Refresh WU materialized views if needed"
echo "3. Check Grafana dashboard for updated WU data"
