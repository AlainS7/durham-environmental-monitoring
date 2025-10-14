#!/usr/bin/env python3
"""Materialize daily partitions from external tables into native partitioned tables.

Creates or updates two native tables:
  - <dataset>.wu_raw_materialized (PARTITION BY DATE(ts))
  - <dataset>.tsi_raw_materialized (PARTITION BY DATE(ts))

For each requested date, it deletes existing rows for that date and inserts
rows from the external tables, converting epoch-like integer timestamps to
TIMESTAMP as column `ts` and preserving other columns.

Assumptions:
  - External tables exist as <dataset>.wu_raw_external and <dataset>.tsi_raw_external
  - External schemas include integer fields `timestamp` or `epoch` or `ts` that
    represent seconds since epoch

Usage examples:
  python scripts/materialize_partitions.py --dataset sensors --project durham-weather-466502 \
      --start 2025-09-16 --end 2025-09-19 --sources all --execute
"""
from __future__ import annotations

import argparse
import datetime as dt
from typing import Iterable, List, Optional
import os

from google.cloud import bigquery
from google.cloud.exceptions import NotFound


def daterange(start: dt.date, end: dt.date) -> Iterable[dt.date]:
    cur = start
    while cur <= end:
        yield cur
        cur = cur + dt.timedelta(days=1)


def _resolve_time_field(client: bigquery.Client, dataset: str, external_table: str) -> str:
    """Pick the best timestamp-like field present in the external table schema."""
    table_ref = f"{client.project}.{dataset}.{external_table}"
    table = client.get_table(table_ref)
    field_names = {f.name for f in table.schema}
    candidates = ["timestamp", "epoch", "ts", "time", "event_time"]
    for c in candidates:
        if c in field_names:
            return c
    # Fall back to first TIMESTAMP/INTEGER-like field
    for f in table.schema:
        if f.field_type in ("TIMESTAMP", "DATETIME", "INTEGER", "INT64"):
            return f.name
    # As last resort, raise an error
    raise RuntimeError(f"Could not determine time field for table {table_ref}")


def ensure_materialized_table(client: bigquery.Client, dataset: str, table: str, external_table: str, cluster_by: List[str] | None = None) -> None:
    fq = f"{client.project}.{dataset}.{table}"
    try:
        client.get_table(fq)
        return
    except NotFound:
        pass

    # Create table using CTAS with zero rows to define schema: cast epoch to TIMESTAMP as ts
    # Filter cluster_by to columns that actually exist in source (excluding time field)
    time_field = _resolve_time_field(client, dataset, external_table)
    src_schema = {f.name for f in client.get_table(f"{client.project}.{dataset}.{external_table}").schema}
    cluster_cols = [c for c in (cluster_by or []) if c in src_schema]
    cluster_clause = f" CLUSTER BY {', '.join(cluster_cols)}" if cluster_cols else ""
    # Choose correct epoch unit dynamically (ns/us/ms/s) to avoid TIMESTAMP overflow
    # Boundaries based on orders of magnitude around current epoch (~1.7e9 s)
    ts_expr = (
        "CASE "
        f"WHEN ABS(CAST(t.{time_field} AS INT64)) >= 100000000000000000 THEN "
        f"  TIMESTAMP_MICROS(DIV(CAST(t.{time_field} AS INT64), 1000)) "
        f"WHEN ABS(CAST(t.{time_field} AS INT64)) >= 100000000000000 THEN "
        f"  TIMESTAMP_MICROS(CAST(t.{time_field} AS INT64)) "
        f"WHEN ABS(CAST(t.{time_field} AS INT64)) >= 100000000000 THEN "
        f"  TIMESTAMP_MILLIS(CAST(t.{time_field} AS INT64)) "
        f"ELSE TIMESTAMP_SECONDS(CAST(t.{time_field} AS INT64)) END"
    )
    except_cols = [c for c in ["timestamp", "epoch", "ts"] if c in src_schema]
    except_clause = f" EXCEPT({', '.join(except_cols)})" if except_cols else ""
    sql = f"""
    CREATE TABLE `{fq}`
    PARTITION BY DATE(ts)
    {cluster_clause}
    AS
    SELECT
      {ts_expr} AS ts,
                    t.*{except_clause}
    FROM `{client.project}.{dataset}.{external_table}` AS t
    WHERE 1=0
    """
    job = client.query(sql)
    job.result()


def delete_partition(client: bigquery.Client, dataset: str, table: str, d: dt.date) -> None:
    # Check if table exists first
    fq = f"{client.project}.{dataset}.{table}"
    try:
        client.get_table(fq)
    except NotFound:
        # Table doesn't exist yet, nothing to delete
        return
    
    sql = f"DELETE FROM `{fq}` WHERE DATE(ts) = @d"
    job = client.query(sql, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("d", "DATE", d.isoformat())]
    ))
    job.result()


def insert_partition_from_external(client: bigquery.Client, dataset: str, table: str, external_table: str, d: dt.date) -> None:
    target_table_ref = f"{client.project}.{dataset}.{table}"
    try:
        target_table = client.get_table(target_table_ref)
        target_cols = [f.name for f in target_table.schema]
    except NotFound:
        print(f"[materialize] Target table {target_table_ref} not found. Cannot insert.")
        return

    external_table_ref = f"{client.project}.{dataset}.{external_table}"
    external_table_obj = client.get_table(external_table_ref)
    external_cols = {f.name for f in external_table_obj.schema}

    time_field = _resolve_time_field(client, dataset, external_table)

    ts_expr = (
        "CASE "
        f"WHEN ABS(CAST(t.{time_field} AS INT64)) >= 100000000000000000 THEN "
        f"  TIMESTAMP_MICROS(DIV(CAST(t.{time_field} AS INT64), 1000)) "
        f"WHEN ABS(CAST(t.{time_field} AS INT64)) >= 100000000000000 THEN "
        f"  TIMESTAMP_MICROS(CAST(t.{time_field} AS INT64)) "
        f"WHEN ABS(CAST(t.{time_field} AS INT64)) >= 100000000000 THEN "
        f"  TIMESTAMP_MILLIS(CAST(t.{time_field} AS INT64)) "
        f"ELSE TIMESTAMP_SECONDS(CAST(t.{time_field} AS INT64)) END"
    )

    select_list = []
    for col in target_cols:
        if col == 'ts':
            select_list.append(f"{ts_expr} AS ts")
        elif col in external_cols:
            select_list.append(f"`{col}`")
        else:
            select_list.append(f"NULL AS `{col}`")

    sql = f"""
    INSERT INTO `{target_table_ref}` ({', '.join(f'`{c}`' for c in target_cols)})
    SELECT {', '.join(select_list)}
    FROM `{external_table_ref}` AS t
    WHERE DATE({ts_expr}) = @d
      AND REGEXP_CONTAINS(_FILE_NAME, @dtpath)
    """
    job = client.query(sql, job_config=bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("d", "DATE", d.isoformat()),
            bigquery.ScalarQueryParameter("dtpath", "STRING", f"/dt={d.isoformat()}/"),
        ]
    ))
    job.result()


def _table_exists(client: bigquery.Client, project: str, dataset: str, table: str) -> bool:
    try:
        client.get_table(f"{project}.{dataset}.{table}")
        return True
    except NotFound:
        return False


def _load_from_gcs_to_staging(
    client: bigquery.Client,
    project: str,
    dataset: str,
    src: str,
    bucket: str,
    prefix: str,
    date: dt.date,
) -> Optional[str]:
    """Load a single partition parquet from GCS into a temporary staging table.

    Returns the fully qualified staging table name.
    """
    staging = f"{src.lower()}_raw_stage_{date.isoformat().replace('-', '')}"
    fq_stage = f"{project}.{dataset}.{staging}"

    # Create or replace an empty table for the stage (schema will be auto-detected by load job)
    # Build exact URI for the expected file name written by collector
    uri = f"gs://{bucket}/{prefix.strip('/')}/source={src}/agg=raw/dt={date.isoformat()}/{src}-{date.isoformat()}.parquet"

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    try:
        load_job = client.load_table_from_uri(uri, fq_stage, job_config=job_config)
        load_job.result()
        print(f"[materialize] Loaded stage from {uri} into {fq_stage}")
        return fq_stage
    except Exception as e:
        # Treat missing object or permission as no data for this date/source
        print(f"[materialize] Skipping load for {src} {date}: {e}")
        return None


def insert_partition_from_gcs(
    client: bigquery.Client,
    dataset: str,
    table: str,
    stage_table: str,
    d: dt.date,
) -> None:
    target_table_ref = f"{client.project}.{dataset}.{table}"
    try:
        target_table = client.get_table(target_table_ref)
        target_cols = [f.name for f in target_table.schema]
    except NotFound:
        # If the target table doesn't exist, we can't proceed with a targeted insert.
        # The calling function should have already created it.
        print(f"[materialize] Target table {target_table_ref} not found. Cannot insert.")
        return

    stage_table_obj = client.get_table(stage_table)
    stage_cols = {f.name for f in stage_table_obj.schema}

    time_field = _resolve_time_field(client, dataset, stage_table.split('.')[-1])

    ts_expr = (
        "CASE "
        f"WHEN ABS(CAST(t.{time_field} AS INT64)) >= 100000000000000000 THEN "
        f"  TIMESTAMP_MICROS(DIV(CAST(t.{time_field} AS INT64), 1000)) "
        f"WHEN ABS(CAST(t.{time_field} AS INT64)) >= 100000000000000 THEN "
        f"  TIMESTAMP_MICROS(CAST(t.{time_field} AS INT64)) "
        f"WHEN ABS(CAST(t.{time_field} AS INT64)) >= 100000000000 THEN "
        f"  TIMESTAMP_MILLIS(CAST(t.{time_field} AS INT64)) "
        f"ELSE TIMESTAMP_SECONDS(CAST(t.{time_field} AS INT64)) END"
    )

    # Build the SELECT list, providing NULL for columns missing in the staging table
    select_list = []
    for col in target_cols:
        if col == 'ts':
            select_list.append(f"{ts_expr} AS ts")
        elif col in stage_cols:
            select_list.append(f"`{col}`")
        else:
            select_list.append(f"NULL AS `{col}`")

    sql = f"""
    INSERT INTO `{target_table_ref}` ({', '.join(f'`{c}`' for c in target_cols)})
    SELECT {', '.join(select_list)}
    FROM `{stage_table}` AS t
    WHERE DATE({ts_expr}) = @d
    """
    job = client.query(sql, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("d", "DATE", d.isoformat())]
    ))
    job.result()


def main() -> None:
    ap = argparse.ArgumentParser(description="Materialize daily partitions from external tables into native tables")
    ap.add_argument("--project", default=None, help="GCP project (defaults to ADC)")
    ap.add_argument("--dataset", required=True, help="BigQuery dataset")
    ap.add_argument("--start", required=True, help="Start date YYYY-MM-DD")
    ap.add_argument("--end", required=True, help="End date YYYY-MM-DD")
    ap.add_argument("--sources", choices=["WU", "TSI", "all"], default="all")
    ap.add_argument("--bucket", default=os.getenv("GCS_BUCKET"), help="GCS bucket for raw parquet fallback")
    ap.add_argument("--prefix", default=os.getenv("GCS_PREFIX", "raw"), help="GCS prefix for raw parquet fallback")
    ap.add_argument("--execute", action="store_true", help="Actually perform DML; otherwise dry run prints actions")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    sources = ["WU", "TSI"] if args.sources == "all" else [args.sources]

    client = bigquery.Client(project=args.project or None)

    actions: list[str] = []

    for src in sources:
        ext = f"{src.lower()}_raw_external"
        mat = f"{src.lower()}_raw_materialized"
        for d in daterange(start, end):
            actions.append(f"Replace partition {d} for {mat} (prefer external; fallback GCS stage)")
            if args.execute:
                delete_partition(client, args.dataset, mat, d)
                # Prefer external table path when available; otherwise, load from GCS directly
                use_external = _table_exists(client, client.project, args.dataset, ext)
                if use_external:
                    try:
                        # Ensure target exists using external schema
                        ensure_materialized_table(client, args.dataset, mat, ext, cluster_by=["native_sensor_id"])
                        insert_partition_from_external(client, args.dataset, mat, ext, d)
                        continue
                    except Exception as e:
                        print(f"[materialize] External path failed for {src} {d}: {e}. Falling back to GCS stage.")
                # Fallback to GCS direct load
                if not args.bucket:
                    print("[materialize] No bucket provided; skipping fallback load.")
                    continue
                stage = _load_from_gcs_to_staging(client, client.project, args.dataset, src, args.bucket, args.prefix, d)
                if stage is None:
                    # nothing to insert
                    continue
                # Ensure target exists using stage schema
                ensure_materialized_table(client, args.dataset, mat, stage.split(".")[-1], cluster_by=["native_sensor_id"])  # source table within same dataset
                insert_partition_from_gcs(client, args.dataset, mat, stage, d)

    if not args.execute:
        print("\n".join(actions))


if __name__ == "__main__":
    main()
