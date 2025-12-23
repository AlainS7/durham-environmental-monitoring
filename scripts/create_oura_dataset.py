#!/usr/bin/env python3
"""
Ensure BigQuery dataset for Oura exists.

Usage:
  .venv/bin/python scripts/create_oura_dataset.py --dataset oura --location US --project <PROJECT>
If --project is omitted, Application Default Credentials will determine it.
"""

from __future__ import annotations
import argparse
import os
from google.cloud import bigquery


def main():
    p = argparse.ArgumentParser(description="Create BigQuery dataset if missing")
    p.add_argument("--dataset", default=os.getenv("OURA_DATASET", "oura"))
    p.add_argument("--location", default=os.getenv("BQ_LOCATION", "US"))
    p.add_argument("--project", default=os.getenv("BQ_PROJECT"))
    args = p.parse_args()

    client = bigquery.Client(project=args.project, location=args.location)
    ds_id = f"{client.project}.{args.dataset}"

    try:
        client.get_dataset(ds_id)
        print(f"✅ Dataset exists: {ds_id}")
        return 0
    except Exception:
        pass

    ds = bigquery.Dataset(ds_id)
    ds.location = args.location
    client.create_dataset(ds, exists_ok=True)
    print(f"✅ Created dataset: {ds_id} (location={args.location})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
