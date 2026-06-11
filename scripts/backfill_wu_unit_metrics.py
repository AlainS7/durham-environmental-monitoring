#!/usr/bin/env python3
"""Targeted WU transformed-metric backfill after unit conversion.

Blast-radius controls:
- source = 'wu' only
- metrics = unit-bearing weather metrics + temperature_calibrated
- date range scoped
- dry-run by default
"""

from __future__ import annotations

import argparse
import os
import sys
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

WU_RAW_METRICS = [
    "temperature",
    "temperature_high",
    "temperature_low",
    "precip_rate",
    "precip_total",
    "pressure_max",
    "pressure_min",
    "pressure_trend",
    "wind_speed_avg",
    "wind_speed_high",
    "wind_speed_low",
    "wind_gust_avg",
    "wind_gust_high",
    "wind_gust_low",
    "dew_point_avg",
    "dew_point_high",
    "dew_point_low",
    "heat_index_avg",
    "heat_index_high",
    "heat_index_low",
    "wind_chill_avg",
    "wind_chill_high",
    "wind_chill_low",
]

WU_ALL_METRICS = WU_RAW_METRICS + ["temperature_calibrated"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Targeted WU unit metric backfill.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD inclusive")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD inclusive")
    parser.add_argument("--execute", action="store_true")
    return parser.parse_args()


def ensure_ca_bundle() -> None:
    if os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE"):
        return
    for candidate in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
        if Path(candidate).exists():
            os.environ["REQUESTS_CA_BUNDLE"] = candidate
            os.environ["SSL_CERT_FILE"] = candidate
            return


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
      AND source = 'wu'
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
      AND source = 'wu'
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


def run_insert_long(client: bigquery.Client, project: str, dataset: str, start_date: str, end_date: str) -> int:
    query = f"""
    INSERT INTO `{project}.{dataset}.sensor_readings_long`
      (timestamp, timestamp_date, native_sensor_id, metric_name, value, source, row_id)
    WITH wu_src AS (
      SELECT
        ts AS timestamp,
        native_sensor_id,
        CAST(temperature AS FLOAT64) AS temperature,
        CAST(temperature_high AS FLOAT64) AS temperature_high,
        CAST(temperature_low AS FLOAT64) AS temperature_low,
        CAST(precip_rate AS FLOAT64) AS precip_rate,
        CAST(precip_total AS FLOAT64) AS precip_total,
        CAST(pressure_max AS FLOAT64) AS pressure_max,
        CAST(pressure_min AS FLOAT64) AS pressure_min,
        CAST(pressure_trend AS FLOAT64) AS pressure_trend,
        CAST(wind_speed_avg AS FLOAT64) AS wind_speed_avg,
        CAST(wind_speed_high AS FLOAT64) AS wind_speed_high,
        CAST(wind_speed_low AS FLOAT64) AS wind_speed_low,
        CAST(wind_gust_avg AS FLOAT64) AS wind_gust_avg,
        CAST(wind_gust_high AS FLOAT64) AS wind_gust_high,
        CAST(wind_gust_low AS FLOAT64) AS wind_gust_low,
        CAST(dew_point_avg AS FLOAT64) AS dew_point_avg,
        CAST(dew_point_high AS FLOAT64) AS dew_point_high,
        CAST(dew_point_low AS FLOAT64) AS dew_point_low,
        CAST(heat_index_avg AS FLOAT64) AS heat_index_avg,
        CAST(heat_index_high AS FLOAT64) AS heat_index_high,
        CAST(heat_index_low AS FLOAT64) AS heat_index_low,
        CAST(wind_chill_avg AS FLOAT64) AS wind_chill_avg,
        CAST(wind_chill_high AS FLOAT64) AS wind_chill_high,
        CAST(wind_chill_low AS FLOAT64) AS wind_chill_low
      FROM `{project}.{dataset}.wu_raw_materialized`
      WHERE ts IS NOT NULL
        AND DATE(ts) BETWEEN @start_date AND @end_date
    ),
    wu_long AS (
      SELECT timestamp, native_sensor_id, metric_name, value, 'wu' AS source
      FROM wu_src
      UNPIVOT (value FOR metric_name IN (
        temperature, temperature_high, temperature_low,
        precip_rate, precip_total,
        pressure_max, pressure_min, pressure_trend,
        wind_speed_avg, wind_speed_high, wind_speed_low,
        wind_gust_avg, wind_gust_high, wind_gust_low,
        dew_point_avg, dew_point_high, dew_point_low,
        heat_index_avg, heat_index_high, heat_index_low,
        wind_chill_avg, wind_chill_high, wind_chill_low
      ))
    ),
    wu_temp_calibrated AS (
      SELECT
        wu.timestamp,
        wu.native_sensor_id,
        'temperature_calibrated' AS metric_name,
        CAST((wu.value * c.a_temp) + c.b_temp AS FLOAT64) AS value,
        'wu' AS source
      FROM wu_long wu
      LEFT JOIN `{project}.{dataset}.wu_calibration_config` c
        ON wu.native_sensor_id = c.stationId
      WHERE wu.metric_name = 'temperature'
        AND c.a_temp IS NOT NULL
    ),
    all_rows AS (
      SELECT * FROM wu_long
      UNION ALL
      SELECT * FROM wu_temp_calibrated
    )
    SELECT
      timestamp,
      DATE(timestamp) AS timestamp_date,
      native_sensor_id,
      metric_name,
      value,
      source,
      FARM_FINGERPRINT(CONCAT(CAST(timestamp AS STRING), native_sensor_id, metric_name)) AS row_id
    FROM all_rows
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
        AND source = 'wu'
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


def main() -> None:
    args = parse_args()
    if bigquery is None:
        sys.exit(
            "Missing dependency: google-cloud-bigquery. "
            "Install in uv env: uv add google-cloud-bigquery"
        )

    ensure_ca_bundle()
    client = bigquery.Client(project=args.project)
    long_fq = f"{args.project}.{args.dataset}.sensor_readings_long"
    hourly_fq = f"{args.project}.{args.dataset}.sensor_readings_hourly"
    daily_fq = f"{args.project}.{args.dataset}.sensor_readings_daily"

    print("Targeted WU unit-metric backfill")
    print(f"project: {args.project}")
    print(f"dataset: {args.dataset}")
    print(f"range  : {args.start} -> {args.end}")
    print(f"metrics: {WU_ALL_METRICS}")
    print(f"mode   : {'EXECUTE' if args.execute else 'DRY-RUN'}")

    impacted_long = impact_count(client, long_fq, "timestamp", args.start, args.end, WU_ALL_METRICS)
    impacted_hourly = impact_count(client, hourly_fq, "hour_ts", args.start, args.end, WU_ALL_METRICS)
    impacted_daily = impact_count(client, daily_fq, "day_ts", args.start, args.end, WU_ALL_METRICS)

    print("\nCurrent rows matching targeted slice:")
    print(f"sensor_readings_long   : {impacted_long}")
    print(f"sensor_readings_hourly : {impacted_hourly}")
    print(f"sensor_readings_daily  : {impacted_daily}")

    if not args.execute:
        print("\nNo data changed. Add --execute to apply.")
        return

    totals = {
        "long_deleted": run_delete(client, long_fq, "timestamp", args.start, args.end, WU_ALL_METRICS),
        "long_inserted": run_insert_long(client, args.project, args.dataset, args.start, args.end),
    }

    totals["hourly_deleted"] = run_delete(client, hourly_fq, "hour_ts", args.start, args.end, WU_ALL_METRICS)
    totals["hourly_inserted"] = run_insert_aggregate(
        client=client,
        table_fq=hourly_fq,
        ts_col="hour_ts",
        date_col="hour_date",
        truncate_expr="TIMESTAMP_TRUNC(timestamp, HOUR)",
        source_table_fq=long_fq,
        start_date=args.start,
        end_date=args.end,
        metrics=WU_ALL_METRICS,
    )

    totals["daily_deleted"] = run_delete(client, daily_fq, "day_ts", args.start, args.end, WU_ALL_METRICS)
    totals["daily_inserted"] = run_insert_aggregate(
        client=client,
        table_fq=daily_fq,
        ts_col="day_ts",
        date_col="day_date",
        truncate_expr="TIMESTAMP_TRUNC(timestamp, DAY)",
        source_table_fq=long_fq,
        start_date=args.start,
        end_date=args.end,
        metrics=WU_ALL_METRICS,
    )

    print("\nDML summary:")
    for k, v in totals.items():
        print(f"{k:>15}: {v}")


if __name__ == "__main__":
    main()
