# Grafana Colocation Analysis - Setup Guide

## ⚠️ Important: Grafana Dataset Access

**Grafana can ONLY query tables in the `sensors_shared` dataset** (not `sensors`).

All queries below use `sensors_shared`, which is automatically synced from the main `sensors` dataset via `scripts/sync_to_grafana.py`. This happens after each backfill completes.

**Example working query:**

```sql
SELECT ts as time, pm2_5, native_sensor_id
FROM `durham-weather-466502.sensors_shared.tsi_raw_materialized`
WHERE $__timeFilter(ts)
```

**What we've done:**

- ✅ Updated all 10 colocation queries to use `sensors_shared`
- ✅ Use calibrated metrics where available (pm2_5_calibrated, temperature_calibrated, etc.)
- ✅ Support Grafana time filter variables ($\_\_timeFilter)
- ✅ Queries can be copy-pasted directly into Grafana

---

## Overview

These SQL queries enable you to visualize and compare different sensor networks (Air Assure, Bluesky, Ambient) deployed at the same residence. Perfect for validating sensor accuracy and showing network agreement metrics.

---

## Setup Steps

### 1. Add 10 New Grafana Data Sources (One per Query)

Each query below becomes a separate data source in Grafana:

1. **Time Series Comparison** (Query 1)
2. **Correlation Scatter Plot** (Query 2)
3. **Statistical Metrics** (Query 3)
4. **Bland-Altman Plot** (Query 4)
5. **Hourly Response Time** (Query 5)
6. **Indoor/Outdoor Cross-Network** (Query 6)
7. **Three-Way Comparison Table** (Query 7)
8. **Performance Heatmap** (Query 8)
9. **Rolling 30-Day Correlation** (Query 9)
10. **Daily Range Consistency** (Query 10)

### 2. Create Dashboard: "Residence Colocation Analysis - RES-001"

#### Panel 1: Time Series (Network PM2.5 Over Time)

- **Query**: Query 1
- **Panel Type**: Time Series
- **Legend**: Show networks as different colors
- **Y-Axis**: PM2.5 (µg/m³)
- **Title**: "Air Assure vs Bluesky - 90 Day Trend"

#### Panel 2: Correlation Scatter Plot

- **Query**: Query 2
- **Panel Type**: Scatter plot (X, Y)
- **X-Axis**: air_assure_pm25
- **Y-Axis**: bluesky_pm25
- **Size**: difference_ug_m3
- **Title**: "Network Agreement (Perfect agreement = diagonal line)"
- **Optional**: Add reference line at y=x

#### Panel 3: Agreement Metrics

- **Query**: Query 3
- **Panel Type**: Stat (4 panels)
  - Panel A: Mean absolute difference
  - Panel B: Air Assure mean value
  - Panel C: Bluesky mean value
  - Panel D: Days of overlap
- **Title**: "Statistical Comparison"

#### Panel 4: Bland-Altman Plot

- **Query**: Query 4
- **Panel Type**: Scatter plot
- **X-Axis**: average_pm25 (mean of both readings)
- **Y-Axis**: difference_aa_minus_bs
- **Title**: "Bland-Altman Plot (Agreement Analysis)"
- **Note**: Points should cluster around Y=0 with ~95% within ±1.96 SD

#### Panel 5: Hourly Colocation (Recent Week)

- **Query**: Query 5
- **Panel Type**: Time Series
- **Y-Axis**: PM2.5 values
- **Title**: "Hourly Network Response - Last 7 Days"
- **Use for**: Detecting sensor lag or communication delays

#### Panel 6: Indoor vs Outdoor by Network

- **Query**: Query 6
- **Panel Type**: Time Series (multi-series)
- **Series**: One line per network-location combo (AA Indoor, AA Outdoor, BS Indoor, BS Outdoor, etc.)
- **Title**: "Network Location Response"
- **Insight**: Shows if networks respond differently indoors vs outdoors

#### Panel 7: Daily Comparison Table

- **Query**: Query 7
- **Panel Type**: Table
- **Columns**: Date, Air Assure, Bluesky, Ambient, AA vs BS Diff, BS vs AM Diff
- **Title**: "Daily Three-Way Comparison"
- **Sort**: Most recent first

#### Panel 8: Performance Heatmap

- **Query**: Query 8
- **Panel Type**: Heatmap
- **X-Axis**: day_of_week
- **Y-Axis**: network
- **Color**: avg_pm25
- **Title**: "Average PM2.5 by Network & Day of Week"
- **Insight**: Detects weekly patterns or network-specific biases

#### Panel 9: Rolling Correlation

- **Query**: Query 9
- **Panel Type**: Time Series
- **Y-Axis**: rolling_30day_correlation (0-1, higher = better agreement)
- **Threshold**: Add alert line at 0.8 (good agreement)
- **Title**: "30-Day Rolling Correlation (Network Drift Detection)"
- **Insight**: Downtrend = networks diverging; uptrend = converging

#### Panel 10: Daily Range / Consistency

- **Query**: Query 10
- **Panel Type**: Area chart
- **Series**: min (bottom), avg (middle), max (top) per network
- **Title**: "Daily Range by Network (Narrower = More Consistent)"
- **Insight**: Consistency indicator; wide range = noisy sensor

---

## Customization for Different Residences

To show a different residence, change this line in all queries:

```sql
WHERE residence_id = 'RES-001'  -- ← Change this
```

Replace `RES-001` with your target residence ID. You can find active residences:

```sql
SELECT DISTINCT residence_id, sensor_name, sensor_role
FROM `durham-weather-466502.sensors.residence_active_sensors`
ORDER BY residence_id;
```

---

## Copy-Paste for Different Residence

Once you've built panels for RES-001:

1. **In Grafana**, duplicate the entire dashboard
2. **Rename to**: "Residence Colocation Analysis - RES-002"
3. **Edit each panel's query**, change:
   ```sql
   WHERE residence_id = 'RES-001'
   ```
   to:
   ```sql
   WHERE residence_id = 'RES-002'
   ```
4. **Save as new dashboard**

Now you can view multiple residences side-by-side by opening two browser tabs!

---

## Quick Interpretation Guide

### What to Look For

| Visualization     | Good Sign                      | Warning Sign                             |
| ----------------- | ------------------------------ | ---------------------------------------- |
| **Time Series**   | Lines overlap closely          | Lines diverge significantly              |
| **Scatter Plot**  | Points along diagonal          | Points scattered far from diagonal       |
| **Mean Abs Diff** | < 2 µg/m³                      | > 5 µg/m³                                |
| **Bland-Altman**  | Points clustered around 0      | Points scattered; bias = non-zero center |
| **Hourly**        | Synchronized peaks/valleys     | Delayed or missing responses             |
| **Heatmap**       | Similar colors across networks | One network much higher/lower            |
| **Rolling Corr**  | ≥ 0.8 and stable               | < 0.7 or declining                       |
| **Daily Range**   | Narrow (consistent readings)   | Wide (noisy sensor)                      |

---

## Advanced Analysis

### Testing for Sensor Drift

Run this query monthly and look for trend:

```sql
-- Add to Grafana: Monthly average by network
SELECT
  EXTRACT(MONTH FROM day_ts) AS month,
  CASE
    WHEN sensor_name LIKE 'AA-%' THEN 'Air Assure'
    WHEN sensor_name LIKE 'BS-%' THEN 'Bluesky'
    WHEN sensor_name LIKE 'AM-%' THEN 'Ambient'
  END AS network,
  ROUND(AVG(avg_value), 2) AS monthly_avg_pm25
FROM `durham-weather-466502.sensors.residence_readings_daily`
WHERE residence_id = 'RES-001'
  AND metric_name = 'pm2_5'
  AND sensor_role = 'Indoor'
  AND EXTRACT(YEAR FROM day_ts) = 2026
GROUP BY month, network
ORDER BY month DESC, network;
```

**Expected**: Relatively flat lines (no drift); trending up/down = sensor aging

### Testing Calibration Impact

Compare raw vs calibrated metrics:

```sql
-- Show raw vs calibrated temperature from Air Assure
SELECT
  day_ts,
  ROUND(
    (SELECT avg_value FROM `durham-weather-466502.sensors.residence_readings_daily` r2
     WHERE r2.residence_id = r1.residence_id
       AND r2.metric_name = 'temperature'
       AND r2.sensor_name = r1.sensor_name
       AND r2.day_ts = r1.day_ts),
    2
  ) AS temperature_raw,
  ROUND(
    (SELECT avg_value FROM `durham-weather-466502.sensors.residence_readings_daily` r2
     WHERE r2.residence_id = r1.residence_id
       AND r2.metric_name = 'temperature_calibrated'
       AND r2.sensor_name = r1.sensor_name
       AND r2.day_ts = r1.day_ts),
    2
  ) AS temperature_calibrated
FROM `durham-weather-466502.sensors.residence_readings_daily` r1
WHERE residence_id = 'RES-001'
  AND sensor_name LIKE 'AA-%'
  AND metric_name = 'temperature'
  AND day_ts >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
ORDER BY day_ts DESC;
```

---

## Grafana Panel Settings

### For All Time Series Panels

- **Tooltip**: All series visible
- **Legend**: Right side, sortable
- **Y-Axis**: Auto scale with nice numbers
- **X-Axis**: Time
- **Threshold lines**: Add at network-specific norms if known

### For Scatter Plots

- **X/Y scales**: Auto
- **Size**: Third dimension (e.g., difference magnitude)
- **Color**: Network identifier
- **Tooltip**: Show all fields on hover

### For Tables

- **Sortable columns**: Yes
- **Searchable**: Yes
- **Pagination**: 25 rows per page
- **Column alignment**: Numbers right-aligned

---

## File Location

All queries available at:

```
docs/GRAFANA_COLOCATION_QUERIES.sql
```

Copy-paste any query directly into Grafana's BigQuery data source editor.
