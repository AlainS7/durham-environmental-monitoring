#!/usr/bin/env python3
"""Upload Oura data for all residents from their earliest detected date to today.

Requires a mapping JSON (resident -> earliest_date) produced by
scripts/detect_oura_earliest_dates.py.

This orchestrates per-resident uploads using the existing uploader logic,
and prints a compact summary at the end.

Usage:
  .venv/bin/python scripts/upload_oura_from_earliest.py \
      --mapping oura_earliest_dates.json --dataset oura --project <PROJECT>

Options:
  --residents can limit to a subset; omit to include all from the JSON.
  --dry-run to estimate without writing.
  --confirm required as a safety guard.
"""

from __future__ import annotations
import argparse
import json
from datetime import date, datetime
from pathlib import Path
import os
import sys

# Make repository root importable
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.upload_oura_all_residents import upload_resident  # type: ignore  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Upload Oura from earliest per resident")
    ap.add_argument(
        "--mapping",
        default="oura_earliest_dates.json",
        help="Path to resident->earliest_date JSON",
    )
    ap.add_argument(
        "--residents", type=int, nargs="+", help="Limit to specific resident numbers"
    )
    ap.add_argument("--dataset", default="oura")
    ap.add_argument("--table-prefix", default="oura")
    ap.add_argument("--project", default=os.getenv("BQ_PROJECT"))
    ap.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args()

    if not args.confirm:
        print("⚠️  Missing --confirm; aborting for safety.")
        return 2

    mapping_path = Path(args.mapping)
    if not mapping_path.exists():
        print(f"❌ Mapping file not found: {mapping_path}")
        return 1

    with open(mapping_path, "r") as f:
        mapping = json.load(f)

    # Choose residents
    if args.residents:
        selected = {
            str(r): mapping.get(str(r)) or mapping.get(r) for r in args.residents
        }
    else:
        selected = mapping

    today = date.today()
    summaries = []
    failures = 0
    for key, earliest in sorted(selected.items(), key=lambda kv: int(kv[0])):
        try:
            r = int(key)
        except Exception:
            continue
        if not earliest:
            print(
                f"Resident {r:>2}: no earliest date (missing PAT or no data) – skipping"
            )
            continue
        try:
            start = datetime.strptime(earliest, "%Y-%m-%d").date()
        except Exception:
            print(f"Resident {r:>2}: invalid date '{earliest}' – skipping")
            continue

        print(
            f"\n==> Uploading resident {r} from {start} to {today} (dry_run={args.dry_run})"
        )
        res = upload_resident(
            r,
            start,
            today,
            dataset=args.dataset,
            prefix=args.table_prefix,
            project=args.project,
            location=args.location,
            dry_run=args.dry_run,
        )
        summaries.append(res)
        if res.get("status") != "ok":
            failures += 1

    print("\n===== FULL UPLOAD SUMMARY =====")
    for s in summaries:
        print(
            f"Resident {s['resident']:>2}: {s['status']:<12} rows={s.get('total_rows', 0):>5}"
        )
    print("Failures:", failures)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
