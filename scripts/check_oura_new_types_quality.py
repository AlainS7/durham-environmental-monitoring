#!/usr/bin/env python3
"""
Lightweight data quality checks for newly added Oura tables.

Checks:
  * sleep_periods: non-null start timestamp, day, resident
  * sessions: non-null start timestamp, day, resident
  * workouts: non-null start timestamp, day, resident
  * daily_heart_rate: hr_avg between 20 and 220, hr_min<=hr_max, hr_samples>0

Usage:
  python scripts/check_oura_new_types_quality.py --dataset oura --project $BQ_PROJECT

Exit code 0 if all checks pass, 1 otherwise.
"""

from __future__ import annotations
import argparse
import os
from google.cloud import bigquery

CHECKS = [
    (
        "oura_sleep_periods",
        "SELECT COUNT(*) AS failures FROM `{project}.{dataset}.oura_sleep_periods`\n         WHERE (COALESCE(CAST(start_datetime AS TIMESTAMP), CAST(start_time AS TIMESTAMP), CAST(start AS TIMESTAMP), CAST(timestamp AS TIMESTAMP)) IS NULL)\n           OR day IS NULL\n           OR resident IS NULL",
    ),
    (
        "oura_sessions",
        "SELECT COUNT(*) AS failures FROM `{project}.{dataset}.oura_sessions`\n         WHERE (COALESCE(CAST(start_datetime AS TIMESTAMP), CAST(start_time AS TIMESTAMP), CAST(start AS TIMESTAMP), CAST(timestamp AS TIMESTAMP)) IS NULL)\n           OR day IS NULL\n           OR resident IS NULL",
    ),
    (
        "oura_workouts",
        "SELECT COUNT(*) AS failures FROM `{project}.{dataset}.oura_workouts`\n         WHERE (COALESCE(CAST(start_datetime AS TIMESTAMP), CAST(start_time AS TIMESTAMP), CAST(start AS TIMESTAMP), CAST(timestamp AS TIMESTAMP)) IS NULL)\n           OR day IS NULL\n           OR resident IS NULL",
    ),
    (
        "oura_daily_heart_rate",
        "SELECT COUNT(*) AS failures FROM `{project}.{dataset}.oura_daily_heart_rate`\n         WHERE hr_avg < 20 OR hr_avg > 220 OR hr_min > hr_max OR hr_samples <= 0",
    ),
]


def run_check(client: bigquery.Client, sql: str) -> int:
    job = client.query(sql)
    row = next(job.result())
    return int(row["failures"]) if "failures" in row.keys() else int(row[0])


def main():
    ap = argparse.ArgumentParser(description="Check Oura new tables quality")
    ap.add_argument("--dataset", default="oura")
    ap.add_argument("--project", default=os.getenv("BQ_PROJECT"))
    ap.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    args = ap.parse_args()

    client = bigquery.Client(project=args.project, location=args.location)

    failures = 0
    for name, templ in CHECKS:
        sql = templ.format(project=client.project, dataset=args.dataset)
        count = run_check(client, sql)
        status = "✅ PASS" if count == 0 else f"❌ FAIL ({count})"
        print(f"{status:10s} {name}")
        if count:
            failures += 1

    if failures:
        print(f"\nTotal failing checks: {failures}")
    else:
        print("\nAll checks passed.")

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
