#!/usr/bin/env python3
"""Verify BigQuery outputs by reporting row counts per partition/table.

Usage:
  python scripts/verify_outputs.py \
    --project <gcp-project> \
    --dataset sensors \
    --start 2025-09-16 --end 2025-09-19 \
    [--tables wu_raw_materialized,tsi_raw_materialized,sensor_readings_long,hourly_summary,daily_summary]

Outputs a simple report to stdout.
"""
from __future__ import annotations
import argparse
import datetime as dt
from typing import List, Tuple
from google.cloud import bigquery
from google.cloud import storage

# Table -> (timestamp column to cast to DATE, label)
DEFAULT_TABLES = [
    ("wu_raw_materialized", "ts", "wu_raw_materialized"),
    ("tsi_raw_materialized", "ts", "tsi_raw_materialized"),
    ("sensor_readings_long", "timestamp", "sensor_readings_long"),
    ("sensor_readings_hourly", "hour_ts", "sensor_readings_hourly"),
    ("sensor_readings_daily", "day_ts", "sensor_readings_daily"),
    ("residence_hourly_by_residence", "hour_ts", "residence_hourly_by_residence"),
    ("residence_daily_by_residence", "day_ts", "residence_daily_by_residence"),
]


def date_range(start: dt.date, end: dt.date) -> List[dt.date]:
    cur = start
    out = []
    while cur <= end:
        out.append(cur)
        cur += dt.timedelta(days=1)
    return out


def run_count_query(client: bigquery.Client, project: str, dataset: str, table: str, ts_col: str, start: dt.date, end: dt.date):
    sql = f"""
    SELECT
      DATE({ts_col}) AS d,
      COUNT(*) AS row_count
    FROM `{project}.{dataset}.{table}`
    WHERE DATE({ts_col}) BETWEEN @start AND @end
    GROUP BY d
    ORDER BY d
    """
    job = client.query(
        sql,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start", "DATE", start.isoformat()),
                bigquery.ScalarQueryParameter("end", "DATE", end.isoformat()),
            ]
        ),
    )
    return list(job.result())


def _gcs_stats_for_date(bucket: str, prefix: str, source: str, date: dt.date):
    """Return (file_count, total_bytes) for gs://bucket/prefix/source=<SRC>/agg=raw/dt=<date>/"""
    client = storage.Client()
    dir_prefix = f"{prefix.rstrip('/')}/source={source}/agg=raw/dt={date.isoformat()}/"
    blobs = client.list_blobs(bucket, prefix=dir_prefix)
    count = 0
    total = 0
    for b in blobs:
        if b.name.endswith('.parquet'):
            count += 1
            total += int(b.size or 0)
    return count, total


def _external_table_row_count(client: bigquery.Client, project: str, dataset: str, external_table: str, date: dt.date) -> int:
    sql = f"""
    SELECT COUNT(*) c
    FROM `{project}.{dataset}.{external_table}`
    WHERE REGEXP_CONTAINS(_FILE_NAME, @dtpath)
    """
    job = client.query(sql, job_config=bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("dtpath", "STRING", f"/dt={date.isoformat()}/")]
    ))
    for row in job.result():
        return int(row[0])
    return 0


def main():
    ap = argparse.ArgumentParser(description="Verify BigQuery outputs")
    ap.add_argument("--project", required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument(
        "--tables",
        help="Comma-separated list like table:ts_col[:label]",
    default=",".join([f"{t}:{c}:{label}" for t, c, label in DEFAULT_TABLES]),
    )
    ap.add_argument("--compare", action="store_true", help="Compare materialized/native counts to external-table rows and GCS object stats for WU/TSI")
    ap.add_argument("--gcs-bucket", default="sensor-data-to-bigquery", help="GCS bucket for raw parquet (for compare mode)")
    ap.add_argument("--gcs-prefix", default="raw", help="GCS prefix for raw parquet (for compare mode)")
    # Optional skip flags to reduce noise in environments without GCS/external access
    ap.add_argument("--skip-gcs", action="store_true", help="Skip GCS listing/stats in compare mode")
    ap.add_argument("--skip-external", action="store_true", help="Skip querying external tables in compare mode")
    args = ap.parse_args()

    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)

    # Parse tables specification
    parsed: List[Tuple[str, str, str]] = []
    for item in args.tables.split(","):
        parts = item.split(":")
        if len(parts) == 2:
            t, col = parts
            label = t
        elif len(parts) >= 3:
            t, col, label = parts[0], parts[1], ":".join(parts[2:])
        else:
            raise SystemExit(f"Invalid table spec: {item}")
        parsed.append((t.strip(), col.strip(), label.strip()))

    client = bigquery.Client(project=args.project)

    print(f"BigQuery verification for {args.project}.{args.dataset} from {start} to {end}\n")

    for table, ts_col, label in parsed:
        print(f"== {label} (table `{args.project}.{args.dataset}.{table}`, date on `{ts_col}`) ==")
        try:
            rows = run_count_query(client, args.project, args.dataset, table, ts_col, start, end)
            if not rows:
                print("  No rows in range.")
            else:
                for r in rows:
                    print(f"  {r['d']}: {r['row_count']:,}")
        except Exception as e:
            print(f"  ERROR: {e}")
        print()

    if args.compare:
        print("== Compare materialized vs external vs GCS (WU, TSI) ==")
        for src in ("WU", "TSI"):
            ext = f"{src.lower()}_raw_external"
            mat = f"{src.lower()}_raw_materialized"
            print(f"-- Source {src} --")
            cur = start
            while cur <= end:
                # GCS stats (optional)
                if args.skip_gcs:
                    gcs_files, gcs_bytes = None, None
                else:
                    try:
                        gcs_files, gcs_bytes = _gcs_stats_for_date(args.gcs_bucket, args.gcs_prefix, src, cur)
                    except Exception as e:
                        gcs_files, gcs_bytes = -1, -1
                        print(f"  {cur} GCS stats error: {e}")

                # External table row count (optional)
                if args.skip_external:
                    ext_rows = None
                else:
                    try:
                        ext_rows = _external_table_row_count(client, args.project, args.dataset, ext, cur)
                    except Exception as e:
                        ext_rows = -1
                        print(f"  {cur} external count error: {e}")
                try:
                    mat_rows = run_count_query(client, args.project, args.dataset, mat, "ts", cur, cur)
                    mat_rows = int(mat_rows[0]["row_count"]) if mat_rows else 0
                except Exception as e:
                    mat_rows = -1
                    print(f"  {cur} materialized count error: {e}")
                # Compute delta only when we have a concrete ext_rows value (not skipped or error)
                if ext_rows is None:
                    delta = None
                    status = "SKIP"
                else:
                    delta = None if (ext_rows < 0 or mat_rows < 0) else (mat_rows - ext_rows)
                    status = "OK" if (delta is not None and abs(delta) == 0) else ("WARN" if delta is not None else "ERR")

                # Friendly formatting
                def fmt(v):
                    if v is None:
                        return "n/a"
                    try:
                        return f"{v:,}"
                    except Exception:
                        return str(v)

                print(f"  {cur}: files={fmt(gcs_files)} bytes={fmt(gcs_bytes)} ext_rows={fmt(ext_rows)} mat_rows={fmt(mat_rows)} delta={delta} [{status}]")
                cur += dt.timedelta(days=1)
            print()


if __name__ == "__main__":
    main()
