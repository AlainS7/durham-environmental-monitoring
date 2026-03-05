#!/usr/bin/env python3
"""Backfill sensor transformation tables for a date range.

Runs the three core SQL transformation scripts in order for each date:
  01_sensor_readings_long.sql   – unified long-format readings
  02_hourly_summary.sql         – hourly aggregates
  03_daily_summary.sql          – daily aggregates

All three scripts are idempotent (DELETE+INSERT per partition), so re-running
a date that already has data is safe.

Usage examples:

  # Execute the full history in 30-day chunks (default — safe to interrupt)
  python3 scripts/backfill_transformations.py --execute

  # Dry-run: see what would run without touching BigQuery
  python3 scripts/backfill_transformations.py --dry-run

  # Resume from a specific date (e.g. after interruption)
  python3 scripts/backfill_transformations.py --start 2025-10-01 --execute

  # Smaller chunks (e.g. 7 days) for a slow connection
  python3 scripts/backfill_transformations.py --chunk-days 7 --execute

  # Explicit date range
  python3 scripts/backfill_transformations.py --start 2025-07-04 --end 2025-12-31 --execute

  # Override project / dataset (defaults from env vars / hardcoded fallback)
  python3 scripts/backfill_transformations.py --project my-proj --dataset sensors --execute
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List, Tuple

# Only import bigquery when actually executing so dry-runs work without creds.
try:
    from google.cloud import bigquery  # type: ignore
except ImportError:
    bigquery = None  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PROJECT = (
    os.getenv("GCP_PROJECT_ID") or os.getenv("BQ_PROJECT") or "durham-weather-466502"
)
DEFAULT_DATASET = os.getenv("BQ_DATASET") or "sensors"
SQL_DIR = Path(__file__).parent.parent / "transformations" / "sql"

# Earliest date for which raw materialized data exists (confirmed via BQ query
# 2026-03-02): wu_raw_materialized starts 2025-07-04, tsi starts 2025-07-07.
# Using the earlier of the two so WU data isn't silently skipped.
DATA_START_DATE = "2025-07-04"

# Default chunk size: process N days per batch. Completed chunks are fully
# committed to BigQuery before the next chunk starts, so interrupting between
# chunks loses no work. Re-run with --start <printed resume date> to continue.
DEFAULT_CHUNK_DAYS = 30

# The three scripts that must run in order.  Patterns are prefixes so they
# remain correct even if filenames gain suffixes later.
PIPELINE_SCRIPTS = [
    "01_sensor_readings_long.sql",
    "02_hourly_summary.sql",
    "03_daily_summary.sql",
]

TOKEN_PATTERN = re.compile(r"\$\{(PROJECT|DATASET)\}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def render(sql: str, project: str, dataset: str) -> str:
    """Replace ${PROJECT} and ${DATASET} tokens in SQL text."""

    def repl(match: re.Match) -> str:
        return project if match.group(1) == "PROJECT" else dataset

    return TOKEN_PATTERN.sub(repl, sql)


def resolve_scripts(sql_dir: Path, names: List[str]) -> List[Path]:
    """Return absolute paths for each named script; raise if any is missing."""
    paths = []
    for name in names:
        p = sql_dir / name
        if not p.exists():
            raise FileNotFoundError(f"Required SQL script not found: {p}")
        paths.append(p)
    return paths


def date_range(start: date, end: date) -> List[date]:
    """Return inclusive list of dates from start to end."""
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def execute_sql(
    client: "bigquery.Client",
    sql: str,
    process_date: str,
) -> None:
    """Run a rendered SQL string against BigQuery with @proc_date parameter."""
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("proc_date", "DATE", process_date)
        ],
        use_legacy_sql=False,
    )
    job = client.query(sql, job_config=job_config)
    job.result()  # blocks until done; raises on failure


# ---------------------------------------------------------------------------
# Core backfill loop
# ---------------------------------------------------------------------------


def run_backfill(
    project: str,
    dataset: str,
    dates: List[date],
    script_paths: List[Path],
    execute: bool,
) -> Tuple[List[date], List[Tuple[date, str, Exception]]]:
    """
    For each date, run each script in order.

    Returns:
        successes  – list of dates that completed all scripts
        failures   – list of (date, script_name, exception) tuples
    """
    client = bigquery.Client(project=project) if execute else None
    successes: List[date] = []
    failures: List[Tuple[date, str, Exception]] = []

    total = len(dates)
    for i, d in enumerate(dates, 1):
        date_str = d.isoformat()
        print(f"\n[{i}/{total}] Processing {date_str} ...")
        day_ok = True

        for script_path in script_paths:
            raw = script_path.read_text()
            sql = render(raw, project, dataset)
            script_name = script_path.name

            if not execute:
                # Dry-run: print rendered SQL (abbreviated) and continue.
                preview = sql[:400].replace("\n", " ").strip()
                print(f"  [DRY-RUN] {script_name}: {preview}...")
                continue

            try:
                execute_sql(client, sql, date_str)
                print(f"  ✓ {script_name}")
            except Exception as exc:
                print(f"  ✗ {script_name}: {exc}", file=sys.stderr)
                failures.append((d, script_name, exc))
                day_ok = False
                # Abort remaining scripts for this day — later scripts depend
                # on earlier ones completing successfully.
                break

        if execute and day_ok:
            successes.append(d)

    return successes, failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--project",
        default=DEFAULT_PROJECT,
        help=f"GCP project ID (default: {DEFAULT_PROJECT})",
    )
    ap.add_argument(
        "--dataset",
        default=DEFAULT_DATASET,
        help=f"BigQuery dataset (default: {DEFAULT_DATASET})",
    )

    # Date range — mutually exclusive pairs
    range_group = ap.add_argument_group("date range (pick one approach)")
    range_group.add_argument(
        "--days",
        type=int,
        default=None,
        metavar="N",
        help="Backfill the last N days ending yesterday. Omit to use the full history since DATA_START_DATE.",
    )
    range_group.add_argument(
        "--start",
        metavar="YYYY-MM-DD",
        help="Explicit start date (inclusive); overrides --days",
    )
    range_group.add_argument(
        "--end",
        metavar="YYYY-MM-DD",
        help="Explicit end date (inclusive); defaults to yesterday when --start is used",
    )

    ap.add_argument(
        "--chunk-days",
        type=int,
        default=DEFAULT_CHUNK_DAYS,
        metavar="N",
        help=f"Process this many days per chunk (default: {DEFAULT_CHUNK_DAYS}). "
        "Each chunk is fully committed before the next starts — safe to interrupt between chunks.",
    )
    ap.add_argument(
        "--sql-dir",
        default=str(SQL_DIR),
        metavar="DIR",
        help=f"Directory containing SQL scripts (default: {SQL_DIR})",
    )
    ap.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute queries (default is dry-run / print only)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicitly request dry-run mode (same as omitting --execute)",
    )
    return ap.parse_args()


def resolve_date_range(args: argparse.Namespace) -> Tuple[date, date]:
    yesterday = date.today() - timedelta(days=1)

    if args.start:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else yesterday
    elif args.days is not None:
        end = date.fromisoformat(args.end) if args.end else yesterday
        start = end - timedelta(days=args.days - 1)
    else:
        # Default: everything from the first day raw data exists through yesterday.
        start = date.fromisoformat(DATA_START_DATE)
        end = date.fromisoformat(args.end) if args.end else yesterday

    if start > end:
        raise ValueError(f"Start date {start} is after end date {end}")

    return start, end


def chunk_dates(dates: List[date], chunk_size: int) -> List[List[date]]:
    """Split a list of dates into consecutive chunks of at most chunk_size."""
    return [dates[i : i + chunk_size] for i in range(0, len(dates), chunk_size)]


def main() -> None:
    args = parse_args()

    execute = args.execute and not args.dry_run
    sql_dir = Path(args.sql_dir)

    # Resolve scripts early so we fail fast if any are missing.
    try:
        script_paths = resolve_scripts(sql_dir, PIPELINE_SCRIPTS)
    except FileNotFoundError as exc:
        sys.exit(str(exc))

    try:
        start, end = resolve_date_range(args)
    except ValueError as exc:
        sys.exit(str(exc))

    all_dates = date_range(start, end)
    chunks = chunk_dates(all_dates, args.chunk_days)
    total_days = len(all_dates)
    total_chunks = len(chunks)

    print("=" * 60)
    print("  Backfill: sensor transformation tables")
    print(f"  Project : {args.project}")
    print(f"  Dataset : {args.dataset}")
    print(f"  Range   : {start} → {end} ({total_days} days)")
    print(f"  Chunks  : {total_chunks} × up to {args.chunk_days} days each")
    print(f"  Scripts : {', '.join(p.name for p in script_paths)}")
    print(f"  Mode    : {'EXECUTE' if execute else 'DRY-RUN'}")
    print("=" * 60)

    if execute and bigquery is None:
        sys.exit(
            "google-cloud-bigquery is not installed. "
            "Run: pip install google-cloud-bigquery"
        )

    all_successes: List[date] = []
    all_failures: List[Tuple[date, str, Exception]] = []

    for chunk_num, chunk in enumerate(chunks, 1):
        chunk_start = chunk[0]
        chunk_end = chunk[-1]
        print(f"\n{'─' * 60}")
        print(
            f"  CHUNK {chunk_num}/{total_chunks}  {chunk_start} → {chunk_end} ({len(chunk)} days)"
        )
        print(f"{'─' * 60}")

        successes, failures = run_backfill(
            project=args.project,
            dataset=args.dataset,
            dates=chunk,
            script_paths=script_paths,
            execute=execute,
        )
        all_successes.extend(successes)
        all_failures.extend(failures)

        # Per-chunk summary with resume instructions.
        print(f"\n  Chunk {chunk_num}/{total_chunks} done.", end="")
        if execute:
            chunk_failed = [f for f in failures]
            if chunk_failed:
                first_failure = min(d for d, _, _ in chunk_failed)
                print(
                    f" {len(successes)}/{len(chunk)} days OK, {len(chunk_failed)} failed."
                )
                print(
                    f"  ⚠  To retry failed days: --start {first_failure} --end {chunk_end}"
                )
            else:
                print(f" {len(successes)}/{len(chunk)} days OK. ✓")

            # Always print resume point so the user knows where to pick up
            # if they close the terminal before the next chunk starts.
            if chunk_num < total_chunks:
                next_start = chunks[chunk_num][0]  # first date of next chunk
                print(f"  💾 Data committed through {chunk_end}.")
                print("     Resume command if interrupted:")
                print(
                    f"     python3 scripts/backfill_transformations.py --start {next_start} --execute"
                )
        else:
            print()  # newline

    # Final summary
    print("\n" + "=" * 60)
    if execute:
        print(
            f"  TOTAL: {len(all_successes)}/{total_days} days succeeded across {total_chunks} chunks."
        )
        if all_failures:
            print(f"\n  All failed dates ({len(all_failures)}):")
            for d, script, exc in all_failures:
                print(f"    {d}  [{script}]  {str(exc)[:80]}")
            earliest_failure = min(d for d, _, _ in all_failures)
            print("\n  To retry all failures:")
            print(
                f"  python3 scripts/backfill_transformations.py --start {earliest_failure} --execute"
            )
    else:
        print(
            f"  Dry-run complete. {total_days} days across {total_chunks} chunks would be processed."
        )
        print("  Add --execute to run for real.")
    print("=" * 60)

    if all_failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
