#!/usr/bin/env python3
"""Manage residence/sensor assignments and resident access in BigQuery.

Supports:
  - add-assignment: create a new assignment row
  - end-assignment: close active assignment(s) for a sensor/residence
  - switch-assignment: move a sensor from one residence to another at an effective timestamp
  - add-resident-access: upsert resident principal -> residence access row

All mutating commands require --execute.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timedelta, timezone

from google.cloud import bigquery
from google.api_core.exceptions import NotFound


def sql_quote(value: str) -> str:
    return value.replace("'", "''")


def parse_ts(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def ts_literal(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S+00:00")


def ensure_tables(client: bigquery.Client, project: str, dataset: str) -> None:
    # residence_sensor_assignments
    client.query(
        f"""
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.residence_sensor_assignments`
(
  residence_id STRING NOT NULL,
  native_sensor_id STRING NOT NULL,
  sensor_name STRING,
  sensor_role STRING NOT NULL,
  start_ts TIMESTAMP NOT NULL,
  end_ts TIMESTAMP,
  updated_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(start_ts)
CLUSTER BY residence_id, native_sensor_id
"""
    ).result()

    # resident_user_access
    client.query(
        f"""
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.resident_user_access` (
  principal_email STRING NOT NULL,
  residence_id STRING NOT NULL,
  active BOOL NOT NULL,
  updated_at TIMESTAMP NOT NULL
)
CLUSTER BY principal_email, residence_id
"""
    ).result()


def preview_or_execute(client: bigquery.Client, sql: str, execute: bool) -> None:
    if not execute:
        print(sql.strip() + "\n")
        return
    client.query(sql).result()


def op_add_assignment(client: bigquery.Client, args: argparse.Namespace) -> None:
    start_ts = parse_ts(args.start_ts)
    sensor_name_expr = f"'{sql_quote(args.sensor_name)}'" if args.sensor_name else "NULL"
    sql = f"""
INSERT INTO `{args.project}.{args.dataset}.residence_sensor_assignments`
  (residence_id, native_sensor_id, sensor_name, sensor_role, start_ts, end_ts, updated_at)
VALUES
  (
    '{sql_quote(args.residence_id)}',
    '{sql_quote(args.native_sensor_id)}',
    {sensor_name_expr},
    '{sql_quote(args.sensor_role)}',
    TIMESTAMP('{ts_literal(start_ts)}'),
    NULL,
    CURRENT_TIMESTAMP()
  )
"""
    preview_or_execute(client, sql, args.execute)


def op_end_assignment(client: bigquery.Client, args: argparse.Namespace) -> None:
    end_ts = parse_ts(args.end_ts)
    filters = []
    if args.native_sensor_id:
        filters.append(f"native_sensor_id = '{sql_quote(args.native_sensor_id)}'")
    if args.residence_id:
        filters.append(f"residence_id = '{sql_quote(args.residence_id)}'")
    if not filters:
        raise SystemExit("Provide at least one filter: --native-sensor-id and/or --residence-id")

    sql = f"""
UPDATE `{args.project}.{args.dataset}.residence_sensor_assignments`
SET end_ts = TIMESTAMP('{ts_literal(end_ts)}'),
    updated_at = CURRENT_TIMESTAMP()
WHERE end_ts IS NULL
  AND {' AND '.join(filters)}
"""
    preview_or_execute(client, sql, args.execute)


def op_switch_assignment(client: bigquery.Client, args: argparse.Namespace) -> None:
    switch_ts = parse_ts(args.switch_ts)
    prior_end = switch_ts - timedelta(seconds=1)

    close_sql = f"""
UPDATE `{args.project}.{args.dataset}.residence_sensor_assignments`
SET end_ts = TIMESTAMP('{ts_literal(prior_end)}'),
    updated_at = CURRENT_TIMESTAMP()
WHERE end_ts IS NULL
  AND native_sensor_id = '{sql_quote(args.native_sensor_id)}'
  AND residence_id = '{sql_quote(args.from_residence_id)}'
"""
    insert_sql = f"""
INSERT INTO `{args.project}.{args.dataset}.residence_sensor_assignments`
  (residence_id, native_sensor_id, sensor_name, sensor_role, start_ts, end_ts, updated_at)
VALUES
  (
    '{sql_quote(args.to_residence_id)}',
    '{sql_quote(args.native_sensor_id)}',
    {("'" + sql_quote(args.sensor_name) + "'") if args.sensor_name else "NULL"},
    '{sql_quote(args.sensor_role)}',
    TIMESTAMP('{ts_literal(switch_ts)}'),
    NULL,
    CURRENT_TIMESTAMP()
  )
"""
    preview_or_execute(client, close_sql, args.execute)
    preview_or_execute(client, insert_sql, args.execute)


def op_add_resident_access(client: bigquery.Client, args: argparse.Namespace) -> None:
    sql = f"""
MERGE `{args.project}.{args.dataset}.resident_user_access` T
USING (
  SELECT
    '{sql_quote(args.principal_email)}' AS principal_email,
    '{sql_quote(args.residence_id)}' AS residence_id,
    {str(args.active).upper()} AS active
) S
ON LOWER(T.principal_email) = LOWER(S.principal_email)
AND T.residence_id = S.residence_id
WHEN MATCHED THEN
  UPDATE SET active = S.active, updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN
  INSERT (principal_email, residence_id, active, updated_at)
  VALUES (S.principal_email, S.residence_id, S.active, CURRENT_TIMESTAMP())
"""
    preview_or_execute(client, sql, args.execute)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Manage residence assignment/access operations")
    p.add_argument("--project", default=os.getenv("BQ_PROJECT") or os.getenv("GCP_PROJECT_ID"))
    p.add_argument("--dataset", default=os.getenv("BQ_DATASET", "sensors"))
    p.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    p.add_argument("--execute", action="store_true", help="Apply changes; otherwise print SQL")

    sub = p.add_subparsers(dest="operation", required=True)

    add = sub.add_parser("add-assignment")
    add.add_argument("--residence-id", required=True)
    add.add_argument("--native-sensor-id", required=True)
    add.add_argument("--sensor-name")
    add.add_argument("--sensor-role", required=True, choices=["Indoor", "Outdoor"])
    add.add_argument("--start-ts", required=True, help="ISO timestamp, e.g. 2026-03-27T00:00:00Z")

    end = sub.add_parser("end-assignment")
    end.add_argument("--native-sensor-id")
    end.add_argument("--residence-id")
    end.add_argument("--end-ts", required=True, help="ISO timestamp")

    switch = sub.add_parser("switch-assignment")
    switch.add_argument("--native-sensor-id", required=True)
    switch.add_argument("--from-residence-id", required=True)
    switch.add_argument("--to-residence-id", required=True)
    switch.add_argument("--sensor-name")
    switch.add_argument("--sensor-role", required=True, choices=["Indoor", "Outdoor"])
    switch.add_argument("--switch-ts", required=True, help="ISO timestamp")

    access = sub.add_parser("add-resident-access")
    access.add_argument("--principal-email", required=True)
    access.add_argument("--residence-id", required=True)
    access.add_argument("--active", choices=["true", "false"], default="true")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.project:
        raise SystemExit("Missing --project (or set BQ_PROJECT/GCP_PROJECT_ID)")
    if not args.execute:
        print("Dry-run mode: SQL will be printed only.\n")
    if args.operation == "add-resident-access":
        args.active = str(args.active).lower() == "true"

    client = bigquery.Client(project=args.project, location=args.location)
    try:
        client.get_dataset(f"{args.project}.{args.dataset}")
    except NotFound as exc:
        raise SystemExit(f"Dataset not found: {args.project}.{args.dataset}") from exc

    ensure_tables(client, args.project, args.dataset)

    if args.operation == "add-assignment":
        op_add_assignment(client, args)
    elif args.operation == "end-assignment":
        op_end_assignment(client, args)
    elif args.operation == "switch-assignment":
        op_switch_assignment(client, args)
    elif args.operation == "add-resident-access":
        op_add_resident_access(client, args)
    else:
        raise SystemExit(f"Unsupported operation: {args.operation}")

    if args.execute:
        print("Operation completed.")


if __name__ == "__main__":
    main()
