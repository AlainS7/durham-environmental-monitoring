#!/usr/bin/env python3
"""Publish wide TSI parquet to GCS from per-day staging tables (AA-targeted backfill).

Use when staging_tsi_YYYYMMDD has the correct rows but GCS upload was skipped
because an older blob already existed (GCS_FORCE_OVERWRITE was not set).
"""
from __future__ import annotations

import argparse
import datetime as dt
import os

import pandas as pd
from google.cloud import bigquery

from src.storage.gcs_uploader import TSI_NUMERIC_COLS, GCSUploader

AA_SENSOR_IDS = ("AA-16", "AA-17", "AA-18", "AA-19", "AA-20")

PIVOT_METRICS = sorted(TSI_NUMERIC_COLS)


def daterange(start: dt.date, end: dt.date):
    cur = start
    while cur <= end:
        yield cur
        cur += dt.timedelta(days=1)


def fetch_wide(
    client: bigquery.Client, project: str, dataset: str, day: dt.date
) -> pd.DataFrame:
    staging = f"{project}.{dataset}.staging_tsi_{day.strftime('%Y%m%d')}"
    pivot_exprs = ",\n      ".join(
        f"MAX(IF(s.metric_name = '{m}', s.value, NULL)) AS `{m}`"
        for m in PIVOT_METRICS
    )
    sql = f"""
    SELECT
      UNIX_SECONDS(TIMESTAMP(s.timestamp)) AS timestamp,
      sim.native_sensor_id,
      {pivot_exprs}
    FROM `{staging}` s
    JOIN `{project}.{dataset}.sensor_id_map` sim
      ON FARM_FINGERPRINT(sim.native_sensor_id) = s.deployment_fk
    WHERE sim.sensor_id IN UNNEST(@sensor_ids)
    GROUP BY timestamp, sim.native_sensor_id
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ArrayQueryParameter("sensor_ids", "STRING", list(AA_SENSOR_IDS))
        ]
    )
    return client.query(sql, job_config=job_config).to_dataframe(
        create_bqstorage_client=False
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", default=os.getenv("PROJECT_ID", "durham-weather-466502"))
    parser.add_argument("--dataset", default=os.getenv("BQ_DATASET", "sensors"))
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--bucket", default=os.getenv("GCS_BUCKET", "sensor-data-to-bigquery"))
    parser.add_argument("--prefix", default=os.getenv("GCS_PREFIX", "raw"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    client = bigquery.Client(project=args.project)
    uploader = GCSUploader(bucket=args.bucket, prefix=args.prefix.strip("/"))

    for day in daterange(start, end):
        wide = fetch_wide(client, args.project, args.dataset, day)
        if wide.empty:
            print(f"[{day}] no AA rows in staging — skip")
            continue
        print(f"[{day}] wide rows={len(wide)} sensors={wide['native_sensor_id'].nunique()}")
        if args.dry_run:
            continue
        wide = wide.copy()
        wide["timestamp"] = pd.to_datetime(wide["timestamp"], unit="s", utc=True)
        path = uploader.upload_parquet(
            wide,
            source="TSI",
            aggregated=False,
            interval="h",
            ts_column="timestamp",
            force=True,
        )
        print(f"[{day}] uploaded gs://{args.bucket}/{path}")


if __name__ == "__main__":
    main()
