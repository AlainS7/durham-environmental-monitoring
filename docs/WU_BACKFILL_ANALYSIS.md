# Weather Underground (WU) Backfill Analysis

## Current Status

**Date Range:** July 4, 2025 → January 23, 2026  
**Total Rows:** 31,590  
**Distinct Days:** 135 (out of 204 expected)  
**Missing Days:** 69

## Missing Data Ranges

### Range 1: November 4-6, 2025

- **Duration:** 3 days
- **Status:** Missing

### Range 2: November 17, 2025 - January 21, 2026

- **Duration:** 66 days
- **Status:** Missing
- **Note:** Same gap as TSI data (already backfilled for TSI)

## Data Present

### November 2025

- Nov 1-3: ✅ (260, 260, 247 rows)
- Nov 4-6: ❌ **MISSING**
- Nov 7-16: ✅ (221-247 rows per day)
- Nov 17-30: ❌ **MISSING**

### December 2025

- All dates: ❌ **MISSING**

### January 2026

- Jan 1-21: ❌ **MISSING**
- Jan 22-23: ✅ (228 rows per day)

## Backfill Script

**Location:** [scripts/backfill_wu.sh](scripts/backfill_wu.sh)

**Usage:**

```bash
bash scripts/backfill_wu.sh
```

**What it does:**

1. Prompts for confirmation for Range 1 (3 days)
2. Prompts for confirmation for Range 2 (66 days)
3. For each date:
   - Updates Cloud Run job with `--start` and `--end` args
   - Executes `weather-data-uploader` job
   - Waits for completion
   - Logs to `/tmp/wu_backfill_YYYY-MM-DD.log`
4. Restores Cloud Run job to default configuration

**Estimated Time:**

- Range 1: ~5 minutes (3 days × ~90 seconds/job)
- Range 2: ~2 hours (66 days × ~90 seconds/job)
- **Total: ~2 hours**

## Verification Commands

### Check WU data coverage

```bash
python3 /tmp/check_wu_gaps.py
```

### Verify specific dates in BigQuery

```bash
bq query --nouse_legacy_sql "
SELECT DATE(ts) as date, COUNT(*) as row_count
FROM \`durham-weather-466502.sensors.wu_raw_materialized\`
WHERE DATE(ts) BETWEEN '2025-11-04' AND '2025-11-06'
   OR DATE(ts) BETWEEN '2025-11-17' AND '2026-01-21'
GROUP BY 1
ORDER BY 1
"
```

### Check total WU rows after backfill

```bash
bq query --nouse_legacy_sql "
SELECT
  MIN(DATE(ts)) as min_date,
  MAX(DATE(ts)) as max_date,
  COUNT(*) as total_rows,
  COUNT(DISTINCT DATE(ts)) as distinct_days
FROM \`durham-weather-466502.sensors.wu_raw_materialized\`
"
```

**Expected after backfill:**

- Distinct Days: 204 (135 + 69 missing)
- Total Rows: ~48,000 (31,590 + ~16,410 from backfill, assuming ~238 rows/day)

## WU vs TSI Comparison

| Metric          | WU                        | TSI                       | Match?               |
| --------------- | ------------------------- | ------------------------- | -------------------- |
| Min Date        | 2025-07-04                | 2025-07-07                | Different            |
| Max Date        | 2026-01-23                | 2026-01-23                | ✅ Same              |
| Missing Range 1 | Nov 4-6 (3 days)          | N/A                       | WU only              |
| Missing Range 2 | Nov 17 - Jan 21 (66 days) | Nov 17 - Jan 21 (66 days) | ✅ Same              |
| Rows per day    | ~234                      | ~6,300                    | Different (expected) |

**Root Cause:** Both TSI and WU data collection stopped on November 16, 2025 and resumed on January 22, 2026. The 3-day gap (Nov 4-6) is WU-specific.

## Next Steps

1. **Run WU backfill:**

   ```bash
   cd /Users/alainsoto/Projects/Developer/work/github.com/AlainS7/durham-environmental-monitoring
   bash scripts/backfill_wu.sh
   ```

2. **Verify completion:**

   ```bash
   python3 /tmp/check_wu_gaps.py
   ```

3. **Optional: Refresh WU views**

   ```bash
   # If you have WU materialized views similar to TSI
   bq query --nouse_legacy_sql "
   CREATE OR REPLACE TABLE \`durham-weather-466502.sensors_shared.wu_raw_materialized\`
   AS SELECT * FROM \`durham-weather-466502.sensors_shared.wu_raw_view\`
   "
   ```

4. **Update Grafana dashboards** with WU data

## Notes

- WU collection uses the same Cloud Run job as TSI (`weather-data-uploader`)
- The job collects both TSI and WU data when executed with `--source=all` (default)
- The backfill script uses the same approach as TSI backfill
- macOS date command compatibility already included
- Logs saved to `/tmp/wu_backfill_YYYY-MM-DD.log` for troubleshooting
