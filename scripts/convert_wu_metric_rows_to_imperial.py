#!/usr/bin/env python3
"""Convert metric-era WU raw rows to imperial with minimal blast radius.

Default behavior is verify-only. Execute mode updates only rows that are
strongly metric-like by pressure scale (mb), using:

  COALESCE(pressure_max, pressure_min) > 100

This keeps already-imperial rows untouched and makes reruns idempotent.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict

try:
    from google.cloud import bigquery
except ImportError:
    bigquery = None  # type: ignore


DEFAULT_PROJECT = (
    os.getenv("GCP_PROJECT_ID") or os.getenv("BQ_PROJECT") or "durham-weather-466502"
)
DEFAULT_DATASET = os.getenv("BQ_DATASET") or "sensors"
DEFAULT_TABLE = "wu_raw_materialized"

# Conversion constants
KMH_TO_MPH = 0.621371
MM_TO_IN = 1.0 / 25.4
MB_TO_INHG = 0.029529983071445

METRIC_LIKE_PREDICATE = "COALESCE(pressure_max, pressure_min) > 100"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify and convert WU metric-era rows to imperial."
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--table", default=DEFAULT_TABLE)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD inclusive")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD inclusive")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run UPDATE. Default is read-only verification.",
    )
    parser.add_argument(
        "--confirm",
        choices=["metric_to_imperial"],
        default=None,
        help="Required with --execute.",
    )
    return parser.parse_args()


def ensure_ca_bundle() -> None:
    if os.getenv("REQUESTS_CA_BUNDLE") or os.getenv("SSL_CERT_FILE"):
        return
    for candidate in ("/etc/ssl/cert.pem", "/private/etc/ssl/cert.pem"):
        if Path(candidate).exists():
            os.environ["REQUESTS_CA_BUNDLE"] = candidate
            os.environ["SSL_CERT_FILE"] = candidate
            return


def fetch_stats(
    client: bigquery.Client, table_fq: str, start_date: str, end_date: str
) -> Dict[str, Any]:
    query = f"""
    WITH in_range AS (
      SELECT *
      FROM `{table_fq}`
      WHERE DATE(ts) BETWEEN @start_date AND @end_date
    )
    SELECT
      COUNT(*) AS total_rows,
      COUNTIF({METRIC_LIKE_PREDICATE}) AS metric_like_rows,
      COUNTIF(COALESCE(pressure_max, pressure_min) BETWEEN 20 AND 40) AS imperial_like_rows,
      COUNTIF(pressure_max IS NULL AND pressure_min IS NULL) AS pressure_missing_rows,
      MIN(DATE(ts)) AS min_date,
      MAX(DATE(ts)) AS max_date,
      MIN(IF({METRIC_LIKE_PREDICATE}, temperature, NULL)) AS metric_like_min_temp,
      APPROX_QUANTILES(IF({METRIC_LIKE_PREDICATE}, temperature, NULL), 100)[SAFE_OFFSET(50)] AS metric_like_p50_temp,
      MAX(IF({METRIC_LIKE_PREDICATE}, temperature, NULL)) AS metric_like_max_temp,
      MIN(IF({METRIC_LIKE_PREDICATE}, pressure_max, NULL)) AS metric_like_min_pressure,
      APPROX_QUANTILES(IF({METRIC_LIKE_PREDICATE}, pressure_max, NULL), 100)[SAFE_OFFSET(50)] AS metric_like_p50_pressure,
      MAX(IF({METRIC_LIKE_PREDICATE}, pressure_max, NULL)) AS metric_like_max_pressure
    FROM in_range
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
    row = next(iter(job.result()), None)
    return dict(row.items()) if row else {}


def print_stats(title: str, stats: Dict[str, Any]) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    if not stats:
        print("No rows.")
        return
    ordered_keys = [
        "total_rows",
        "metric_like_rows",
        "imperial_like_rows",
        "pressure_missing_rows",
        "min_date",
        "max_date",
        "metric_like_min_temp",
        "metric_like_p50_temp",
        "metric_like_max_temp",
        "metric_like_min_pressure",
        "metric_like_p50_pressure",
        "metric_like_max_pressure",
    ]
    for key in ordered_keys:
        print(f"{key:>24}: {stats.get(key)}")


def convert_rows(client: bigquery.Client, table_fq: str, start_date: str, end_date: str) -> int:
    query = f"""
    UPDATE `{table_fq}`
    SET
      temperature = IF(temperature IS NULL, NULL, ROUND((temperature * 9.0 / 5.0) + 32.0, 6)),
      temperature_high = IF(temperature_high IS NULL, NULL, ROUND((temperature_high * 9.0 / 5.0) + 32.0, 6)),
      temperature_low = IF(temperature_low IS NULL, NULL, ROUND((temperature_low * 9.0 / 5.0) + 32.0, 6)),
      dew_point_avg = IF(dew_point_avg IS NULL, NULL, ROUND((dew_point_avg * 9.0 / 5.0) + 32.0, 6)),
      dew_point_high = IF(dew_point_high IS NULL, NULL, ROUND((dew_point_high * 9.0 / 5.0) + 32.0, 6)),
      dew_point_low = IF(dew_point_low IS NULL, NULL, ROUND((dew_point_low * 9.0 / 5.0) + 32.0, 6)),
      heat_index_avg = IF(heat_index_avg IS NULL, NULL, ROUND((heat_index_avg * 9.0 / 5.0) + 32.0, 6)),
      heat_index_high = IF(heat_index_high IS NULL, NULL, ROUND((heat_index_high * 9.0 / 5.0) + 32.0, 6)),
      heat_index_low = IF(heat_index_low IS NULL, NULL, ROUND((heat_index_low * 9.0 / 5.0) + 32.0, 6)),
      wind_chill_avg = IF(wind_chill_avg IS NULL, NULL, ROUND((wind_chill_avg * 9.0 / 5.0) + 32.0, 6)),
      wind_chill_high = IF(wind_chill_high IS NULL, NULL, ROUND((wind_chill_high * 9.0 / 5.0) + 32.0, 6)),
      wind_chill_low = IF(wind_chill_low IS NULL, NULL, ROUND((wind_chill_low * 9.0 / 5.0) + 32.0, 6)),
      wind_speed_avg = IF(wind_speed_avg IS NULL, NULL, ROUND(wind_speed_avg * {KMH_TO_MPH}, 6)),
      wind_speed_high = IF(wind_speed_high IS NULL, NULL, ROUND(wind_speed_high * {KMH_TO_MPH}, 6)),
      wind_speed_low = IF(wind_speed_low IS NULL, NULL, ROUND(wind_speed_low * {KMH_TO_MPH}, 6)),
      wind_gust_avg = IF(wind_gust_avg IS NULL, NULL, ROUND(wind_gust_avg * {KMH_TO_MPH}, 6)),
      wind_gust_high = IF(wind_gust_high IS NULL, NULL, ROUND(wind_gust_high * {KMH_TO_MPH}, 6)),
      wind_gust_low = IF(wind_gust_low IS NULL, NULL, ROUND(wind_gust_low * {KMH_TO_MPH}, 6)),
      precip_rate = IF(precip_rate IS NULL, NULL, ROUND(precip_rate * {MM_TO_IN}, 6)),
      precip_total = IF(precip_total IS NULL, NULL, ROUND(precip_total * {MM_TO_IN}, 6)),
      pressure_max = IF(pressure_max IS NULL, NULL, ROUND(pressure_max * {MB_TO_INHG}, 6)),
      pressure_min = IF(pressure_min IS NULL, NULL, ROUND(pressure_min * {MB_TO_INHG}, 6)),
      pressure_trend = IF(pressure_trend IS NULL, NULL, ROUND(pressure_trend * {MB_TO_INHG}, 6))
    WHERE DATE(ts) BETWEEN @start_date AND @end_date
      AND {METRIC_LIKE_PREDICATE}
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


def main() -> None:
    args = parse_args()
    if bigquery is None:
        sys.exit(
            "Missing dependency: google-cloud-bigquery. "
            "Install in uv env: uv add google-cloud-bigquery"
        )

    ensure_ca_bundle()
    table_fq = f"{args.project}.{args.dataset}.{args.table}"
    client = bigquery.Client(project=args.project)

    print("WU metric->imperial conversion")
    print(f"project: {args.project}")
    print(f"dataset: {args.dataset}")
    print(f"table  : {args.table}")
    print(f"range  : {args.start} -> {args.end}")
    print(f"mode   : {'EXECUTE' if args.execute else 'VERIFY'}")
    print(f"filter : {METRIC_LIKE_PREDICATE}")

    before = fetch_stats(client, table_fq, args.start, args.end)
    print_stats("Before conversion", before)

    if not args.execute:
        print("\nNo data changed. Re-run with --execute --confirm metric_to_imperial")
        return

    if args.confirm != "metric_to_imperial":
        sys.exit("Blocked: --execute requires --confirm metric_to_imperial")

    updated = convert_rows(client, table_fq, args.start, args.end)
    print(f"\nUpdated rows: {updated}")

    after = fetch_stats(client, table_fq, args.start, args.end)
    print_stats("After conversion", after)

    print("\nNext step: rebuild targeted WU transformed metrics for same date range.")
    print(
        "uv run python scripts/backfill_wu_unit_metrics.py "
        f"--start {args.start} --end {args.end} --execute"
    )


if __name__ == "__main__":
    main()
