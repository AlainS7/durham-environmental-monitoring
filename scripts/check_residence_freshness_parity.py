#!/usr/bin/env python3
"""Check freshness parity between production and shared residence daily views."""

from __future__ import annotations

import argparse
from datetime import date

from google.cloud import bigquery


def _read_max_day(
    client: bigquery.Client,
    project: str,
    dataset: str,
    table: str,
) -> date | None:
    query = f"""
    SELECT MAX(DATE(day_ts)) AS max_day
    FROM `{project}.{dataset}.{table}`
    """
    row = next(iter(client.query(query).result()), None)
    if row is None:
        return None
    return row["max_day"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare MAX(day_ts) between sensors.residence_readings_daily and "
            "sensors_shared.residence_readings_daily."
        )
    )
    parser.add_argument("--project", required=True, help="BigQuery project ID")
    parser.add_argument("--prod-dataset", default="sensors", help="Production dataset")
    parser.add_argument(
        "--shared-dataset",
        default="sensors_shared",
        help="Shared/Grafana dataset",
    )
    parser.add_argument("--table", default="residence_readings_daily")
    parser.add_argument(
        "--max-lag-days",
        type=int,
        default=0,
        help="Maximum allowed lag (prod max day - shared max day)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = bigquery.Client(project=args.project)

    prod_max = _read_max_day(client, args.project, args.prod_dataset, args.table)
    shared_max = _read_max_day(client, args.project, args.shared_dataset, args.table)

    print(f"prod_max_day={prod_max}")
    print(f"shared_max_day={shared_max}")

    if prod_max is None or shared_max is None:
        raise SystemExit("Unable to compute freshness parity: one side has no data.")

    lag_days = (prod_max - shared_max).days
    print(f"lag_days={lag_days}")

    if lag_days < 0:
        raise SystemExit(
            f"Shared dataset appears ahead of production by {-lag_days} day(s), investigate sync flow."
        )

    if lag_days > args.max_lag_days:
        raise SystemExit(
            f"Freshness parity failed: shared lags production by {lag_days} day(s) "
            f"(max allowed={args.max_lag_days})."
        )

    print("Freshness parity check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

