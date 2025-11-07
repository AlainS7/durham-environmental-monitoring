#!/usr/bin/env python3
"""Detect earliest available Oura data per resident by probing backwards month-by-month.

Strategy:
  * For each resident, start at a recent anchor (today) and step backwards in months.
  * For each month window, request a minimal lightweight endpoint (daily_sleep).
  * Record the earliest day found; then optionally refine within that month.
  * Stop scanning after N consecutive empty months (safety cutoff) or reaching a configured minimum date.

Outputs:
  * Prints a summary table resident -> earliest_date (or None)
  * Optionally writes JSON: --out-file oura_earliest_dates.json

Usage:
  .venv/bin/python scripts/detect_oura_earliest_dates.py --residents 1 2 3 --min-date 2024-01-01 --out-file earliest.json
  .venv/bin/python scripts/detect_oura_earliest_dates.py --all-residents --min-date 2024-01-01

Notes:
  * Requires pat_rX.env files under oura-rings/pats with PERSONAL_ACCESS_TOKEN entries.
  * Uses only daily_sleep to reduce API load; earliest date typically aligns across daily endpoints.
"""

from __future__ import annotations
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "oura-rings"))
from oura_client import OuraClient  # type: ignore


def load_token(resident: int) -> str | None:
    pats_dir = Path(__file__).parent.parent / "oura-rings" / "pats"
    pat_file = pats_dir / f"pat_r{resident}.env"
    if not pat_file.exists():
        return None
    with open(pat_file, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("PERSONAL_ACCESS_TOKEN="):
                return line.split("=", 1)[1]
    return None


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def prev_month_start(d: date) -> date:
    if d.month == 1:
        return date(d.year - 1, 12, 1)
    return date(d.year, d.month - 1, 1)


def end_of_month(start: date) -> date:
    if start.month == 12:
        return date(start.year, 12, 31)
    nxt = date(start.year, start.month + 1, 1)
    return nxt - timedelta(days=1)


def probe_month(client: OuraClient, start: date, end: date) -> list[dict]:  # type: ignore
    return client.get_daily_sleep(start_date=str(start), end_date=str(end))  # type: ignore


def detect_earliest_for_resident(
    resident: int, min_date: date, cutoff_empty: int = 6
) -> date | None:
    token = load_token(resident)
    if not token:
        print(f"Resident {resident:>2}: Missing PAT – skipping")
        return None
    today = date.today()
    current = month_start(today)
    consecutive_empty = 0
    earliest: date | None = None
    with OuraClient(token) as client:  # type: ignore
        while current >= min_date:
            m_end = end_of_month(current)
            data = probe_month(client, current, m_end)
            if data:
                # refine to earliest day inside month
                days = sorted(
                    [
                        datetime.strptime(d["day"], "%Y-%m-%d").date()
                        for d in data
                        if d.get("day")
                    ]
                )
                if days:
                    earliest = days[0]
                break
            else:
                consecutive_empty += 1
                if consecutive_empty >= cutoff_empty:
                    break
            current = prev_month_start(current)
    return earliest


def parse_args():
    ap = argparse.ArgumentParser(description="Detect earliest Oura data per resident")
    ap.add_argument(
        "--residents", type=int, nargs="+", help="Explicit resident numbers"
    )
    ap.add_argument("--all-residents", action="store_true")
    ap.add_argument(
        "--min-date", default="2024-01-01", help="Earliest date to search back to"
    )
    ap.add_argument("--out-file", help="Optional JSON output file")
    return ap.parse_args()


def main():
    args = parse_args()
    min_date = datetime.strptime(args.min_date, "%Y-%m-%d").date()
    residents = args.residents or ([] if not args.all_residents else list(range(1, 21)))
    if not residents:
        print("No residents specified.")
        return 1
    results = {}
    print("Scanning earliest Oura data (daily_sleep) ...")
    for r in residents:
        earliest = detect_earliest_for_resident(r, min_date)
        results[r] = earliest.isoformat() if earliest else None
        status = earliest if earliest else "NO DATA FOUND"
        print(f"Resident {r:>2}: {status}")
    if args.out_file:
        with open(args.out_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Written JSON: {args.out_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
