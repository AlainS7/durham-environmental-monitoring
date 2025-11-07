#!/usr/bin/env python3
"""Backfill a date range into the consolidated sensor_readings table.

Modes supported:
 1. Partitioned / single staging table (legacy) via --staging-table
 2. Multiple staging tables (union) via --staging-tables or --auto-detect-staging (prefix/suffix)
 3. Per-source dated tables pattern (--per-source-dated + --sources) naming: staging_<source>_YYYYMMDD

For modes 1 & 2, each MERGE filters DATE(timestamp)=@d.
For per-source dated tables, each table is assumed to only contain its date's rows (no filter); missing tables are skipped.

Example:
  python scripts/merge_backfill_range.py \
    --project $BQ_PROJECT --dataset sensors \
    --start 2025-08-21 --end 2025-08-28 --per-source-dated --sources tsi,wu

Environment fallbacks: BQ_PROJECT, BQ_LOCATION
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys
from typing import List

from google.cloud import bigquery
from google.cloud.exceptions import NotFound
from merge_sensor_readings import (  # type: ignore
    resolve_staging_tables,
    ensure_target_exists_from_reference,
    build_merge_sql,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("merge_backfill_range")


def parse_args():
    p = argparse.ArgumentParser(
        description="Backfill a date range with MERGE operations"
    )
    p.add_argument("--project", default=os.getenv("BQ_PROJECT"))
    p.add_argument("--dataset", required=True)
    p.add_argument("--start", required=True, help="Start date (YYYY-MM-DD) inclusive")
    p.add_argument("--end", required=True, help="End date (YYYY-MM-DD) inclusive")
    p.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    # Staging selection (shared with merge_sensor_readings.py style)
    p.add_argument(
        "--staging-table", default=None, help="Single partitioned staging table name"
    )
    p.add_argument(
        "--staging-tables",
        default=None,
        help="Explicit comma list of staging tables to UNION",
    )
    p.add_argument(
        "--auto-detect-staging",
        action="store_true",
        help="Auto-detect staging tables by prefix/suffix",
    )
    p.add_argument(
        "--staging-prefix", default="sensor_readings_", help="Prefix for auto-detect"
    )
    p.add_argument("--staging-suffix", default="_raw", help="Suffix for auto-detect")
    # Per-source dated tables mode
    p.add_argument(
        "--per-source-dated",
        action="store_true",
        help="Use per-source dated tables pattern staging_<src>_YYYYMMDD",
    )
    p.add_argument(
        "--sources",
        default="tsi,wu",
        help="Comma list of source ids for per-source dated mode",
    )
    p.add_argument("--target-table", default="sensor_readings")
    p.add_argument("--update-only-if-changed", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    # Validate mutually exclusive selection
    selections = sum(
        [
            1 if args.staging_table else 0,
            1 if args.staging_tables else 0,
            1 if args.auto_detect_staging else 0,
            1 if args.per_source_dated else 0,
        ]
    )
    if selections == 0:
        # Default to auto-detect for convenience
        args.auto_detect_staging = True
    elif selections > 1:
        raise SystemExit(
            "Specify only one staging selection mode among --staging-table, --staging-tables, --auto-detect-staging, --per-source-dated"
        )
    return args


def daterange(start: dt.date, end: dt.date):
    cur = start
    while cur <= end:
        yield cur
        cur += dt.timedelta(days=1)


def merge_per_source_dated(client: bigquery.Client, a, start: dt.date, end: dt.date):
    sources: List[str] = [s.strip() for s in a.sources.split(",") if s.strip()]
    if not sources:
        raise SystemExit("No sources provided for per-source dated mode")
    target_created = False
    predicate = "T.value != S.value" if a.update_only_if_changed else "TRUE"
    for day in daterange(start, end):
        ds = day.strftime("%Y%m%d")
        existing: List[str] = []
        for src in sources:
            t = f"staging_{src}_{ds}"
            try:
                client.get_table(f"{a.dataset}.{t}")
                existing.append(t)
            except NotFound:
                log.warning("Missing staging table %s - skipping for %s", t, ds)
        if not existing:
            log.warning("No staging tables present for %s; skipping day", ds)
            continue
        if not target_created:
            ensure_target_exists_from_reference(
                client, a.dataset, existing[0], a.target_table
            )
            target_created = True
        # Ensure timestamp type consistency: some staging loads may have inferred STRING timestamps
        # due to dataframe coercion before load. CAST handles both STRING->TIMESTAMP and TIMESTAMP->TIMESTAMP.
        selects = [
            f"SELECT CAST(timestamp AS TIMESTAMP) AS timestamp, deployment_fk, metric_name, value FROM `{client.project}.{a.dataset}.{t}`"
            for t in existing
        ]
        union = "\nUNION ALL\n".join(selects)
        sql = f"""
MERGE `{client.project}.{a.dataset}.{a.target_table}` T
USING (
  {union}
) S
ON T.timestamp = S.timestamp AND T.deployment_fk = S.deployment_fk AND T.metric_name = S.metric_name
WHEN MATCHED AND {predicate} THEN UPDATE SET value = S.value
WHEN NOT MATCHED THEN INSERT (timestamp, deployment_fk, metric_name, value) VALUES (S.timestamp, S.deployment_fk, S.metric_name, S.value)
""".strip()
        if a.dry_run:
            log.info("[DRY RUN] Would MERGE %s from %d tables", day, len(existing))
            continue
        log.info("Merging %s from %d tables...", day, len(existing))
        job = client.query(sql)
        job.result()
        log.info(
            "Merged %s (affected rows: %s)",
            day,
            getattr(job, "num_dml_affected_rows", "n/a"),
        )
    log.info("Per-source dated backfill complete %s -> %s", start, end)


def merge_partitioned_or_union(
    client: bigquery.Client, a, start: dt.date, end: dt.date
):
    # Build a lightweight args-like namespace for reuse with resolve_staging_tables
    from types import SimpleNamespace

    tmp = SimpleNamespace(
        staging_table=a.staging_table,
        staging_tables=a.staging_tables,
        auto_detect_staging=a.auto_detect_staging
        and not a.staging_tables
        and not a.staging_table,
        staging_prefix=a.staging_prefix,
        staging_suffix=a.staging_suffix,
        target_table=a.target_table,
    )
    staging_tables = resolve_staging_tables(client, a.dataset, tmp)  # type: ignore
    ensure_target_exists_from_reference(
        client, a.dataset, staging_tables[0], a.target_table
    )
    for day in daterange(start, end):
        date_str = day.isoformat()
        sql = build_merge_sql(
            client.project,
            a.dataset,
            staging_tables,
            a.target_table,
            a.update_only_if_changed,
        )
        cfg = bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("d", "DATE", date_str)]
        )
        if a.dry_run:
            log.info(
                "[DRY RUN] Would MERGE partition %s from %d staging table(s)",
                date_str,
                len(staging_tables),
            )
            continue
        log.info(
            "Merging date %s from %d staging table(s)...", date_str, len(staging_tables)
        )
        job = client.query(sql, job_config=cfg)
        job.result()
        log.info(
            "Date %s merged (affected: %s)",
            date_str,
            getattr(job, "num_dml_affected_rows", "n/a"),
        )
    log.info("Backfill complete %s -> %s", start, end)


def main():
    a = parse_args()
    try:
        start_date = dt.date.fromisoformat(a.start)
        end_date = dt.date.fromisoformat(a.end)
    except ValueError as e:  # pragma: no cover
        log.error("Invalid date: %s", e)
        sys.exit(1)
    if end_date < start_date:
        log.error("End date before start date")
        sys.exit(1)
    client = bigquery.Client(project=a.project, location=a.location)
    if a.per_source_dated:
        merge_per_source_dated(client, a, start_date, end_date)
    else:
        merge_partitioned_or_union(client, a, start_date, end_date)


if __name__ == "__main__":  # pragma: no cover
    main()
