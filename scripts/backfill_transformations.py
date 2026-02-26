#!/usr/bin/env python3
"""Backfill sensor_readings_long (and downstream tables) for a date range.

Works on macOS and Linux. Calls run_transformations.py for each date.

Usage:
  python scripts/backfill_transformations.py --start 2025-07-04 --end 2026-02-04

  # Dry-run (prints commands without executing):
  python scripts/backfill_transformations.py --start 2025-07-04 --end 2026-02-04 --dry-run

  # Only run transformation step 01 (sensor_readings_long):
  python scripts/backfill_transformations.py --start 2025-07-04 --end 2026-02-04 --steps 01
"""

import argparse
import subprocess
import sys
from datetime import date, timedelta, datetime

PROJECT = "durham-weather-466502"
DATASET = "sensors"
SQL_DIR = "transformations/sql"


def daterange(start: date, end: date):
    """Yield dates from start to end inclusive."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def main():
    parser = argparse.ArgumentParser(description="Backfill transformations")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--project", default=PROJECT)
    parser.add_argument("--dataset", default=DATASET)
    parser.add_argument("--dir", default=SQL_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--steps", help="Comma-separated step prefixes to run (e.g., '01,02,03')"
    )
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)
    total_days = (end_date - start_date).days + 1

    print(f"{'=' * 60}")
    print(f"Backfill Transformations")
    print(f"  Range: {start_date} → {end_date} ({total_days} days)")
    print(f"  Project: {args.project}")
    print(f"  Dataset: {args.dataset}")
    if args.steps:
        print(f"  Steps: {args.steps}")
    if args.dry_run:
        print(f"  Mode: DRY RUN")
    print(f"{'=' * 60}\n")

    success = 0
    errors = []

    for i, d in enumerate(daterange(start_date, end_date), 1):
        ds = d.isoformat()
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] ({i}/{total_days}) Processing {ds}...", end=" ", flush=True)

        cmd = [
            sys.executable,
            "scripts/run_transformations.py",
            "--project",
            args.project,
            "--dataset",
            args.dataset,
            "--dir",
            args.dir,
            "--date",
            ds,
            "--execute",
        ]

        if args.dry_run:
            print(f"WOULD RUN: {' '.join(cmd)}")
            success += 1
            continue

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                print(f"❌ ERROR")
                errors.append((ds, result.stderr[:200]))
                print(f"    {result.stderr[:200]}")
            else:
                print(f"✅")
                success += 1
        except subprocess.TimeoutExpired:
            print(f"⏰ TIMEOUT")
            errors.append((ds, "Timeout after 300s"))
        except Exception as e:
            print(f"💥 {e}")
            errors.append((ds, str(e)))

    print(f"\n{'=' * 60}")
    print(f"BACKFILL COMPLETE")
    print(f"  Success: {success}/{total_days}")
    print(f"  Errors:  {len(errors)}/{total_days}")
    if errors:
        print(f"\nFailed dates:")
        for ds, err in errors:
            print(f"  {ds}: {err}")
    print(f"{'=' * 60}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
