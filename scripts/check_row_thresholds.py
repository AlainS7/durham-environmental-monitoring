#!/usr/bin/env python3
"""Check per-table row count thresholds for a given date partition.
Fails (exit 1) if any table is below its configured minimum.

Config is inline (could be externalized): dict of table -> min rows.

Usage:
  python scripts/check_row_thresholds.py --project p --dataset sensors --date 2025-08-26
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import yaml  # type: ignore
from google.cloud import bigquery

DEFAULT_THRESHOLDS = {
    'wu_raw_materialized': 100,   # adjust after observing production volumes
    'tsi_raw_materialized': 100,
    'sensor_readings_long': 100,
}


def load_thresholds(config_path: str | None = None, thresholds_json: str | None = None) -> dict[str, int]:
    """Load row thresholds merging defaults, optional YAML config, and JSON override.

    Precedence: defaults < YAML row_thresholds < JSON override.
    The YAML file is only read if present and PyYAML available.
    """
    thresholds: dict[str, int] = DEFAULT_THRESHOLDS.copy()
    cfg_path = None
    if config_path:
        p = Path(config_path)
        if p.exists():
            cfg_path = p
    else:
        default = Path('config/data_quality.yaml')
        if default.exists():
            cfg_path = default
    if cfg_path:
        try:
            with open(cfg_path) as f:
                data = yaml.safe_load(f) or {}
            rt = data.get('row_thresholds') or {}
            thresholds.update({k:int(v) for k,v in rt.items()})
        except Exception as e:  # pragma: no cover
            print(f"Warning: failed to load config {cfg_path}: {e}")
    if thresholds_json:
        try:
            thresholds.update(json.loads(Path(thresholds_json).read_text()))
        except Exception as e:  # pragma: no cover
            print(f"Warning: failed to load JSON override {thresholds_json}: {e}")
    return thresholds

def count_partition(client: bigquery.Client, project: str, dataset: str, table: str, date: str) -> int:
    fq = f"{project}.{dataset}.{table}"
    date_column = {
        "wu_raw_materialized": "ts",
        "tsi_raw_materialized": "ts",
        "sensor_readings_long": "timestamp",
        "sensor_readings_hourly": "hour_ts",
        "sensor_readings_daily": "day_ts",
    }.get(table)
    q = (
        f"SELECT COUNT(*) c FROM `{fq}` WHERE DATE({date_column})=@d"
        if date_column
        else f"SELECT COUNT(*) c FROM `{fq}`"
    )
    cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter('d','DATE',date)])
    return list(client.query(q, job_config=cfg).result())[0]['c']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', required=True)
    ap.add_argument('--dataset', required=True)
    ap.add_argument('--date', required=True)
    ap.add_argument('--thresholds-json', help='Optional JSON mapping table->min_rows (deprecated in favor of --config)')
    ap.add_argument('--config', help='YAML config file with row_thresholds section (default config/data_quality.yaml if exists)')
    args = ap.parse_args()

    thresholds = load_thresholds(args.config, args.thresholds_json)

    client = bigquery.Client(project=args.project)
    failures = []
    results = {}
    for table, minimum in thresholds.items():
        try:
            cnt = count_partition(client, args.project, args.dataset, table, args.date)
            results[table] = {'count': cnt, 'min_required': minimum}
            if cnt < minimum:
                failures.append(table)
        except Exception as e:
            results[table] = {'error': str(e)}
            failures.append(table)
    print(json.dumps({'date': args.date, 'results': results}, indent=2))
    if failures:
        raise SystemExit(f"Threshold check failed: {failures}")

if __name__ == '__main__':
    main()
