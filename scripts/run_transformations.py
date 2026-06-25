#!/usr/bin/env python3
"""Render and optionally execute transformation SQL files.

Supports simple token replacement for ${PROJECT} and ${DATASET} plus
parameter @proc_date (passed as --date) using BigQuery query parameters.

Usage:
  python scripts/run_transformations.py --project my-proj --dataset sensors --dir transformations/sql --date 2025-08-26 --execute

Without --execute it prints the SQL (dry run). Execution order is lexical (filenames sorted).
"""

from __future__ import annotations
import argparse
import os
from pathlib import Path
from typing import List
import re

from google.cloud import bigquery  # type: ignore

TOKEN_PATTERN = re.compile(r"\$\{(PROJECT|DATASET)\}")


def render(sql: str, project: str, dataset: str) -> str:
    def repl(match):
        key = match.group(1)
        return project if key == "PROJECT" else dataset

    return TOKEN_PATTERN.sub(repl, sql)


def list_sql_files(dir_path: Path) -> List[Path]:
    return sorted(
        [
            p
            for p in dir_path.glob("*.sql")
            if p.is_file() and not p.name.endswith(".template.sql")
        ]
    )


def execute_sql(client: bigquery.Client, sql: str, process_date: str):
    """Execute SQL file using BigQuery's multi-statement support.

    BigQuery Standard SQL supports multiple statements in a single query
    when use_legacy_sql=False. The key is using the proper job config.
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("proc_date", "DATE", process_date)
        ],
        use_legacy_sql=False,
    )

    # Execute the entire SQL as a multi-statement batch
    # BigQuery will process DECLARE + statements together
    job = client.query(sql, job_config=job_config)
    job.result()


def reconcile_assignment_overrides(
    client: bigquery.Client, project: str, dataset: str, process_date: str
) -> None:
    """Re-apply manual assignment overrides after 07 refreshes."""
    sql = f"""
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.residence_sensor_assignment_overrides`
(
  residence_id STRING NOT NULL,
  native_sensor_id STRING NOT NULL,
  sensor_name STRING,
  sensor_role STRING NOT NULL,
  start_ts TIMESTAMP NOT NULL,
  end_ts TIMESTAMP,
  updated_at TIMESTAMP NOT NULL,
  override_source STRING
)
PARTITION BY DATE(start_ts)
CLUSTER BY residence_id, native_sensor_id;

MERGE `{project}.{dataset}.residence_sensor_assignments` T
USING (
  SELECT
    residence_id,
    native_sensor_id,
    sensor_name,
    sensor_role,
    start_ts,
    end_ts
  FROM `{project}.{dataset}.residence_sensor_assignment_overrides`
) S
ON T.residence_id = S.residence_id
AND T.native_sensor_id = S.native_sensor_id
AND T.sensor_role = S.sensor_role
AND T.start_ts = S.start_ts
WHEN MATCHED THEN
  UPDATE SET
    sensor_name = S.sensor_name,
    end_ts = S.end_ts,
    updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (residence_id, native_sensor_id, sensor_name, sensor_role, start_ts, end_ts, updated_at)
  VALUES (S.residence_id, S.native_sensor_id, S.sensor_name, S.sensor_role, S.start_ts, S.end_ts, CURRENT_TIMESTAMP());
"""
    execute_sql(client, sql, process_date)


def main():
    ap = argparse.ArgumentParser(description="Run transformation SQL files")
    ap.add_argument(
        "--project",
        default=os.getenv("BQ_PROJECT"),
        help="GCP project (defaults to BQ_PROJECT env var, required for --execute)",
    )
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--dir", default="transformations/sql")
    ap.add_argument(
        "--date",
        required=True,
        help="Processing date (e.g. yesterday) for parameter @proc_date",
    )
    ap.add_argument("--execute", action="store_true", help="Execute instead of print")
    args = ap.parse_args()

    # Only require / instantiate BigQuery client when executing. For a dry run we
    # simply render and print SQL so credentials are unnecessary (helps PR CI
    # workflows that lack GCP auth for preview).
    if not args.project and args.execute:
        raise SystemExit("--project or BQ_PROJECT env var required for execution")

    # For dry runs, use placeholder if project not provided
    project_id = args.project or "PROJECT_PLACEHOLDER"

    client = bigquery.Client(project=args.project) if args.execute else None
    dir_path = Path(args.dir)
    if not dir_path.exists():
        raise SystemExit(f"Directory not found: {dir_path}")

    for sql_file in list_sql_files(dir_path):
        raw = sql_file.read_text()
        sql = render(raw, project_id, args.dataset)
        print(f"-- {sql_file.name} --")
        if args.execute:
            # mypy: client is not None in execute path
            execute_sql(client, sql, args.date)  # type: ignore[arg-type]
            print(f"Executed {sql_file.name}")
            if sql_file.name == "07_residence_sensor_assignments.sql":
                reconcile_assignment_overrides(
                    client, project_id, args.dataset, args.date
                )  # type: ignore[arg-type]
                print("Reconciled residence assignment overrides")
        else:
            print(sql)


if __name__ == "__main__":
    main()
