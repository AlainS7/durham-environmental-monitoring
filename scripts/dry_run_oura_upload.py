#!/usr/bin/env python3
"""
Collect Oura data for a resident and perform a BigQuery dry-run upload to estimate rows and cost.

This script:
  - Loads PAT from local `oura-rings/pats/pat_r1.env` by default (no secrets in repo)
  - Collects last 7 days of data for selected types
  - Builds DataFrames
  - Calls BigQuery loader in dry-run mode with cost tracking

Usage:
  .venv/bin/python scripts/dry_run_oura_upload.py --resident 1 --days 7 --dataset oura --project <PROJECT>
"""

from __future__ import annotations
import argparse
import os
from datetime import date, timedelta
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "oura-rings"))

from oura_client import OuraClient  # type: ignore
from oura_bigquery_loader import build_daily_frames, upload_frames_to_bigquery  # type: ignore


def load_token_from_pats(resident: int = 1) -> str | None:
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


essential_types = [
    ("sleep", "get_daily_sleep"),
    ("activity", "get_daily_activity"),
    ("readiness", "get_daily_readiness"),
    ("daily_spo2", "get_daily_spo2"),
    ("daily_stress", "get_daily_stress"),
    ("daily_cardiovascular_age", "get_daily_cardiovascular_age"),
    # Newly added collections
    ("sleep_periods", "get_sleep_periods"),
    ("sessions", "get_sessions"),
    ("workouts", "get_workouts"),
    ("heart_rate", "get_heart_rate"),  # aggregated to daily_heart_rate in builder
]


def main():
    ap = argparse.ArgumentParser(description="Dry-run Oura → BigQuery upload")
    ap.add_argument("--resident", type=int, default=1)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--dataset", default="oura")
    ap.add_argument("--table-prefix", default="oura")
    ap.add_argument("--project", default=os.getenv("BQ_PROJECT"))
    ap.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    args = ap.parse_args()

    token = load_token_from_pats(args.resident)
    if not token:
        print(
            "❌ No Oura PAT found in oura-rings/pats; please add pat_r{args.resident}.env"
        )
        return 1

    end_d = date.today()
    start_d = end_d - timedelta(days=args.days)
    params = {"start_date": str(start_d), "end_date": str(end_d)}

    print(
        f"Collecting resident {args.resident} data for {params['start_date']} → {params['end_date']}"
    )

    data: dict = {}
    with OuraClient(token) as client:  # type: ignore
        for key, method_name in essential_types:
            fn = getattr(client, method_name)
            try:
                data[key] = fn(**params)
                print(f"  ✓ {key:28s} {len(data[key]) if data[key] else 0:>4} records")
            except Exception as e:
                print(f"  ⚠️  {key}: {e}")

    frames = build_daily_frames(data, resident_no=args.resident)

    print("\nEstimating BigQuery upload (DRY-RUN)...")
    result = upload_frames_to_bigquery(
        frames,
        dataset=args.dataset,
        table_prefix=args.table_prefix,
        project=args.project,
        location=args.location,
        dry_run=True,
        track_costs=True,
    )

    tables = result["tables"]
    costs = result["cost_metrics"]

    print("\nTables and row counts:")
    for tbl, rows in tables.items():
        est_bytes = costs["tables"].get(tbl, {}).get("estimated_bytes", 0)
        print(f"  - {tbl:35s} {rows:>5} rows | ~{est_bytes / 1e6:>7.2f} MB")

    print(
        "\nTotal estimated bytes: ~{:.2f} MB".format(
            costs["total_bytes_processed"] / 1e6
        )
    )
    print(
        "Estimated query cost (pricing $5/TB): ${:.6f}".format(
            costs["estimated_cost_usd"]
        )
    )
    print(
        "\nNote: Uploads themselves are free; this estimates query costs for validation/reads."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
