#!/usr/bin/env python3
"""Verify first, then optionally convert TSI temperature from C to F.

Purpose:
- Detect whether a date range in `tsi_raw_materialized.temperature` looks like
  Celsius or Fahrenheit.
- Convert only when explicitly requested with --execute.

Safety:
- Default mode is read-only verification.
- Execute mode requires --confirm-scale celsius.
- Script blocks conversion when data already looks Fahrenheit unless --force.

Example:
  # Verify only (recommended first step)
  python3 scripts/convert_tsi_temperature_c_to_f.py --start 2025-07-07 --end 2026-02-29

  # Convert after verification
  python3 scripts/convert_tsi_temperature_c_to_f.py \
      --start 2025-07-07 --end 2026-02-29 \
      --execute --confirm-scale celsius
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List

try:
    from google.cloud import bigquery
except ImportError:
    bigquery = None  # type: ignore


DEFAULT_PROJECT = (
    os.getenv("GCP_PROJECT_ID") or os.getenv("BQ_PROJECT") or "durham-weather-466502"
)
DEFAULT_DATASET = os.getenv("BQ_DATASET") or "sensors"
DEFAULT_TABLE = "tsi_raw_materialized"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify and optionally convert historical TSI temperatures from C to F."
    )
    parser.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help=f"GCP project (default: {DEFAULT_PROJECT})",
    )
    parser.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help=f"BigQuery dataset (default: {DEFAULT_DATASET})",
    )
    parser.add_argument(
        "--table",
        default=DEFAULT_TABLE,
        help=f"BigQuery table (default: {DEFAULT_TABLE})",
    )
    parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD), inclusive.",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="End date (YYYY-MM-DD), inclusive.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Run UPDATE query. Omit for read-only verification.",
    )
    parser.add_argument(
        "--confirm-scale",
        choices=["celsius", "fahrenheit"],
        default=None,
        help="Required with --execute. Must be 'celsius' to run conversion.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow conversion even when heuristic says data already looks Fahrenheit.",
    )
    return parser.parse_args()


def fetch_stats(
    client: bigquery.Client,
    table_fq: str,
    start_date: str,
    end_date: str,
) -> Dict[str, Any]:
    query = f"""
    SELECT
      COUNT(*) AS total_rows,
      COUNTIF(temperature IS NULL) AS null_rows,
      COUNTIF(temperature IS NOT NULL) AS non_null_rows,
      MIN(temperature) AS min_temp,
      MAX(temperature) AS max_temp,
      AVG(temperature) AS avg_temp,
      APPROX_QUANTILES(temperature, 100)[SAFE_OFFSET(10)] AS p10,
      APPROX_QUANTILES(temperature, 100)[SAFE_OFFSET(50)] AS p50,
      APPROX_QUANTILES(temperature, 100)[SAFE_OFFSET(90)] AS p90,
      COUNTIF(temperature BETWEEN -40 AND 50) AS celsius_like_rows,
      COUNTIF(temperature BETWEEN 50 AND 130) AS fahrenheit_like_rows,
      COUNTIF(temperature BETWEEN 32 AND 50) AS overlap_rows
    FROM `{table_fq}`
    WHERE DATE(ts) BETWEEN @start_date AND @end_date
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
            bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
        ]
    )
    row = next(iter(client.query(query, job_config=job_config).result()), None)
    if row is None:
        return {}
    return dict(row.items())


def fetch_daily_scale_stats(
    client: bigquery.Client,
    table_fq: str,
    start_date: str,
    end_date: str,
) -> List[Dict[str, Any]]:
    """Return per-day scale signals to avoid row-only heuristics."""
    query = f"""
    SELECT
      DATE(ts) AS day,
      COUNTIF(temperature IS NOT NULL) AS non_null_rows,
      APPROX_QUANTILES(temperature, 100)[SAFE_OFFSET(50)] AS p50,
      COUNTIF(temperature BETWEEN -40 AND 50) AS celsius_like_rows,
      COUNTIF(temperature BETWEEN 50 AND 130) AS fahrenheit_like_rows
    FROM `{table_fq}`
    WHERE DATE(ts) BETWEEN @start_date AND @end_date
      AND temperature IS NOT NULL
    GROUP BY day
    ORDER BY day
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
            bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
        ]
    )
    rows = client.query(query, job_config=job_config).result()
    out: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row.items())
        non_null_rows = int(item.get("non_null_rows") or 0)
        celsius_like_rows = int(item.get("celsius_like_rows") or 0)
        p50 = float(item.get("p50") or 0.0)
        c_ratio = (celsius_like_rows / non_null_rows) if non_null_rows else 0.0
        # Celsius day if both central tendency + majority support it.
        item["celsius_ratio"] = c_ratio
        item["likely_celsius_day"] = p50 < 55.0 and c_ratio >= 0.90
        out.append(item)
    return out


def classify_scale(stats: Dict[str, Any]) -> str:
    non_null = int(stats.get("non_null_rows") or 0)
    if non_null == 0:
        return "no_temperature_data"

    p10 = float(stats.get("p10") or 0.0)
    p50 = float(stats.get("p50") or 0.0)
    p90 = float(stats.get("p90") or 0.0)

    # Heuristic only. User still confirms before execute.
    if p50 <= 45 and p90 <= 70:
        return "celsius_likely"
    if p50 >= 55 and p10 >= 32:
        return "fahrenheit_likely"
    return "mixed_or_ambiguous"


def print_stats(stats: Dict[str, Any], label: str) -> None:
    if not stats:
        print(f"{label}: no rows returned.")
        return

    print(f"\n{label}")
    print("-" * len(label))
    print(f"total_rows          : {int(stats.get('total_rows') or 0)}")
    print(f"non_null_rows       : {int(stats.get('non_null_rows') or 0)}")
    print(f"null_rows           : {int(stats.get('null_rows') or 0)}")
    print(f"min_temp            : {stats.get('min_temp')}")
    print(f"p10                 : {stats.get('p10')}")
    print(f"p50                 : {stats.get('p50')}")
    print(f"p90                 : {stats.get('p90')}")
    print(f"max_temp            : {stats.get('max_temp')}")
    print(f"avg_temp            : {stats.get('avg_temp')}")
    print(f"celsius_like_rows   : {int(stats.get('celsius_like_rows') or 0)}")
    print(f"fahrenheit_like_rows: {int(stats.get('fahrenheit_like_rows') or 0)}")
    print(f"overlap_rows_32_50  : {int(stats.get('overlap_rows') or 0)}")


def print_daily_scale_stats(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        print("\nDaily scale scan: no non-null temperature rows.")
        return
    print("\nDaily scale scan")
    print("----------------")
    print("day         p50    c_ratio  likely_celsius")
    for r in rows:
        day = str(r.get("day"))
        p50 = float(r.get("p50") or 0.0)
        c_ratio = float(r.get("celsius_ratio") or 0.0)
        likely = bool(r.get("likely_celsius_day"))
        print(f"{day}  {p50:6.2f}  {c_ratio:7.3f}  {str(likely).lower()}")


def convert_temperature(
    client: bigquery.Client,
    table_fq: str,
    start_date: str,
    end_date: str,
) -> int:
    # Convert only days strongly classified as Celsius-like.
    query = f"""
    WITH daily_scale AS (
      SELECT
        DATE(ts) AS day,
        APPROX_QUANTILES(temperature, 100)[SAFE_OFFSET(50)] AS p50,
        SAFE_DIVIDE(
          COUNTIF(temperature BETWEEN -40 AND 50),
          COUNTIF(temperature IS NOT NULL)
        ) AS celsius_ratio
      FROM `{table_fq}`
      WHERE DATE(ts) BETWEEN @start_date AND @end_date
        AND temperature IS NOT NULL
      GROUP BY day
    ),
    celsius_days AS (
      SELECT day
      FROM daily_scale
      WHERE p50 < 55.0
        AND celsius_ratio >= 0.90
    )
    UPDATE `{table_fq}`
    SET temperature = ROUND((temperature * 9.0 / 5.0) + 32.0, 6)
    WHERE DATE(ts) IN (SELECT day FROM celsius_days)
      AND temperature IS NOT NULL
      AND temperature BETWEEN -40 AND 60
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
            bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
        ]
    )
    job = client.query(query, job_config=job_config)
    job.result()
    return int(job.num_dml_affected_rows or 0)


def main() -> None:
    args = parse_args()
    table_fq = f"{args.project}.{args.dataset}.{args.table}"

    if bigquery is None:
        sys.exit(
            "Missing dependency: google-cloud-bigquery. "
            "Install with: pip install google-cloud-bigquery"
        )

    print("TSI temperature unit verification/conversion")
    print(f"project: {args.project}")
    print(f"dataset: {args.dataset}")
    print(f"table  : {args.table}")
    print(f"range  : {args.start} -> {args.end}")
    print(f"mode   : {'EXECUTE' if args.execute else 'VERIFY'}")

    client = bigquery.Client(project=args.project)
    before_stats = fetch_stats(client, table_fq, args.start, args.end)
    print_stats(before_stats, "Before conversion")
    classification = classify_scale(before_stats)
    print(f"\nscale_assessment: {classification}")
    daily_rows = fetch_daily_scale_stats(client, table_fq, args.start, args.end)
    print_daily_scale_stats(daily_rows)
    candidate_days = [str(r["day"]) for r in daily_rows if r.get("likely_celsius_day")]
    print(f"\nlikely_celsius_days: {len(candidate_days)}")
    if candidate_days:
        print("days: " + ", ".join(candidate_days))

    if not args.execute:
        print("\nNo data changed. Re-run with --execute only after manual review.")
        return

    if args.confirm_scale != "celsius":
        sys.exit("Blocked: --execute requires --confirm-scale celsius")

    if not candidate_days and classification == "fahrenheit_likely" and not args.force:
        print("\nNo likely Celsius days found in range. Nothing to convert.")
        return

    affected = convert_temperature(client, table_fq, args.start, args.end)
    print(f"\nUpdated rows: {affected}")

    after_stats = fetch_stats(client, table_fq, args.start, args.end)
    print_stats(after_stats, "After conversion")
    after_classification = classify_scale(after_stats)
    print(f"\npost_conversion_scale_assessment: {after_classification}")

    print("\nNext step: rebuild derived tables for same date range:")
    print(
        "python3 scripts/backfill_transformations.py "
        f"--start {args.start} --end {args.end} --execute"
    )


if __name__ == "__main__":
    main()
