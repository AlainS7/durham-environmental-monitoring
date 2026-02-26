# BigQuery Refresh Cost Analysis: Daily vs Weekly Grafana Updates

## Current State

### sensors (Production Dataset)

- `tsi_raw_materialized`: 1,378,113 rows, ~365 MB
- `wu_raw_materialized`: 32,046 rows, ~8 MB

### sensors_shared (Grafana Dataset)

- `tsi_raw_materialized`: 1,378,113 rows (daily refresh via bash script)
- `wu_raw_view`: VIEW pointing to sensors.wu_raw_materialized (no materialized copy)

---

## Refresh Strategies Compared

### Strategy 1: Weekly Refresh (CURRENT FOR GRAFANA)

**Frequency**: 1 refresh per week (Monday 01:00 UTC)

**TSI Refresh Query**:

```sql
CREATE OR REPLACE TABLE sensors_shared.tsi_raw_materialized
PARTITION BY DATE(ts)
CLUSTER BY native_sensor_id AS
SELECT * FROM sensors.tsi_raw_materialized;
```

**Estimated Cost**:

- Query scans: 1,378,113 rows × ~265 bytes/row ≈ 365 MB per refresh
- 52 refreshes/year
- BigQuery cost: $0.70/TB scanned
  - **365 MB × 52 × $0.70/TB = $13.33/year** (negligible)

---

### Strategy 2: Daily Refresh (RECOMMENDED)

**Frequency**: 1 refresh per day (01:00 UTC)

**Same TSI Query**, runs 365 times/year

**Estimated Cost**:

- Same query: 365 MB per refresh
- 365 refreshes/year
- BigQuery cost: $0.70/TB scanned
  - **365 MB × 365 × $0.70/TB = $93.05/year**

**Cost Difference**: $93.05 - $13.33 = **$79.72/year extra** (~$6.64/month)

**Alternative Cost Model** (using on-demand pricing):

- 365 MB × 365 days = 133 GB/year = 0.133 TB/year
- 0.133 TB × $0.70/TB = **$0.093/month** (under free tier)

---

## New Requirement: WU Materialization in sensors_shared

### Adding WU Refresh (Daily)

```sql
CREATE OR REPLACE TABLE sensors_shared.wu_raw_materialized
PARTITION BY DATE(ts)
AS
SELECT * FROM sensors.wu_raw_materialized;
```

**Additional Cost**:

- Query scans: 32,046 rows × ~200 bytes/row ≈ 8 MB per refresh
- 365 refreshes/year
- BigQuery cost: 8 MB × 365 × $0.70/TB = **$2.05/year**

---

## Total Cost Summary

| Strategy            | TSI Refresh | WU Refresh | Total Annual | Monthly   |
| ------------------- | ----------- | ---------- | ------------ | --------- |
| **Weekly TSI Only** | $13.33      | $0         | $13.33       | $1.11     |
| **Daily TSI Only**  | $93.05      | $0         | $93.05       | $7.75     |
| **Daily TSI + WU**  | $93.05      | $2.05      | **$95.10**   | **$7.92** |

---

## Key Factors & Tradeoffs

### Reasons to Choose DAILY Refresh

1. **Grafana Real-Time Visibility** (Your requirement)
   - Users can see yesterday's complete daily data
   - No lag between production and Grafana views
   - Matches your "check the last day's daily" requirement

2. **Minimal Cost Impact**
   - $7.92/month for both TSI + WU is negligible
   - Under BigQuery free tier (1 TB/month free)
   - Less than 1/10th of most cloud budgets

3. **Data Freshness**
   - 24-hour lag is acceptable for analytical Grafana dashboards
   - Better than weekly for trend detection
   - Enables daily monitoring without hitting production queries

4. **Implementation Simplicity**
   - Use same pattern as current TSI refresh script
   - Both TSI and WU use identical materialization logic
   - No complex scheduling needed

### Reasons to Stay WEEKLY

1. **Cost Savings**: $79.72/year (only $6.64/month difference)
2. **Query Reduction**: 52 queries/year vs 365 queries/year
3. **Grafana Acceptable**: Weekly data is fine for most dashboards

---

## Recommendation: DAILY REFRESH ✅

**Why Daily is Better for Your Use Case**:

1. You explicitly want "to check the last day's daily" in Grafana
2. Cost is negligible ($7.92/month total)
3. Aligns with your daily data ingestion pipeline
4. No technical barriers
5. Matches business requirement for real-time visibility

**Implementation**:

- Create refresh script for WU (mirror of TSI script)
- Run both at 01:00 UTC daily via GitHub Actions
- Monitor query execution times (expect <5 seconds each)

---

## Implementation Steps

### 1. Add WU Materialization to sensors_shared

```sql
-- File: create_wu_materialized_shared.sql
CREATE OR REPLACE TABLE sensors_shared.wu_raw_materialized
PARTITION BY DATE(ts)
AS
SELECT * FROM sensors.wu_raw_materialized;
```

### 2. Create Daily Refresh Script

```bash
#!/bin/bash
# scripts/refresh_wu_shared.sh
set -euo pipefail

bq query --nouse_legacy_sql << 'EOF'
CREATE OR REPLACE TABLE `durham-weather-466502.sensors_shared.wu_raw_materialized`
PARTITION BY DATE(ts)
AS
SELECT * FROM `durham-weather-466502.sensors.wu_raw_materialized`;
EOF

echo "✓ WU shared table refreshed at $(date)"
```

### 3. Add to GitHub Actions Workflow

```yaml
# .github/workflows/daily-refresh-shared.yml
name: Daily Refresh Shared Tables

on:
  schedule:
    - cron: "0 1 * * *" # 01:00 UTC daily

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Auth to GCP
        uses: google-github-actions/auth@v2
        with:
          credentials_json: "${{ secrets.GCP_SA_KEY_JSON }}"

      - name: Refresh TSI shared
        run: bash scripts/refresh_tsi_shared.sh

      - name: Refresh WU shared
        run: bash scripts/refresh_wu_shared.sh

      - name: Upload logs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: refresh-logs
          path: "*.log"
```

---

## Monitoring & Alerts

```bash
# Query to monitor refresh performance
SELECT
  creation_time,
  table_id,
  row_count,
  size_bytes / 1024 / 1024 as size_mb
FROM sensors_shared.INFORMATION_SCHEMA.TABLES
WHERE table_id LIKE '%materialized'
ORDER BY creation_time DESC;
```

---

## Conclusion

**Daily refresh of both TSI and WU in sensors_shared costs $7.92/month and perfectly aligns with your requirement to have current Grafana views that show "the last day's daily" data.**

The cost is negligible and the implementation is straightforward. Recommended: **Implement Daily Refresh Strategy** ✅
