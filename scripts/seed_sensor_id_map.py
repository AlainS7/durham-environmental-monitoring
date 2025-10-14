#!/usr/bin/env python3
"""Seed identity mapping into sensor_id_map for all known native_sensor_id values.

By default, seeds from sensor_readings_long and sensor_readings_daily to capture all
sensors seen historically. Safe to re-run; only inserts rows that don't exist.

Usage:
  python scripts/seed_sensor_id_map.py --project durham-weather-466502 --dataset sensors [--execute]

Without --execute it prints the SQL only.
"""
from __future__ import annotations
import argparse
from google.cloud import bigquery
from google.api_core.exceptions import NotFound

CREATE_TABLE_SQL = """-- Ensure target table exists
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.sensor_id_map` (
    sensor_id STRING NOT NULL,
    native_sensor_id STRING NOT NULL,
    effective_start_date DATE,
    effective_end_date DATE,
    source STRING,
    updated_at TIMESTAMP
);
"""
INSERT_SQL_TEMPLATE = """
INSERT INTO `{project}.{dataset}.sensor_id_map` (sensor_id, native_sensor_id, source, updated_at)
SELECT DISTINCT native_sensor_id AS sensor_id, native_sensor_id, source, CURRENT_TIMESTAMP()
FROM (
  {sources_sql}
) s
LEFT JOIN `{project}.{dataset}.sensor_id_map` m USING (native_sensor_id)
WHERE m.native_sensor_id IS NULL
"""


def table_exists(client: bigquery.Client, table_fqdn: str) -> bool:
    try:
        client.get_table(table_fqdn)
        return True
    except NotFound:
        return False


def ensure_table(client: bigquery.Client, project: str, dataset: str) -> None:
    """Ensure `{project}.{dataset}.sensor_id_map` exists, creating with API if missing.

    Uses the BigQuery API to create the table with a fixed schema. Falls back to DDL
    only if API creation is not available.
    """
    table_id = f"{project}.{dataset}.sensor_id_map"
    try:
        client.get_table(table_id)
        return
    except NotFound:
        # Define schema explicitly
        schema = [
            bigquery.SchemaField("sensor_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("native_sensor_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("effective_start_date", "DATE", mode="NULLABLE"),
            bigquery.SchemaField("effective_end_date", "DATE", mode="NULLABLE"),
            bigquery.SchemaField("source", "STRING", mode="NULLABLE"),
            bigquery.SchemaField("updated_at", "TIMESTAMP", mode="NULLABLE"),
        ]
        table = bigquery.Table(table_id, schema=schema)
        # create_table raises NotFound if dataset doesn't exist; let it bubble up
        client.create_table(table)
        # Double-check creation before returning
        client.get_table(table_id)


def main():
    ap = argparse.ArgumentParser(description="Seed identity rows into sensor_id_map")
    ap.add_argument('--project', required=True)
    ap.add_argument('--dataset', required=True)
    ap.add_argument('--execute', action='store_true', help='Execute the insert; otherwise print SQL')
    args = ap.parse_args()

    client = bigquery.Client(project=args.project)

    # Determine dataset location to ensure query jobs run in the same location
    ds_ref = client.get_dataset(f"{args.project}.{args.dataset}")
    ds_location = ds_ref.location  # e.g., 'US', 'EU', 'us-central1'

    # We'll still try to create via API (fast path), but also include IF NOT EXISTS DDL
    # inline with the INSERT in a single multi-statement job to avoid any race conditions.
    try:
        ensure_table(client, args.project, args.dataset)
    except Exception:
        # Non-fatal; we'll rely on the inline DDL below
        pass

    # Build sources list based on available tables
    sources = []
    long_fqdn = f"{args.project}.{args.dataset}.sensor_readings_long"
    daily_fqdn = f"{args.project}.{args.dataset}.sensor_readings_daily"
    if table_exists(client, long_fqdn):
        sources.append(f"SELECT native_sensor_id, source FROM `{long_fqdn}`")
    if table_exists(client, daily_fqdn):
        sources.append(f"SELECT native_sensor_id, source FROM `{daily_fqdn}`")

    if not sources:
        print("No source tables found (sensor_readings_long/daily). Nothing to seed.")
        return

    sources_sql = "\n  UNION DISTINCT\n  ".join(sources)
    insert_sql = INSERT_SQL_TEMPLATE.format(project=args.project, dataset=args.dataset, sources_sql=sources_sql)
    combined_sql = (
        CREATE_TABLE_SQL.format(project=args.project, dataset=args.dataset)
        + "\n"
        + insert_sql
    )

    if not args.execute:
        print(combined_sql)
        return

    target_fqdn = f"{args.project}.{args.dataset}.sensor_id_map"
    pre_exists = table_exists(client, target_fqdn)
    print(f"Dataset location: {ds_location}")
    print(f"Table existed before query: {pre_exists}")

    # Run the multi-statement DDL+INSERT in the dataset's location. Note: location is not a
    # QueryJobConfig property in this client version; pass it directly to client.query().
    job = client.query(combined_sql, location=ds_location)
    try:
        job.result()
        post_exists = table_exists(client, target_fqdn)
        print(f"Seed completed. Affected rows: {job.num_dml_affected_rows}")
        print(f"Table existed after query: {post_exists}")
    except Exception:
        post_exists = table_exists(client, target_fqdn)
        print("Seeding failed.")
        print(f"Dataset location: {ds_location}")
        print(f"Table existed before query: {pre_exists}, after query: {post_exists}")
        try:
            print(f"Job error_result: {getattr(job, 'error_result', None)}")
            print(f"Job errors: {getattr(job, 'errors', None)}")
        except Exception:
            pass
        raise


if __name__ == '__main__':
    main()
