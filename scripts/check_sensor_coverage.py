#!/usr/bin/env python3
"""Check TSI and WU sensor data coverage in BigQuery."""

from google.cloud import bigquery
from datetime import date, timedelta

client = bigquery.Client(project="durham-weather-466502")

print("=" * 80)
print("TSI & WEATHER UNDERGROUND DATA COVERAGE CHECK")
print("=" * 80)

# Check TSI raw data
print("\n1. TSI RAW DATA (tsi_raw_materialized):")
print("-" * 80)

tsi_query = """
SELECT 
    dt as date,
    COUNT(DISTINCT native_sensor_id) as devices,
    COUNT(*) as row_count
FROM `durham-weather-466502.sensors.tsi_raw_materialized`
WHERE dt >= DATE_SUB(CURRENT_DATE(), INTERVAL 10 DAY)
GROUP BY date
ORDER BY date DESC
LIMIT 10
"""

try:
    results = client.query(tsi_query).result()
    rows = list(results)
    if rows:
        for row in rows:
            print(f"  {row.date}: {row.devices} devices, {row.row_count:,} rows")
    else:
        print("  ⚠️  No recent data")
except Exception as e:
    print(f"  ❌ Error: {str(e)[:200]}")

# Check WU raw data
print("\n2. WEATHER UNDERGROUND RAW DATA (wu_raw_materialized):")
print("-" * 80)

wu_query = """
SELECT 
    DATE(ts) as date,
    COUNT(DISTINCT native_sensor_id) as stations,
    COUNT(*) as row_count
FROM `durham-weather-466502.sensors.wu_raw_materialized`
WHERE DATE(ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 10 DAY)
GROUP BY date
ORDER BY date DESC
LIMIT 10
"""

try:
    results = client.query(wu_query).result()
    rows = list(results)
    if rows:
        for row in rows:
            print(f"  {row.date}: {row.stations} stations, {row.row_count:,} rows")
    else:
        print("  ⚠️  No recent data")
except Exception as e:
    print(f"  ❌ Error: {str(e)[:200]}")

# Check transformed sensor_readings_long
print("\n3. TRANSFORMED DATA (sensor_readings_long):")
print("-" * 80)

transformed_query = """
SELECT 
    timestamp_date as date,
    source,
    COUNT(DISTINCT native_sensor_id) as sensors,
    COUNT(*) as row_count
FROM `durham-weather-466502.sensors.sensor_readings_long`
WHERE timestamp_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 10 DAY)
GROUP BY date, source
ORDER BY date DESC, source
LIMIT 20
"""

try:
    results = client.query(transformed_query).result()
    rows = list(results)
    if rows:
        current_date = None
        for row in rows:
            if row.date != current_date:
                if current_date is not None:
                    print()
                current_date = row.date
                print(f"  {row.date}:")
            print(f"    {row.source:3s}: {row.sensors} sensors, {row.row_count:,} rows")
    else:
        print("  ⚠️  No recent data")
except Exception as e:
    print(f"  ❌ Error: {str(e)[:200]}")

# Check for data gaps
print("\n4. CHECKING FOR GAPS:")
print("-" * 80)

gap_query = """
WITH date_series AS (
  SELECT date
  FROM UNNEST(GENERATE_DATE_ARRAY(
    DATE_SUB(CURRENT_DATE(), INTERVAL 10 DAY),
    CURRENT_DATE()
  )) as date
),
tsi_coverage AS (
  SELECT 
    dt as date,
    COUNT(*) as tsi_rows
  FROM `durham-weather-466502.sensors.tsi_raw_materialized`
  WHERE dt >= DATE_SUB(CURRENT_DATE(), INTERVAL 10 DAY)
  GROUP BY date
),
wu_coverage AS (
  SELECT 
    DATE(ts) as date,
    COUNT(*) as wu_rows
  FROM `durham-weather-466502.sensors.wu_raw_materialized`
  WHERE DATE(ts) >= DATE_SUB(CURRENT_DATE(), INTERVAL 10 DAY)
  GROUP BY date
)
SELECT 
  ds.date,
  COALESCE(tsi.tsi_rows, 0) as tsi_rows,
  COALESCE(wu.wu_rows, 0) as wu_rows,
  CASE 
    WHEN COALESCE(tsi.tsi_rows, 0) = 0 THEN '❌ TSI MISSING'
    WHEN COALESCE(wu.wu_rows, 0) = 0 THEN '❌ WU MISSING'
    WHEN COALESCE(tsi.tsi_rows, 0) = 0 AND COALESCE(wu.wu_rows, 0) = 0 THEN '❌ BOTH MISSING'
    ELSE '✅ OK'
  END as status
FROM date_series ds
LEFT JOIN tsi_coverage tsi ON ds.date = tsi.date
LEFT JOIN wu_coverage wu ON ds.date = wu.date
ORDER BY ds.date DESC
"""

try:
    results = client.query(gap_query).result()
    rows = list(results)
    if rows:
        for row in rows:
            status_icon = "❌" if "MISSING" in row.status else "✅"
            print(
                f"  {row.date}: TSI={row.tsi_rows:>6,} | WU={row.wu_rows:>6,} | {row.status}"
            )
    else:
        print("  ⚠️  No data")
except Exception as e:
    print(f"  ❌ Error: {str(e)[:200]}")

print("\n" + "=" * 80)
