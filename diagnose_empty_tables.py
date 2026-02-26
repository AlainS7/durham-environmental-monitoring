#!/usr/bin/env python3
"""Diagnose why transformation tables are empty."""

from google.cloud import bigquery

client = bigquery.Client(project="durham-weather-466502")

# 1. Check raw data
print("=" * 70)
print("1. RAW DATA SOURCE")
print("=" * 70)

query = "SELECT COUNT(*), MIN(CAST(sample_date AS DATE)), MAX(CAST(sample_date AS DATE)) FROM `durham-weather-466502.sensors.sensor_readings`"
result = list(client.query(query).result())[0]
print(f"sensor_readings: {result[0]:,} rows | {result[1]} to {result[2]}")

# 2. Check materialized source tables
print("\n" + "=" * 70)
print("2. MATERIALIZED SOURCE TABLES")
print("=" * 70)

for table_name in ["tsi_raw_materialized", "wu_raw_materialized"]:
    query = f"SELECT COUNT(*), MAX(CAST(sample_date AS DATE)) FROM `durham-weather-466502.sensors.{table_name}`"
    try:
        result = list(client.query(query).result())[0]
        print(f"{table_name:30} {result[0]:>10,} rows | latest: {result[1]}")
    except Exception as e:
        print(f"{table_name:30} ERROR")

# 3. Check transformation output tables
print("\n" + "=" * 70)
print("3. TRANSFORMATION OUTPUT TABLES")
print("=" * 70)

for table_name in [
    "sensor_readings_long",
    "sensor_readings_daily",
    "sensor_readings_hourly",
    "sensor_readings_daily_enriched",
]:
    query = f"SELECT COUNT(*) FROM `durham-weather-466502.sensors.{table_name}`"
    try:
        result = list(client.query(query).result())[0][0]
        status = "✅" if result > 0 else "❌"
        print(f"{table_name:35} {result:>10,} rows {status}")
    except Exception as e:
        print(f"{table_name:35} ERROR: {str(e)[:40]}")

# 4. Try running a single transformation for latest date
print("\n" + "=" * 70)
print("4. ATTEMPTING SINGLE TRANSFORMATION")
print("=" * 70)

# Get the latest date from raw data
query = "SELECT MAX(CAST(sample_date AS DATE)) FROM `durham-weather-466502.sensors.wu_raw_materialized`"
latest_date = list(client.query(query).result())[0][0]
print(f"Latest data date available: {latest_date}")

# Try a simple query from the transformation logic
query_test = f"""
SELECT 
  COUNT(*) as test_count,
  DATE(TIMESTAMP_MILLIS(CAST(sample_timestamp AS INT64))) as date_col
FROM `durham-weather-466502.sensors.tsi_raw_materialized`
WHERE DATE(TIMESTAMP_MILLIS(CAST(sample_timestamp AS INT64))) = DATE '{latest_date}'
GROUP BY date_col
"""

try:
    result = list(client.query(query_test).result())
    if result:
        print(f"Test query for {latest_date}: {result[0][0]:,} rows found")
    else:
        print(f"Test query for {latest_date}: NO ROWS")
except Exception as e:
    print(f"Test query failed: {e}")
