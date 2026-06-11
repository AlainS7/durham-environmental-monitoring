#!/usr/bin/env python3
"""Backfill only TSI temperature-related metrics in transformed tables.

Goal:
- Keep WU untouched.
- Keep non-temperature metrics untouched.
- Refresh only selected TSI metrics in:
  - sensor_readings_long
  - sensor_readings_hourly
  - sensor_readings_daily

Default mode is dry-run (impact report only).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path
from typing import List

try:
    from google.cloud import bigquery
except ImportError:
    bigquery = None  # type: ignore


DEFAULT_PROJECT = (
    os.getenv("GCP_PROJECT_ID") or os.getenv("BQ_PROJECT") or "durham-weather-466502"
)
DEFAULT_DATASET = os.getenv("BQ_DATASET") or "sensors"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Targeted TSI-only temperature metric backfill."
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD (inclusive)")
    parser.add_argument(
        "--include-temperature-harmonized",
        action="store_true",
        help="Also refresh temperature_harmonized metric rows.",
    )
    parser.add_argument(
        "--include-pm25-mv-corrected",
        action="store_true",
        help="Also refresh pm2_5_mv_corrected metric rows.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run DELETE/INSERT. Default is dry-run impact report.",
    )
    return parser.parse_args()


def metric_list(args: argparse.Namespace) -> List[str]:
    metrics = ["temperature"]
    if args.include_temperature_harmonized:
        metrics.append("temperature_harmonized")
    if args.include_pm25_mv_corrected:
        metrics.append("pm2_5_mv_corrected")
    return metrics


def impact_count(
    client: bigquery.Client,
    table_fq: str,
    ts_col: str,
    start: str,
    end: str,
    metrics: List[str],
) -> int:
    query = f"""
    SELECT COUNT(*) AS n
    FROM `{table_fq}`
    WHERE DATE({ts_col}) BETWEEN @start_date AND @end_date
      AND source = 'tsi'
      AND metric_name IN UNNEST(@metrics)
    """
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_date", "DATE", start),
                bigquery.ScalarQueryParameter("end_date", "DATE", end),
                bigquery.ArrayQueryParameter("metrics", "STRING", metrics),
            ]
        ),
    )
    return int(next(iter(job.result()))["n"])


def run_delete(
    client: bigquery.Client,
    table_fq: str,
    ts_col: str,
    start_date: str,
    end_date: str,
    metrics: List[str],
) -> int:
    query = f"""
    DELETE FROM `{table_fq}`
    WHERE DATE({ts_col}) BETWEEN @start_date AND @end_date
      AND source = 'tsi'
      AND metric_name IN UNNEST(@metrics)
    """
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
                bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
                bigquery.ArrayQueryParameter("metrics", "STRING", metrics),
            ]
        ),
    )
    job.result()
    return int(job.num_dml_affected_rows or 0)


def run_insert_long(
    client: bigquery.Client,
    project: str,
    dataset: str,
    start_date: str,
    end_date: str,
    metrics: List[str],
) -> int:
    include_temp_h = "temperature_harmonized" in metrics
    include_pm25_mv = "pm2_5_mv_corrected" in metrics

    union_blocks = [
        """
        SELECT
          timestamp,
          DATE(timestamp) AS timestamp_date,
          native_sensor_id,
          'temperature' AS metric_name,
          CAST(temperature AS FLOAT64) AS value,
          'tsi' AS source
        FROM tsi_src
        WHERE temperature IS NOT NULL
        """
    ]

    if include_temp_h:
        union_blocks.append(
            """
            SELECT
              t.timestamp,
              DATE(t.timestamp) AS timestamp_date,
              t.native_sensor_id,
              'temperature_harmonized' AS metric_name,
              CAST((t.temperature * h.slope) + h.intercept AS FLOAT64) AS value,
              'tsi' AS source
            FROM tsi_src t
            INNER JOIN harmonization_rules h
              ON t.native_sensor_id = h.native_sensor_id
             AND h.effective_date <= DATE(t.timestamp)
             AND (h.end_date IS NULL OR h.end_date >= DATE(t.timestamp))
            WHERE t.temperature IS NOT NULL
            """
        )

    if include_pm25_mv:
        union_blocks.append(
            """
            SELECT
              timestamp,
              DATE(timestamp) AS timestamp_date,
              native_sensor_id,
              'pm2_5_mv_corrected' AS metric_name,
              CAST(
                GREATEST(
                  0.0,
                  CASE
                    WHEN is_indoor = TRUE THEN
                      32.37531517845487
                      + 0.7832728929424163 * pm2_5
                      + (-0.27911836195444806) * humidity
                      + (-0.06786051081629864) * temperature
                    ELSE
                      0.6319569528186428
                      + 0.6922536497361194 * pm2_5
                      + 0.06423603583020391 * temperature
                      + (-0.023752731801088067) * humidity
                  END
                ) AS FLOAT64
              ) AS value,
              'tsi' AS source
            FROM tsi_src
            WHERE pm2_5 IS NOT NULL
              AND humidity IS NOT NULL
              AND temperature IS NOT NULL
              AND pm2_5 BETWEEN 0.0 AND 1000.0
              AND humidity BETWEEN 0.0 AND 100.0
              AND temperature BETWEEN -58.0 AND 140.0
            """
        )

    cte_h_rules = ""
    if include_temp_h:
        cte_h_rules = f"""
        , harmonization_rules AS (
          SELECT native_sensor_id, slope, intercept, effective_date, end_date
          FROM `{project}.{dataset}.calibration_config`
          WHERE metric_name = 'temperature'
            AND native_sensor_id != 'DEFAULT'
        )
        """

    query = f"""
    INSERT INTO `{project}.{dataset}.sensor_readings_long`
      (timestamp, timestamp_date, native_sensor_id, metric_name, value, source, row_id)
    WITH tsi_src AS (
      SELECT
        ts AS timestamp,
        native_sensor_id,
        is_indoor,
        CAST(pm2_5 AS FLOAT64) AS pm2_5,
        CAST(humidity AS FLOAT64) AS humidity,
        CAST(temperature AS FLOAT64) AS temperature
      FROM `{project}.{dataset}.tsi_raw_materialized`
      WHERE ts IS NOT NULL
        AND DATE(ts) BETWEEN @start_date AND @end_date
    )
    {cte_h_rules}
    , metric_rows AS (
      {" UNION ALL ".join(union_blocks)}
    )
    SELECT
      timestamp,
      timestamp_date,
      native_sensor_id,
      metric_name,
      value,
      source,
      FARM_FINGERPRINT(CONCAT(CAST(timestamp AS STRING), native_sensor_id, metric_name)) AS row_id
    FROM metric_rows
    """

    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
                bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
            ]
        ),
    )
    job.result()
    return int(job.num_dml_affected_rows or 0)


def run_insert_aggregate(
    client: bigquery.Client,
    table_fq: str,
    ts_col: str,
    date_col: str,
    truncate_expr: str,
    source_table_fq: str,
    start_date: str,
    end_date: str,
    metrics: List[str],
) -> int:
    query = f"""
    INSERT INTO `{table_fq}`
      ({ts_col}, {date_col}, native_sensor_id, source, metric_name, avg_value, min_value, max_value, samples, row_id)
    WITH grouped AS (
      SELECT
        {truncate_expr} AS {ts_col},
        DATE({truncate_expr}) AS {date_col},
        native_sensor_id,
        source,
        metric_name,
        AVG(value) AS avg_value,
        MIN(value) AS min_value,
        MAX(value) AS max_value,
        COUNT(*) AS samples
      FROM `{source_table_fq}`
      WHERE DATE(timestamp) BETWEEN @start_date AND @end_date
        AND source = 'tsi'
        AND metric_name IN UNNEST(@metrics)
      GROUP BY 1,2,3,4,5
    )
    SELECT
      {ts_col},
      {date_col},
      native_sensor_id,
      source,
      metric_name,
      avg_value,
      min_value,
      max_value,
      samples,
      FARM_FINGERPRINT(
        CONCAT(
          CAST({ts_col} AS STRING),
          '|', native_sensor_id,
          '|', metric_name,
          '|', source
        )
      ) AS row_id
    FROM grouped
    """
    job = client.query(
        query,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
                bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
                bigquery.ArrayQueryParameter("metrics", "STRING", metrics),
            ]
        ),
    )
    job.result()
    return int(job.num_dml_affected_rows or 0)


def ensure_ca_bundle() -> None:
    """Set a stable CA bundle path when Python/certifi path is broken."""
    if os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE"):
        return
    candidates = [
        "/etc/ssl/cert.pem",
        "/private/etc/ssl/cert.pem",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            os.environ["REQUESTS_CA_BUNDLE"] = candidate
            os.environ["SSL_CERT_FILE"] = candidate
            return


def main() -> None:
    args = parse_args()
    if bigquery is None:
        sys.exit(
            "Missing dependency: google-cloud-bigquery. "
            "Install with: pip install google-cloud-bigquery"
        )

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    if start > end:
        sys.exit("Invalid date range: start > end")

    metrics = metric_list(args)
    ensure_ca_bundle()
    client = bigquery.Client(project=args.project)

    long_fq = f"{args.project}.{args.dataset}.sensor_readings_long"
    hourly_fq = f"{args.project}.{args.dataset}.sensor_readings_hourly"
    daily_fq = f"{args.project}.{args.dataset}.sensor_readings_daily"

    print("Targeted TSI metric backfill")
    print(f"project: {args.project}")
    print(f"dataset: {args.dataset}")
    print(f"range  : {args.start} -> {args.end}")
    print(f"metrics: {metrics}")
    print(f"mode   : {'EXECUTE' if args.execute else 'DRY-RUN'}")

    impacted_long = impact_count(client, long_fq, "timestamp", args.start, args.end, metrics)
    impacted_hourly = impact_count(client, hourly_fq, "hour_ts", args.start, args.end, metrics)
    impacted_daily = impact_count(client, daily_fq, "day_ts", args.start, args.end, metrics)

    print("\nCurrent rows matching targeted slice:")
    print(f"sensor_readings_long   : {impacted_long}")
    print(f"sensor_readings_hourly : {impacted_hourly}")
    print(f"sensor_readings_daily  : {impacted_daily}")

    if not args.execute:
        print("\nNo data changed.")
        print("Run with --execute to apply targeted refresh.")
        return

    totals = {
        "long_deleted": 0,
        "long_inserted": 0,
        "hourly_deleted": 0,
        "hourly_inserted": 0,
        "daily_deleted": 0,
        "daily_inserted": 0,
    }

    start_date = start.isoformat()
    end_date = end.isoformat()

    totals["long_deleted"] += run_delete(
        client, long_fq, "timestamp", start_date, end_date, metrics
    )
    totals["long_inserted"] += run_insert_long(
        client, args.project, args.dataset, start_date, end_date, metrics
    )

    totals["hourly_deleted"] += run_delete(
        client, hourly_fq, "hour_ts", start_date, end_date, metrics
    )
    totals["hourly_inserted"] += run_insert_aggregate(
        client=client,
        table_fq=hourly_fq,
        ts_col="hour_ts",
        date_col="hour_date",
        truncate_expr="TIMESTAMP_TRUNC(timestamp, HOUR)",
        source_table_fq=long_fq,
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
    )

    totals["daily_deleted"] += run_delete(
        client, daily_fq, "day_ts", start_date, end_date, metrics
    )
    totals["daily_inserted"] += run_insert_aggregate(
        client=client,
        table_fq=daily_fq,
        ts_col="day_ts",
        date_col="day_date",
        truncate_expr="TIMESTAMP_TRUNC(timestamp, DAY)",
        source_table_fq=long_fq,
        start_date=start_date,
        end_date=end_date,
        metrics=metrics,
    )

    print("\nDML summary:")
    for k, v in totals.items():
        print(f"{k:>15}: {v}")


if __name__ == "__main__":
    main()
