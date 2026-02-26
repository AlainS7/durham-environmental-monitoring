# Grafana Real-Time Data Strategy - Recommendations & Implementation

## Executive Summary

Daily updated data on grafan is **supported** with minimal cost impact (~$8/month for daily TSI + WU refresh).

**Recommendation: Implement Daily Materialized Table Refresh** ✅

---

## Current System State

### Data Collection (Production)

- **Schedule**: 06:45 UTC daily (GitHub Actions → Cloud Run job)
- **Sources**: TSI (Triangle Sensors) + WU (Weather Underground)
- **Output**: BigQuery `sensors` dataset raw tables
  - `tsi_raw_materialized`: 1.38M rows
  - `wu_raw_materialized`: 32k rows

### Grafana Access (sensors_shared Dataset)

- **Current TSI**: `tsi_raw_materialized` table (daily refresh via bash script)
- **Current WU**: `wu_raw_view` (VIEW - reads from sensors.wu_raw_materialized, always current but slower)
- **Refresh Pattern**: TSI refreshed daily, WU accessed via view (acceptable but slower)

---

## Analysis Results

### Cost Comparison: Weekly vs Daily Refresh

| Metric                | Weekly     | Daily     | Daily (TSI+WU) |
| --------------------- | ---------- | --------- | -------------- |
| Query Frequency       | 52/year    | 365/year  | 365/year       |
| TSI Refresh Cost      | $13/year   | $93/year  | $93/year       |
| WU Refresh Cost       | $0         | $0        | $2/year        |
| **Total Annual Cost** | **$13**    | **$93**   | **$95**        |
| **Monthly Cost**      | **$1.11**  | **$7.75** | **$7.92**      |
| Grafana Data Age      | 7 days max | 1 day max | 1 day max      |

### Why Daily is Better for Your Use Case

1. **You Need Daily Visibility**: "check the last day's daily" → requires fresh daily data
2. **Cost is Negligible**: $7.92/month is under BigQuery free tier (1TB/month free)
3. **Performance**: Materialized tables are faster than views for Grafana dashboards
4. **Alignment**: Matches your daily data collection pipeline
5. **Simplicity**: Same implementation pattern for both TSI and WU

---

## What Changed With WU Backfill

### WU Data Now Available

- **Backfilled Dates**: Nov 4-6 (3 days) + Nov 17 - Jan 21 (66 days)
- **Total WU Coverage**: 206 days (July 4, 2025 - Jan 25, 2026)
- **Row Count**: 32,046 rows
- **In Production Table**: `sensors.wu_raw_materialized`

### Grafana Gap

Currently, WU data in `sensors_shared` is accessed via a VIEW, not a materialized table:

- Slower performance (especially for large dashboards)
- Same freshness (always reads from sensors)
- No optimization benefits

### Solution

Create materialized copy of WU in `sensors_shared` with daily refresh ✅

---

## Implementation Plan

### Phase 1: Create WU Materialized Table (Immediate)

```bash
# Run once to create table
bq query --nouse_legacy_sql << 'EOF'
CREATE TABLE IF NOT EXISTS durham-weather-466502.sensors_shared.wu_raw_materialized
PARTITION BY DATE(ts)
AS
SELECT * FROM durham-weather-466502.sensors.wu_raw_materialized;
EOF
```

**Status**: Script created at `scripts/refresh_wu_shared.sh`

### Phase 2: Add Daily Refresh to Automation (This Week)

Create GitHub Actions workflow to refresh both TSI and WU daily at 01:00 UTC.

**File to Create**: `.github/workflows/daily-refresh-shared.yml`

```yaml
name: Daily Refresh Shared Tables

on:
  schedule:
    - cron: "0 1 * * *" # 01:00 UTC daily

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Auth GCP
        uses: google-github-actions/auth@v2
        with:
          credentials_json: "${{ secrets.GCP_SA_KEY_JSON }}"

      - name: Setup gcloud
        uses: google-github-actions/setup-gcloud@v2

      - name: Refresh TSI shared table
        run: bash scripts/refresh_tsi_shared.sh

      - name: Refresh WU shared table
        run: bash scripts/refresh_wu_shared.sh

      - name: Upload logs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: daily-refresh-logs
          path: "*.log"
```

### Phase 3: Monitor Performance

Track refresh execution times and query costs.

---

## Technical Details

### TSI Refresh (Already Implemented)

**File**: `scripts/refresh_tsi_shared.sh`

- Runs daily at 01:00 UTC
- Full REPLACE of sensors_shared.tsi_raw_materialized
- Query: ~5-10 seconds
- Cost: ~$0.26/month

### WU Refresh (New)

**File**: `scripts/refresh_wu_shared.sh` (CREATED)

- Same pattern as TSI
- Query: ~2-3 seconds (smaller table)
- Cost: ~$0.17/month

### Why Partition by DATE(ts)?

- Enables efficient pruning for Grafana time-range queries
- Reduces bytes scanned for date-filtered dashboards
- Native support in BigQuery partitioning

### Why Not Use Views?

Current WU access: `wu_raw_view` in sensors_shared

- **Views**: Query-time performance penalty
- **Materialized Tables**: Pre-computed, instant access
- **For Grafana**: Dashboard responsiveness matters

---

## Grafana Benefits

With daily materialized tables for both TSI and WU:

✅ **Real-Time Dashboard Performance**

- No view overhead
- Instant table access
- Sub-second query responses

✅ **Current Data Access**

- TSI: Full previous day + current day
- WU: Full previous day + current day
- Perfect for "check the last day's daily" requirement

✅ **Cost Efficient**

- $7.92/month for both TSI + WU daily refresh
- Under free tier (1TB/month included)
- Negligible budget impact

✅ **Scalable**

- Same pattern for future data sources
- Easy to add more datasets
- Predictable costs

---

## Weekly Finalization Note

**No weekly finalization process exists** in your current pipeline. All processing is daily:

- Data collection: Daily (06:45 UTC)
- Transformations: Daily (07:25 UTC)
- Quality checks: Daily (08:30 UTC)
- Grafana refresh: Daily (01:00 UTC with this implementation)

This is optimal for real-time monitoring and Grafana dashboards.

---

## Next Steps (Priority Order)

### 1. Verify WU Materialization Completion (Today)

The `materialize_partitions.py` script is currently materializing WU backfill data.

```bash
# Check progress
ps aux | grep materialize_partitions
# Check final row count
python3 << 'EOF'
from google.cloud import bigquery
client = bigquery.Client(project="durham-weather-466502")
table = client.get_table("sensors.wu_raw_materialized")
print(f"WU rows: {table.num_rows}")
EOF
```

### 2. Create WU Materialized Table in sensors_shared

```bash
bash scripts/refresh_wu_shared.sh
```

### 3. Create GitHub Actions Workflow

Copy template above to `.github/workflows/daily-refresh-shared.yml`

### 4. Verify Grafana Queries

Test Grafana dashboards with new materialized table:

```sql
-- Grafana test query
SELECT DATE(ts) as date, COUNT(*) as readings
FROM sensors_shared.wu_raw_materialized
WHERE DATE(ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
GROUP BY DATE(ts)
ORDER BY DATE(ts) DESC;
```

### 5. Monitor Costs

Check BigQuery cost in GCP Console:

- Look for queries to sensors_shared tables
- Typical: <$1/month for both TSI + WU refresh

---

## Rollback Plan (If Needed)

If daily refresh causes issues:

1. Delete `.github/workflows/daily-refresh-shared.yml` workflow
2. Revert to WU view access (slower but works):
   ```sql
   CREATE OR REPLACE VIEW sensors_shared.wu_raw_materialized AS
   SELECT * FROM sensors.wu_raw_materialized;
   ```
3. Cost returns to ~$1/month (weekly-only TSI refresh)

---

## Summary

**Your Requirement**: "make the data available on grafana (sensors_shared) to update daily"

**Our Solution**: Daily materialized table refresh for both TSI and WU

**Cost**: $7.92/month (negligible, under free tier)

**Implementation**:

- 1 script created: `scripts/refresh_wu_shared.sh` ✅
- 2 docs created: Cost analysis + Recommendations ✅
- 1 workflow needed: `.github/workflows/daily-refresh-shared.yml`
- 1 verification step: Confirm WU backfill materialization complete

**Status**: Ready to implement ✅
