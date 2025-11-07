#!/usr/bin/env python3
"""
One-time helper script to (re)create Oura event tables as partitioned by day for cheaper scans.

It will:
  * Inspect existing tables: oura_sleep_periods, oura_sessions, oura_workouts
  * If they exist and are not partitioned on 'day', it will create new temp tables with partitioning
  * Copy data over, then replace the originals (requires appropriate permissions)
  * Skips tables that are already partitioned

Usage:
  python scripts/partition_oura_event_tables.py --dataset oura --project $BQ_PROJECT --confirm

Safe by default: requires --confirm flag.

Note: BigQuery load jobs created earlier are append-only; this script performs DDL + COPY statements.
"""

from __future__ import annotations
import argparse
import os
from google.cloud import bigquery

EVENT_TABLES = ["oura_sleep_periods", "oura_sessions", "oura_workouts"]


def is_partitioned(table: bigquery.Table) -> bool:
    return bool(table.time_partitioning and table.time_partitioning.field == "day")


def recreate_partitioned(client: bigquery.Client, dataset: str, table_name: str):
    full_id = f"{client.project}.{dataset}.{table_name}"
    try:
        table = client.get_table(full_id)
    except Exception:
        print(f"⚠️  Table not found, skipping create: {full_id}")
        return

    if is_partitioned(table):
        print(f"✅ Already partitioned: {full_id}")
        return

    # Create a new partitioned table with same schema
    temp_id = f"{full_id}__tmp_part"
    print(f"🔧 Creating partitioned copy: {temp_id}")
    new_table = bigquery.Table(temp_id, schema=table.schema)
    new_table.time_partitioning = bigquery.TimePartitioning(field="day")
    new_table.clustering_fields = [
        c.name for c in table.schema if c.name not in ("resident", "day")
    ][:4]
    client.delete_table(temp_id, not_found_ok=True)
    client.create_table(new_table)

    # Copy data
    copy_job = client.query(f"INSERT INTO `{temp_id}` SELECT * FROM `{full_id}`")
    copy_job.result()
    print(f"📦 Copied rows into partitioned table: {temp_id}")

    # Replace original
    client.delete_table(full_id)
    client.query(f"CREATE TABLE `{full_id}` AS SELECT * FROM `{temp_id}`").result()
    client.delete_table(temp_id)
    print(f"✅ Replaced original with partitioned: {full_id}")


def main():
    ap = argparse.ArgumentParser(description="Partition Oura event tables by day")
    ap.add_argument("--dataset", default="oura")
    ap.add_argument("--project", default=os.getenv("BQ_PROJECT"))
    ap.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    if not args.confirm:
        print("⚠️  Missing --confirm; aborting")
        return 2

    client = bigquery.Client(project=args.project, location=args.location)

    for tbl in EVENT_TABLES:
        recreate_partitioned(client, args.dataset, tbl)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
