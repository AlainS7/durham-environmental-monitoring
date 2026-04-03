#!/usr/bin/env python3
"""Upsert (MERGE) sensor readings from staging into canonical fact table.

Workflow expectation:
 1. Raw parquet files are available in staging table(s)
 2. Run this script to MERGE rows for a given date partition into target table
 3. Optionally cleanup staging partition in single-table mode

Natural key: (timestamp, deployment_fk, metric_name)
"""

from __future__ import annotations

import argparse
import logging
import os
from typing import List

from google.cloud import bigquery

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("merge_sensor_readings")


def parse_args():
    p = argparse.ArgumentParser(
        description="MERGE staging sensor readings into target fact table"
    )
    p.add_argument("--project", default=os.getenv("BQ_PROJECT"))
    p.add_argument("--dataset", required=True, help="BigQuery dataset ID")
    p.add_argument("--date", required=True, help="Date (YYYY-MM-DD) partition to merge")
    p.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    p.add_argument(
        "--staging-table", default=None, help="Single staging table name (partitioned)"
    )
    p.add_argument(
        "--staging-tables",
        default=None,
        help="Comma separated list of staging tables to UNION ALL",
    )
    p.add_argument(
        "--auto-detect-staging",
        action="store_true",
        help="Auto-detect staging tables by prefix/suffix",
    )
    p.add_argument(
        "--staging-prefix",
        default="sensor_readings_",
        help="Prefix used to auto-detect staging tables",
    )
    p.add_argument(
        "--staging-suffix",
        default="_raw",
        help="Suffix used to auto-detect staging tables",
    )
    p.add_argument(
        "--target-table",
        default="sensor_readings",
        help="Target fact table name (partitioned)",
    )
    p.add_argument(
        "--update-only-if-changed",
        action="store_true",
        help="Skip UPDATE when value unchanged",
    )
    p.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete staging rows for the date after merge (single-table mode)",
    )
    args = p.parse_args()

    selections = sum(
        [
            1 if args.staging_table else 0,
            1 if args.staging_tables else 0,
            1 if args.auto_detect_staging else 0,
        ]
    )
    if selections == 0:
        args.staging_table = "staging_sensor_readings_raw"
    elif selections > 1:
        raise SystemExit(
            "Specify only one of --staging-table, --staging-tables, or --auto-detect-staging"
        )
    return args


def ensure_target_exists_from_reference(
    client: bigquery.Client, dataset: str, reference_staging: str, target: str
):
    try:
        client.get_table(f"{dataset}.{target}")
        return
    except Exception:
        pass
    try:
        st = client.get_table(f"{dataset}.{reference_staging}")
    except Exception as e:
        raise SystemExit(
            f"Reference staging table '{reference_staging}' not found to derive schema: {e}"
        )
    schema = [
        f
        for f in st.schema
        if f.name in {"timestamp", "deployment_fk", "metric_name", "value"}
    ]
    if not schema:
        raise SystemExit(
            "Could not derive schema subset from staging table (required fields missing)"
        )
    tbl = bigquery.Table(f"{client.project}.{dataset}.{target}", schema=schema)
    tbl.time_partitioning = bigquery.TimePartitioning(field="timestamp")
    client.create_table(tbl)
    log.info(
        "Created target table %s.%s from schema of %s",
        dataset,
        target,
        reference_staging,
    )


def resolve_staging_tables(client: bigquery.Client, dataset: str, args) -> List[str]:
    if args.staging_table:
        return [args.staging_table]
    if args.staging_tables:
        return [t.strip() for t in args.staging_tables.split(",") if t.strip()]
    if args.auto_detect_staging:
        prefix = args.staging_prefix
        suffix = args.staging_suffix
        detected = []
        for tbl in client.list_tables(dataset):  # type: ignore[arg-type]
            name = tbl.table_id
            if not name.startswith(prefix):
                continue
            if suffix and not name.endswith(suffix):
                continue
            if name == args.target_table:
                continue
            detected.append(name)
        if not detected:
            raise SystemExit(
                f"Auto-detect found no staging tables with prefix '{prefix}' and suffix '{suffix}' in dataset {dataset}"
            )
        log.info("Auto-detected staging tables: %s", ", ".join(detected))
        return detected
    raise SystemExit("No staging table selection resolved")


def build_merge_sql(
    project: str,
    dataset: str,
    staging_tables,
    target: str,
    date_str: str,
    update_if_changed: bool,
) -> str:
    # Backward compatibility: allow single staging table string.
    if isinstance(staging_tables, str):
        staging_tables_list: List[str] = [staging_tables]
    else:
        staging_tables_list = staging_tables

    unions = []
    for t in staging_tables_list:
        unions.append(
            f"SELECT timestamp, deployment_fk, metric_name, value FROM `{project}.{dataset}.{t}` WHERE DATE(timestamp)=@d"
        )
    union_sql = "\nUNION ALL\n".join(unions)
    predicate = "T.value != S.value" if update_if_changed else "TRUE"
    ref_for_comment = ",".join(staging_tables_list)

    return f"""
-- MERGE from staging tables: {ref_for_comment}
MERGE `{project}.{dataset}.{target}` T
USING (
  SELECT
    timestamp,
    deployment_fk,
    metric_name,
    ANY_VALUE(value) AS value
  FROM (
    {union_sql}
  )
  GROUP BY timestamp, deployment_fk, metric_name
) S
ON T.timestamp = S.timestamp
 AND T.deployment_fk = S.deployment_fk
 AND T.metric_name = S.metric_name
WHEN MATCHED AND {predicate} THEN UPDATE SET value = S.value
WHEN NOT MATCHED THEN INSERT (timestamp, deployment_fk, metric_name, value) VALUES (S.timestamp, S.deployment_fk, S.metric_name, S.value)
""".strip()


def merge_partition(client: bigquery.Client, args, staging_tables: List[str]):
    ensure_target_exists_from_reference(
        client, args.dataset, staging_tables[0], args.target_table
    )
    sql = build_merge_sql(
        client.project,
        args.dataset,
        staging_tables,
        args.target_table,
        args.date,
        args.update_only_if_changed,
    )
    cfg = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("d", "DATE", args.date)]
    )
    log.info(
        "Running MERGE for %s from %d staging table(s)...",
        args.date,
        len(staging_tables),
    )
    job = client.query(sql, job_config=cfg)
    job.result()
    log.info("MERGE complete. Affected rows: %s", job.num_dml_affected_rows)


def cleanup_staging(client: bigquery.Client, args, staging_tables: List[str]):
    if not args.cleanup:
        return
    if len(staging_tables) != 1:
        log.warning(
            "Cleanup skipped: only supported for single staging table mode (got %d tables)",
            len(staging_tables),
        )
        return
    sql = f"DELETE FROM `{client.project}.{args.dataset}.{staging_tables[0]}` WHERE DATE(timestamp)=@d"
    cfg = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("d", "DATE", args.date)]
    )
    log.info("Cleaning up staging partition %s in %s...", args.date, staging_tables[0])
    job = client.query(sql, job_config=cfg)
    job.result()
    log.info("Cleanup complete (deleted rows: %s)", job.num_dml_affected_rows)


def main():
    a = parse_args()
    client = bigquery.Client(project=a.project, location=a.location)
    staging_tables = resolve_staging_tables(client, a.dataset, a)
    merge_partition(client, a, staging_tables)
    cleanup_staging(client, a, staging_tables)


if __name__ == "__main__":  # pragma: no cover
    main()
