#!/usr/bin/env python3
"""\n+Bulk Oura → BigQuery uploader for ALL residents and full available history.\n+\n+Strategy:\n+  * Iterates over configured residents (env files pat_rX.env must exist)\n+  * Uses a rolling monthly window from a chosen start date until today\n+  * Performs REAL BigQuery uploads (dry_run disabled) appending rows\n+  * Skips months with no data (prints summary)\n+  * Resilient: continues on resident errors; logs failures\n+  * Cost tracking enabled per batch\n+\n+Usage examples:\n+  .venv/bin/python scripts/upload_oura_all_residents.py --start 2025-01-01 --residents 1 2 3\n+  .venv/bin/python scripts/upload_oura_all_residents.py --start 2024-01-01 --all-residents\n+\n+Safety first:\n+  * Requires explicit --confirm flag to run (to avoid accidental large uploads)\n+  * Can enable --dry-run to inspect counts before real run\n+\n+Environment:\n+  * BQ_PROJECT (optional, else ADC)\n+  * BQ_LOCATION (default US)\n+\n+Tables written (prefix 'oura'):\n+  oura_daily_sleep, oura_daily_activity, oura_daily_readiness,\n+  oura_daily_spo2, oura_daily_stress, oura_daily_cardiovascular_age\n+\n+Exit codes:\n+  0 success, 1 if any resident had fatal error, 2 if confirm flag missing.\n+"""

from __future__ import annotations
import argparse
from datetime import date, datetime, timedelta
from pathlib import Path
import os
import sys
import logging

sys.path.insert(0, str(Path(__file__).parent.parent / "oura-rings"))

from oura_client import OuraClient  # type: ignore
from oura_bigquery_loader import build_daily_frames, upload_frames_to_bigquery  # type: ignore
from oura_import_options import DATA_TYPES  # type: ignore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("oura_bulk_upload")


ESSENTIAL_KEYS = [
    ("sleep", "get_daily_sleep"),
    ("activity", "get_daily_activity"),
    ("readiness", "get_daily_readiness"),
    ("daily_spo2", "get_daily_spo2"),
    ("daily_stress", "get_daily_stress"),
    ("daily_cardiovascular_age", "get_daily_cardiovascular_age"),
    # Newly added types
    ("sleep_periods", "get_sleep_periods"),
    ("sessions", "get_sessions"),
    ("workouts", "get_workouts"),
    ("heart_rate", "get_heart_rate"),
]


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


def month_windows(start: date, end: date):
    """Yield (month_start, month_end) date tuples inclusive."""
    cur = date(start.year, start.month, 1)
    while cur <= end:
        if cur.month == 12:
            nxt = date(cur.year + 1, 1, 1)
        else:
            nxt = date(cur.year, cur.month + 1, 1)
        window_end = min(nxt - timedelta(days=1), end)
        yield (cur, window_end)
        cur = nxt


def collect_month(token: str, resident: int, start_d: date, end_d: date) -> dict:
    params = {"start_date": str(start_d), "end_date": str(end_d)}
    data: dict = {}
    with OuraClient(token) as client:  # type: ignore
        for key, method_name in ESSENTIAL_KEYS:
            if not DATA_TYPES.get(
                key if key.startswith("daily_") else f"daily_{key}", True
            ):
                continue
            fn = getattr(client, method_name)
            try:
                data[key] = fn(**params)
            except Exception as e:
                log.warning(
                    "Resident %s %s month %s-%s error: %s",
                    resident,
                    key,
                    start_d,
                    end_d,
                    e,
                )
    return data


def upload_resident(
    resident: int,
    start: date,
    end: date,
    *,
    dataset: str,
    prefix: str,
    project: str | None,
    location: str,
    dry_run: bool,
) -> dict:
    token = load_token(resident)
    if not token:
        log.error("Resident %s missing PAT env file", resident)
        return {"resident": resident, "status": "missing_token"}

    total_rows = 0
    table_row_counts: dict[str, int] = {}
    months = list(month_windows(start, end))
    for m_start, m_end in months:
        log.info("Resident %s collecting %s → %s", resident, m_start, m_end)
        data = collect_month(token, resident, m_start, m_end)
        frames = build_daily_frames(data, resident_no=resident)
        # Optional filtering to only newly added tables
        if os.getenv("ONLY_NEW_TYPES") == "1":
            keep = {"sleep_periods", "sessions", "workouts", "daily_heart_rate"}
            frames = {k: v for k, v in frames.items() if k in keep}
        if not frames:
            log.info(
                "Resident %s no data for %s-%s – skipping", resident, m_start, m_end
            )
            continue
        result = upload_frames_to_bigquery(
            frames,
            dataset=dataset,
            table_prefix=prefix,
            project=project,
            location=location,
            dry_run=dry_run,
            track_costs=True,
        )
        for tbl, rows in result["tables"].items():
            table_row_counts[tbl] = table_row_counts.get(tbl, 0) + rows
            total_rows += rows
        log.info(
            "Resident %s month %s uploaded tables=%s",
            resident,
            m_start.strftime("%Y-%m"),
            list(result["tables"].keys()),
        )

    return {
        "resident": resident,
        "status": "ok",
        "total_rows": total_rows,
        "tables": table_row_counts,
    }


def parse_args():
    ap = argparse.ArgumentParser(description="Bulk upload Oura data to BigQuery")
    ap.add_argument(
        "--start", required=True, help="Start date YYYY-MM-DD (first month)"
    )
    ap.add_argument("--end", help="End date YYYY-MM-DD (default today)")
    ap.add_argument(
        "--residents", type=int, nargs="+", help="Explicit resident numbers"
    )
    ap.add_argument(
        "--all-residents", action="store_true", help="Attempt residents 1-20"
    )
    ap.add_argument("--dataset", default="oura")
    ap.add_argument("--table-prefix", default="oura")
    ap.add_argument("--project", default=os.getenv("BQ_PROJECT"))
    ap.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    ap.add_argument(
        "--dry-run", action="store_true", help="Do not write, only estimate"
    )
    ap.add_argument(
        "--only-new-types",
        action="store_true",
        help=(
            "Upload only newly added tables: sleep_periods, sessions, workouts, daily_heart_rate"
        ),
    )
    ap.add_argument(
        "--confirm",
        action="store_true",
        help="Required to perform (even dry-run) bulk operation",
    )
    return ap.parse_args()


def main():
    args = parse_args()
    if not args.confirm:
        print("⚠️  Missing --confirm; aborting for safety.")
        return 2
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else date.today()
    if end < start:
        print("❌ End before start")
        return 1

    if args.all_residents:
        residents = list(range(1, 21))
    else:
        residents = args.residents or []
    if not residents:
        print("❌ No residents specified")
        return 1

    log.info(
        "Bulk upload start=%s end=%s residents=%s dry_run=%s",
        start,
        end,
        residents,
        args.dry_run,
    )
    failures = 0
    summaries = []
    for r in residents:
        res = upload_resident(
            r,
            start,
            end,
            dataset=args.dataset,
            prefix=args.table_prefix,
            project=args.project,
            location=args.location,
            dry_run=args.dry_run,
        )
        # If only-new-types requested, filter the result tables display
        if args.only_new_types and res.get("tables"):
            new_keys = {
                f"{args.table_prefix}_sleep_periods",
                f"{args.table_prefix}_sessions",
                f"{args.table_prefix}_workouts",
                f"{args.table_prefix}_daily_heart_rate",
            }
            res["tables"] = {k: v for k, v in res["tables"].items() if k in new_keys}
        summaries.append(res)
        if res.get("status") != "ok":
            failures += 1

    print("\n===== BULK UPLOAD SUMMARY =====")
    for s in summaries:
        print(
            f"Resident {s['resident']:>2}: {s['status']:<12} rows={s.get('total_rows', 0):>5}"
        )
        if s.get("tables"):
            for tbl, rows in sorted(s["tables"].items()):
                print(f"   - {tbl:35s} {rows:>5} rows")

    print("Failures:", failures)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
