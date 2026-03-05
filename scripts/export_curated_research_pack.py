#!/usr/bin/env python3
"""Export curated BigQuery research-pack summaries to CSV artifacts."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

from google.cloud import bigquery

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("export-curated-research-pack")

DATASET_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")

DAILY_SOURCE_COLUMNS = [
    "source",
    "row_count",
    "distinct_sensors",
    "min_timestamp",
    "max_timestamp",
]

HOURLY_SUMMARY_COLUMNS = [
    "hour_ts",
    "source",
    "pm25_avg",
    "temperature_avg",
    "humidity_avg",
    "pm25_samples",
    "temperature_samples",
    "humidity_samples",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export curated research-pack summaries from BigQuery."
    )
    parser.add_argument("--project", required=True, help="GCP project ID")
    parser.add_argument("--dataset", required=True, help="BigQuery dataset ID")
    parser.add_argument("--date", required=True, help="Date partition in YYYY-MM-DD")
    parser.add_argument("--output-dir", required=True, help="Base output directory")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> tuple[dt.date, Path]:
    project = args.project.strip()
    if not project:
        raise ValueError("--project cannot be empty")
    if "`" in project:
        raise ValueError("--project contains invalid character: `")

    dataset = args.dataset.strip()
    if not DATASET_RE.fullmatch(dataset):
        raise ValueError("--dataset must be a valid BigQuery dataset identifier")

    try:
        export_date = dt.date.fromisoformat(args.date)
    except ValueError as exc:
        raise ValueError("--date must be in YYYY-MM-DD format") from exc

    output_dir = Path(args.output_dir).expanduser().resolve()
    return export_date, output_dir


def run_query(client: bigquery.Client, sql: str, export_date: dt.date) -> list[dict[str, Any]]:
    config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("proc_date", "DATE", export_date.isoformat())
        ]
    )
    job = client.query(sql, job_config=config)
    rows = []
    for row in job.result():
        rows.append({key: row.get(key) for key in row.keys()})
    return rows


def serialize_value(value: Any) -> Any:
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    return value


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: serialize_value(row.get(key)) for key in fieldnames})
    log.info("Wrote %s (%d rows)", path, len(rows))


def daily_source_sql(project: str, dataset: str) -> str:
    return f"""
    SELECT
      source,
      COUNT(*) AS row_count,
      COUNT(DISTINCT native_sensor_id) AS distinct_sensors,
      MIN(timestamp) AS min_timestamp,
      MAX(timestamp) AS max_timestamp
    FROM `{project}.{dataset}.sensor_readings_long`
    WHERE DATE(timestamp) = @proc_date
    GROUP BY source
    ORDER BY source
    """


def hourly_summary_sql(project: str, dataset: str) -> str:
    return f"""
    WITH hourly AS (
      SELECT
        hour_ts,
        source,
        CASE
          WHEN LOWER(metric_name) IN ('pm2_5', 'pm2.5', 'pm25') THEN 'pm25'
          WHEN LOWER(metric_name) IN ('temperature', 'temp') THEN 'temperature'
          WHEN LOWER(metric_name) IN ('humidity', 'rh', 'relative_humidity') THEN 'humidity'
          ELSE NULL
        END AS metric_group,
        avg_value,
        samples
      FROM `{project}.{dataset}.sensor_readings_hourly`
      WHERE DATE(hour_ts) = @proc_date
    )
    SELECT
      hour_ts,
      source,
      ROUND(AVG(IF(metric_group = 'pm25', avg_value, NULL)), 3) AS pm25_avg,
      ROUND(AVG(IF(metric_group = 'temperature', avg_value, NULL)), 3) AS temperature_avg,
      ROUND(AVG(IF(metric_group = 'humidity', avg_value, NULL)), 3) AS humidity_avg,
      SUM(IF(metric_group = 'pm25', samples, 0)) AS pm25_samples,
      SUM(IF(metric_group = 'temperature', samples, 0)) AS temperature_samples,
      SUM(IF(metric_group = 'humidity', samples, 0)) AS humidity_samples
    FROM hourly
    WHERE metric_group IS NOT NULL
    GROUP BY hour_ts, source
    ORDER BY hour_ts, source
    """


def write_metadata(
    path: Path,
    project: str,
    dataset: str,
    export_date: dt.date,
    daily_path: Path,
    daily_rows: int,
    hourly_path: Path,
    hourly_rows: int,
) -> None:
    payload = {
        "project": project,
        "dataset": dataset,
        "date": export_date.isoformat(),
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "artifacts": [
            {
                "name": "daily_source_summary",
                "path": str(daily_path),
                "row_count": daily_rows,
                "columns": DAILY_SOURCE_COLUMNS,
            },
            {
                "name": "hourly_pm25_temp_humidity_summary",
                "path": str(hourly_path),
                "row_count": hourly_rows,
                "columns": HOURLY_SUMMARY_COLUMNS,
            },
        ],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    log.info("Wrote %s", path)


def main() -> int:
    args = parse_args()
    try:
        export_date, output_dir = validate_args(args)
        export_dir = output_dir / export_date.isoformat()
        export_dir.mkdir(parents=True, exist_ok=True)

        log.info(
            "Starting curated export for %s.%s on %s",
            args.project,
            args.dataset,
            export_date.isoformat(),
        )
        client = bigquery.Client(project=args.project)

        daily_rows = run_query(client, daily_source_sql(args.project, args.dataset), export_date)
        hourly_rows = run_query(
            client,
            hourly_summary_sql(args.project, args.dataset),
            export_date,
        )

        daily_csv = export_dir / "daily_source_summary.csv"
        hourly_csv = export_dir / "hourly_pm25_temp_humidity_summary.csv"
        metadata_json = export_dir / "metadata.json"

        write_csv(daily_csv, DAILY_SOURCE_COLUMNS, daily_rows)
        write_csv(hourly_csv, HOURLY_SUMMARY_COLUMNS, hourly_rows)
        write_metadata(
            metadata_json,
            args.project,
            args.dataset,
            export_date,
            daily_csv,
            len(daily_rows),
            hourly_csv,
            len(hourly_rows),
        )

        log.info("Curated export completed successfully")
        return 0
    except Exception:
        log.exception("Curated export failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
