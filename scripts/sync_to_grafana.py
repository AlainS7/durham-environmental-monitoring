#!/usr/bin/env python3
"""Sync sensor data from production dataset to Grafana-accessible dataset.

Uses BigQuery Python client to copy tables and create views.
"""

from google.cloud import bigquery
from google.cloud.bigquery import CopyJob, LoadJobConfig
import sys

PROJECT = "durham-weather-466502"
PROD_DS = "sensors"
GRAFANA_DS = "sensors_shared"

client = bigquery.Client(project=PROJECT)

# Tables to copy
TABLES = [
    "sensor_readings_long",
    "sensor_readings_hourly",
    "sensor_readings_daily",
    "sensor_id_map",
    "residence_sensor_assignments",
]

print("=" * 50)
print("Syncing to Grafana Dataset (Python)")
print("=" * 50)
print(f"Project: {PROJECT}")
print(f"Source:  {PROD_DS}")
print(f"Target:  {GRAFANA_DS}")
print()

success = 0
failed = 0

# Copy tables
print("Copying tables...")
for table_name in TABLES:
    src = f"{PROJECT}.{PROD_DS}.{table_name}"
    dst = f"{PROJECT}.{GRAFANA_DS}.{table_name}"

    try:
        source_table = client.get_table(src)
        dest_table_id = dst
        job_config = bigquery.CopyJobConfig()
        job_config.write_disposition = bigquery.WriteDisposition.WRITE_TRUNCATE

        copy_job = client.copy_table(src, dest_table_id, job_config=job_config)
        copy_job.result()

        print(f"  {table_name}... ✅")
        success += 1
    except Exception as e:
        print(f"  {table_name}... ❌ {str(e)[:60]}")
        failed += 1

print()
print("=" * 50)
print("SYNC COMPLETE")
print(f"  Success: {success}")
print(f"  Failed:  {failed}")
print("=" * 50)

if failed == 0:
    print("\n✅ All tables synced to Grafana!")
    sys.exit(0)
else:
    print(f"\n❌ {failed} tables failed to sync.")
    sys.exit(1)
