#!/usr/bin/env python3
"""Upsert (MERGE) sensor readings from staging into canonical fact table.

Workflow expectation:
 1. Raw parquet files loaded into staging table via load_to_bigquery.py using --table-prefix staging_sensor_readings
 2. Run this script to MERGE rows for a given date partition into the target table (default sensor_readings)
 3. Optionally cleanup staging partition

Idempotent: running again for the same date only updates changed values or inserts missing rows.

Natural key used: (timestamp, deployment_fk, metric_name)

Example:
  python scripts/merge_sensor_readings.py \
    --project $BQ_PROJECT --dataset sensors --date 2025-08-20 \
    --staging-table staging_sensor_readings_raw \
    --target-table sensor_readings \
    --cleanup
"""
from __future__ import annotations
import argparse
import logging
import os
from typing import List
from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger("merge_sensor_readings")


def parse_args():
    p = argparse.ArgumentParser(description="MERGE staging sensor readings into target fact table")
    p.add_argument('--project', default=os.getenv('BQ_PROJECT'))
    p.add_argument('--dataset', required=True, help='BigQuery dataset ID')
    p.add_argument('--date', required=True, help='Date (YYYY-MM-DD) partition to merge')
    p.add_argument('--location', default=os.getenv('BQ_LOCATION', 'US'))
    # Single table (legacy behavior)
    p.add_argument('--staging-table', default=None, help='Single staging table name (partitioned)')
    # Multiple tables comma-separated
    p.add_argument('--staging-tables', default=None, help='Comma separated list of staging tables to UNION ALL')
    # Auto-detect tables with prefix (e.g. sensor_readings_ and suffix _raw)
    p.add_argument('--auto-detect-staging', action='store_true', help='Auto-detect staging tables by prefix/suffix')
    p.add_argument('--staging-prefix', default='sensor_readings_', help='Prefix used to auto-detect staging tables')
    p.add_argument('--staging-suffix', default='_raw', help='Suffix used to auto-detect staging tables')
    p.add_argument('--target-table', default='sensor_readings', help='Target fact table name (partitioned)')
    p.add_argument('--update-only-if-changed', action='store_true', help='Skip UPDATE when value unchanged')
    p.add_argument('--cleanup', action='store_true', help='Delete staging rows for the date after merge (only for single-table legacy)')
    args = p.parse_args()

    # Normalize staging tables selection
    selections = sum([
        1 if args.staging_table else 0,
        1 if args.staging_tables else 0,
        1 if args.auto_detect_staging else 0
    ])
    if selections == 0:
        # default legacy single table name
        args.staging_table = 'staging_sensor_readings_raw'
    elif selections > 1:
        raise SystemExit("Specify only one of --staging-table, --staging-tables, or --auto-detect-staging")
    return args


def ensure_target_exists_from_reference(client: bigquery.Client, dataset: str, reference_staging: str, target: str):
    """Create target table if missing using schema subset from a reference staging table."""
    try:
        client.get_table(f"{dataset}.{target}")
        return
    except Exception:
        pass
    try:
        st = client.get_table(f"{dataset}.{reference_staging}")
    except Exception as e:
        raise SystemExit(f"Reference staging table '{reference_staging}' not found to derive schema: {e}")
    schema = [f for f in st.schema if f.name in {'timestamp','deployment_fk','metric_name','value'}]
    if not schema:
        raise SystemExit("Could not derive schema subset from staging table (required fields missing)")
    tbl = bigquery.Table(f"{client.project}.{dataset}.{target}", schema=schema)
    tbl.time_partitioning = bigquery.TimePartitioning(field='timestamp')
    client.create_table(tbl)
    log.info(f"Created target table {dataset}.{target} from schema of {reference_staging}")


def resolve_staging_tables(client: bigquery.Client, dataset: str, args) -> List[str]:
    if args.staging_table:
        return [args.staging_table]
    if args.staging_tables:
        return [t.strip() for t in args.staging_tables.split(',') if t.strip()]
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
            raise SystemExit(f"Auto-detect found no staging tables with prefix '{prefix}' and suffix '{suffix}' in dataset {dataset}")
        log.info("Auto-detected staging tables: %s", ', '.join(detected))
        return detected
    raise SystemExit("No staging table selection resolved (this should not happen)")


def build_merge_sql(project: str, dataset: str, staging_tables, target: str, date_str: str, update_if_changed: bool) -> str:
    """Build the MERGE SQL statement.

    Backwards compatibility:
      Previous signature (pre-refactor) included a date parameter before the update flag and
      accepted a single staging table string. Tests still call it that way. The refactor moved
      date handling outside and required a list. This function now accepts either a single
      table name (str) or a list of table names and keeps the date parameter (currently used
      only for clarity; the query still filters with DATE(timestamp)=@d parameter binding).
    """
    # Normalize staging_tables to list
    if isinstance(staging_tables, str):
        staging_tables_list: List[str] = [staging_tables]
    else:
        staging_tables_list = staging_tables
    predicate = "T.value != S.value" if update_if_changed else "TRUE"
    if len(staging_tables_list) == 1:
        source_sql = (f"SELECT timestamp, deployment_fk, metric_name, value FROM `"
                      f"{project}.{dataset}.{staging_tables_list[0]}` WHERE DATE(timestamp)=@d")
        ref_for_comment = staging_tables_list[0]
    else:
        unions = []
        for t in staging_tables_list:
            unions.append(
                f"SELECT timestamp, deployment_fk, metric_name, value FROM `{project}.{dataset}.{t}` WHERE DATE(timestamp)=@d"
            )
        source_sql = "\nUNION ALL\n".join(unions)
        ref_for_comment = ",".join(staging_tables_list)
    return f"""
-- MERGE from staging tables: {ref_for_comment}
MERGE `{project}.{dataset}.{target}` T
USING (
  {source_sql}
) S
ON T.timestamp = S.timestamp
 AND T.deployment_fk = S.deployment_fk
 AND T.metric_name = S.metric_name
WHEN MATCHED AND {predicate} THEN UPDATE SET value = S.value
WHEN NOT MATCHED THEN INSERT (timestamp, deployment_fk, metric_name, value) VALUES (S.timestamp, S.deployment_fk, S.metric_name, S.value)
""".strip()


def merge_partition(client: bigquery.Client, args, staging_tables: List[str]):
    # create target if needed using first staging table as reference
    ensure_target_exists_from_reference(client, args.dataset, staging_tables[0], args.target_table)
    # Pass args.date explicitly for backward compatible signature
    sql = build_merge_sql(client.project, args.dataset, staging_tables, args.target_table, args.date, args.update_only_if_changed)
    cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter('d', 'DATE', args.date)])
    log.info("Running MERGE for %s from %d staging table(s)...", args.date, len(staging_tables))
    job = client.query(sql, job_config=cfg)
    job.result()
    log.info("MERGE complete. Affected rows: %s", job.num_dml_affected_rows)


def cleanup_staging(client: bigquery.Client, args, staging_tables: List[str]):
    if not args.cleanup:
        return
    if len(staging_tables) != 1:
        log.warning("Cleanup skipped: only supported for single staging table mode (got %d tables)", len(staging_tables))
        return
    sql = f"DELETE FROM `{client.project}.{args.dataset}.{staging_tables[0]}` WHERE DATE(timestamp)=@d"
    cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter('d', 'DATE', args.date)])
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

if __name__ == '__main__':  # pragma: no cover
    main()
