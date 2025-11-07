#!/usr/bin/env python3
"""Quick script to check Oura data coverage in BigQuery."""

from google.cloud import bigquery

client = bigquery.Client(project="durham-weather-466502")

tables = [
    "oura_daily_sleep",
    "oura_daily_activity",
    "oura_daily_readiness",
    "oura_daily_spo2",
    "oura_daily_stress",
    "oura_daily_cardiovascular_age",
]

print("Data coverage by table (recent 10 days):")
print("=" * 80)

for table_name in tables:
    query = f"""
    SELECT 
        DATE(day) as day,
        COUNT(DISTINCT resident) as residents,
        COUNT(*) as row_count
    FROM `durham-weather-466502.oura.{table_name}`
    WHERE day >= DATE_SUB(CURRENT_DATE(), INTERVAL 10 DAY)
    GROUP BY day
    ORDER BY day DESC
    LIMIT 10
    """

    try:
        results = client.query(query).result()
        row_list = list(results)
        if row_list:
            print(f"\n{table_name}:")
            for row in row_list:
                print(f"  {row.day}: {row.residents} residents, {row.row_count} rows")
        else:
            print(f"\n{table_name}: No recent data")
    except Exception as e:
        print(f"\n{table_name}: Error - {str(e)[:200]}")
