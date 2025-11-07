#!/usr/bin/env python3
"""
Estimate BigQuery on-demand query cost for merging per-source dated staging (WU/TSI)
into the consolidated table over a date range, using dry-run bytes processed.

This mirrors the per-source dated MERGE used by scripts/merge_backfill_range.py
and runs each day's MERGE as a dry-run to collect total_bytes_processed.

Notes:
- This estimates query processing cost only. Storage, Cloud Run, egress, or API costs are not included.
- Pricing varies by region and plan. Configure price per TB via --price-per-tb (default 6.0 USD/TB).
- Requires permissions to query metadata and staging/target tables.

Usage:
  python scripts/estimate_sensor_costs.py \
    --project durham-weather-466502 --dataset sensors \
    --start 2025-10-05 --end 2025-11-07 \
    --sources tsi,wu --target-table sensor_readings \
    --price-per-tb 6
"""

from __future__ import annotations

import argparse
import datetime as dt
from typing import List

from google.cloud import bigquery
from google.cloud.exceptions import NotFound


def parse_args():
    p = argparse.ArgumentParser(
        description="Estimate BigQuery MERGE cost for WU/TSI staging"
    )
    p.add_argument("--project", required=False, help="GCP Project ID (ADC if omitted)")
    p.add_argument("--dataset", default="sensors")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--location", default="US")
    p.add_argument("--sources", default="tsi,wu", help="Comma separated sources")
    p.add_argument("--target-table", default="sensor_readings")
    p.add_argument(
        "--price-per-tb",
        type=float,
        default=6.0,
        help="USD per TB processed (query cost)",
    )
    p.add_argument(
        "--storage-price-per-gb-month",
        type=float,
        default=0.02,
        help="USD per GB-month (logical bytes storage cost)",
    )
    p.add_argument(
        "--storage-days",
        type=int,
        default=30,
        help="Days of storage to estimate (prorates GB-month by days/30)",
    )
    return p.parse_args()


def daterange(start: dt.date, end: dt.date):
    cur = start
    while cur <= end:
        yield cur
        cur += dt.timedelta(days=1)


def table_exists(client: bigquery.Client, dataset: str, table: str) -> bool:
    try:
        client.get_table(f"{dataset}.{table}")
        return True
    except NotFound:
        return False


def build_merge_sql(
    project: str, dataset: str, target_table: str, staging_tables: List[str]
) -> str:
    selects = [
        f"SELECT CAST(timestamp AS TIMESTAMP) AS timestamp, deployment_fk, metric_name, value FROM `{project}.{dataset}.{t}`"
        for t in staging_tables
    ]
    union = "\nUNION ALL\n".join(selects)
    sql = f"""
MERGE `{project}.{dataset}.{target_table}` T
USING (
  {union}
) S
ON T.timestamp = S.timestamp AND T.deployment_fk = S.deployment_fk AND T.metric_name = S.metric_name
WHEN MATCHED THEN UPDATE SET value = S.value
WHEN NOT MATCHED THEN INSERT (timestamp, deployment_fk, metric_name, value)
VALUES (S.timestamp, S.deployment_fk, S.metric_name, S.value)
""".strip()
    return sql


def main():
    a = parse_args()
    client = bigquery.Client(project=a.project, location=a.location)
    start = dt.date.fromisoformat(a.start)
    end = dt.date.fromisoformat(a.end)
    sources = [s.strip() for s in a.sources.split(",") if s.strip()]
    total_bytes = 0
    day_bytes: list[tuple[str, int]] = []
    staging_tables_all: list[str] = []

    for day in daterange(start, end):
        ds = day.strftime("%Y%m%d")
        existing: List[str] = []
        for src in sources:
            t = f"staging_{src}_{ds}"
            if table_exists(client, a.dataset, t):
                existing.append(t)
        if not existing:
            continue
        staging_tables_all.extend(existing)
        sql = build_merge_sql(client.project, a.dataset, a.target_table, existing)
        job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        job = client.query(sql, job_config=job_config)
        b = int(job.total_bytes_processed or 0)
        total_bytes += b
        day_bytes.append((day.isoformat(), b))

    total_tb = total_bytes / (1024**4)
    est_cost = total_tb * a.price_per_tb

    # Storage estimation (approximate): sum logical bytes of involved staging tables
    storage_bytes = 0
    if staging_tables_all:
        # Query __TABLES__ for size_bytes
        # Build IN list safely via query parameters
        placeholders = ", ".join([f"@t{i}" for i in range(len(staging_tables_all))])
        sql_storage = f"""
        SELECT COALESCE(SUM(size_bytes), 0) AS total
        FROM `{client.project}.{a.dataset}.__TABLES__`
        WHERE table_id IN ({placeholders})
        """
        params = [
            bigquery.ScalarQueryParameter(f"t{i}", "STRING", name)
            for i, name in enumerate(staging_tables_all)
        ]
        job = client.query(
            sql_storage, job_config=bigquery.QueryJobConfig(query_parameters=params)
        )
        for row in job:
            storage_bytes = int(row["total"]) if row["total"] is not None else 0

    storage_gb = storage_bytes / (1024**3)
    # Prorate by storage-days vs 30-day month
    prorate_factor = max(a.storage_days, 0) / 30.0
    est_storage_cost = storage_gb * a.storage_price_per_gb_month * prorate_factor

    print("Day,BytesProcessed")
    for d, b in day_bytes:
        print(f"{d},{b}")
    print()
    print(f"Total bytes processed: {total_bytes:,}")
    print(f"Total TB processed: {total_tb:.4f}")
    print(f"Estimated cost (@ ${a.price_per_tb:.2f}/TB): ${est_cost:.2f}")
    print()
    print("Storage estimation (approximate, from staging logical bytes)")
    print(f"Staging logical bytes (sum): {storage_bytes:,}")
    print(f"Staging logical GB: {storage_gb:.4f}")
    print(
        f"Estimated storage cost (@ ${a.storage_price_per_gb_month:.4f}/GB-month, days={a.storage_days}): ${est_storage_cost:.2f}"
    )


if __name__ == "__main__":
    main()
