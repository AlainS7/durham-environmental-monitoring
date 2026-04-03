#!/usr/bin/env python3
"""Deprecated BigQuery direct loader.

Use external->materialize flow instead:
1. scripts/create_bq_external_tables.py
2. scripts/materialize_partitions.py
3. scripts/run_transformations.py
"""

from __future__ import annotations

import argparse
import logging

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
log = logging.getLogger("load_to_bigquery")


def build_gcs_uri(bucket: str, prefix: str, source: str, agg: str, date: str) -> str:
    return f"gs://{bucket}/{prefix}/source={source}/agg={agg}/dt={date}/*.parquet"


def main():
    parser = argparse.ArgumentParser(
        description="DEPRECATED: direct BigQuery load path. Use external->materialize flow instead."
    )
    parser.add_argument("--dataset", required=False)
    parser.add_argument("--project", required=False)
    parser.add_argument("--location", required=False)
    parser.add_argument("--bucket", required=False)
    parser.add_argument("--prefix", required=False)
    parser.add_argument("--date", required=False)
    parser.add_argument("--source", required=False)
    parser.add_argument("--agg", required=False)
    parser.add_argument("--table-prefix", required=False)
    parser.add_argument("--partition-field", required=False)
    parser.add_argument("--cluster-by", required=False)
    parser.add_argument("--write", required=False)
    parser.add_argument("--create", required=False)
    parser.add_argument("--replace-date", action="store_true")
    parser.parse_args()

    raise SystemExit(
        "scripts/load_to_bigquery.py is deprecated and intentionally disabled. "
        "Use: create-external -> materialize -> run-transformations."
    )


if __name__ == "__main__":
    main()
