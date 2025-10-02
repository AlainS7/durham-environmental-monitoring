# Historical Data Backfill Summary

**Date Completed**: October 2, 2025  
**Date Range**: July 4 - October 2, 2025 (91 days)

## Overview

Successfully completed a 90-day historical backfill of environmental sensor data for Durham's monitoring network, collecting data from both Weather Underground (WU) weather stations and TSI Link air quality sensors.

## Data Collection Results

### Weather Underground (WU)
- **Files**: 92 daily parquet files
- **Total Observations**: 3,748 readings
- **Stations**: 13 weather stations
- **Coverage**: 100% (Jul 4 - Oct 2, 2025)
- **Metrics**: temperature, humidity, precipitation, wind, solar radiation, UV

### TSI Link (Air Quality)
- **Files**: 90 daily parquet files  
- **Total Observations**: 188,076 readings
- **Sensors**: 35 air quality devices
- **Coverage**: 98.9% (missing Aug 31 & Sep 1 due to API data unavailability)
- **Metrics**: PM2.5, temperature, humidity

## Storage Architecture

```
GCS Bucket: gs://sensor-data-to-bigquery/raw/
├── source=WU/
│   └── agg=raw/
│       └── dt=YYYY-MM-DD/
│           └── WU-YYYY-MM-DD.parquet (92 files)
└── source=TSI/
    └── agg=raw/
        └── dt=YYYY-MM-DD/
            └── TSI-YYYY-MM-DD.parquet (90 files)
```

### BigQuery Tables

**External Tables** (auto-query GCS parquet files):
- `wu_raw_external`: 3,748 rows accessible
- `tsi_raw_external`: 188,076 rows accessible

**Materialized Tables**:
- `wu_raw_materialized`: Contains Sep 16-19 data only (original baseline)
- `tsi_raw_materialized`: Contains Sep 16-19 data only (original baseline)

**Transformed Tables** (processed via daily transformations):
- `sensor_readings_long`: 3,456 rows (Sep 16-19 only)
- `sensor_readings_hourly`: 3,456 rows (Sep 16-19 only)
- `sensor_readings_daily`: 192 rows (Sep 16-19 only)

## Important Notes

### Data Accessibility
✅ **All backfilled raw data is fully accessible** via BigQuery external tables (`wu_raw_external`, `tsi_raw_external`)  
✅ External tables use wildcard patterns to auto-discover all parquet files in GCS  
✅ Can query the full 91-day range directly from external tables

### Materialized Tables Status
⚠️ The materialized tables (`wu_raw_materialized`, `tsi_raw_materialized`) were not automatically populated with backfilled data because:
1. Data collection writes directly to GCS (not BigQuery)
2. Parquet schema evolution caused type inconsistencies across date ranges
3. Requires manual schema alignment or incremental daily ingestion

### Transformation Status
⚠️ Downstream transformed tables (`sensor_readings_long`, `_hourly`, `_daily`) only contain the original Sep 16-19 baseline because:
1. Transformation SQL reads from materialized tables (not external tables)
2. Ran 91 daily transformations, but they only processed data present in materialized tables
3. Would need to either:
   - Populate materialized tables from external tables (schema issues)
   - Modify transformation SQL to read from external tables
   - Use daily ingestion pipeline to populate materialized tables incrementally

## Automation Status

### Daily Workflows (GitHub Actions)
✅ **Daily Ingestion** (`daily-ingest.yml`): Runs at 06:45 UTC  
✅ **Daily Transformations** (`transformations-execute.yml`): Runs at 07:25 UTC  
✅ **Daily Maintenance** (`maintenance.yml`): Runs at 02:00 UTC

### Validated Components
✅ Production API credentials stored in Secret Manager:
  - `tsi_creds` (version 6): TSI Link API key/secret
  - `wu_api_key` (version 13): Weather Underground API key
  
✅ Data collection script (`daily_data_collector.py`):
  - Successfully fetches from both APIs
  - Writes to GCS with proper partitioning
  - Handles date ranges via `--start` / `--end` arguments

✅ GCS-to-BigQuery pipeline:
  - External tables configured with wildcard URIs
  - Auto-detects new parquet files
  - Proper partition pruning by date

## Production Usage Recommendations

### For Analytics & Reporting
**Recommended**: Query external tables directly for full 91-day historical access:
```sql
-- Example: Get all PM2.5 readings for July 2025
SELECT 
  TIMESTAMP_MICROS(CAST(timestamp / 1000 AS INT64)) as ts,
  native_sensor_id,
  pm2_5
FROM `durham-weather-466502.sensors.tsi_raw_external`
WHERE DATE(TIMESTAMP_MICROS(CAST(timestamp / 1000 AS INT64))) 
  BETWEEN '2025-07-01' AND '2025-07-31'
  AND pm2_5 IS NOT NULL
```

### For Ongoing Data Collection
**Status**: ✅ Fully operational
- Daily workflow will continue collecting new data automatically
- New data writes to GCS → external tables (immediately queryable)
- Transformations run daily but only process materialized table data

### For Backfill of Transformed Tables (Optional)
If you need the full 91 days in transformed tables (`sensor_readings_long`, etc.), options:

1. **Re-run daily ingestion for each historical date** (recommended):
   ```bash
   # Triggers full pipeline: GCS → materialized → transformations
   gh workflow run daily-ingest.yml --field start_date=2025-07-04 --field end_date=2025-07-18
   ```

2. **Modify transformation SQL** to read from external tables instead of materialized

3. **Manual materialized table population** (requires schema alignment fixes)

## Validation Performed

✅ Verified 91 dates generated: Jul 4 - Oct 2, 2025  
✅ Confirmed 92 WU files uploaded (one date has duplicate, cleaned)  
✅ Confirmed 90 TSI files uploaded (expected: Aug 31 & Sep 1 have no API data)  
✅ External tables query successfully across full date range  
✅ Row counts: 3,748 WU + 188,076 TSI = 191,824 total observations  
✅ API credentials tested and working  
✅ GitHub Actions workflows validated (schedule + manual trigger)

## Files Modified

- `.gitignore`: Added dbt artifacts exclusions
- `transformations/dbt/profiles.yml`: Created for local dbt testing (gitignored)

## Cleanup Actions Taken

- Removed problematic smoke test file: `WU-2025-08-26-smoketest.parquet`
- Generated temporary date list: `/tmp/backfill_dates.txt` (not committed)
- Transformation logs: `/tmp/transformation_run.log` (not committed)

## Next Steps (Optional)

1. **If full transformed table backfill needed**: Use daily ingestion workflow for historical dates
2. **Monitor daily automation**: Check workflow runs in GitHub Actions tab
3. **Schema evolution**: Consider enforcing consistent parquet schema for future ingestions
4. **Materialized table strategy**: Decide if materialized tables are needed or external tables sufficient

---
**Backfill Completed**: October 2, 2025 20:22 UTC  
**Duration**: ~23 minutes (6 chunks × ~4 minutes each)  
**Success Rate**: 100% for available data
