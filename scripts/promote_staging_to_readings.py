#!/usr/bin/env python3
"""Promote per-day TSI staging tables into sensor_readings_long / hourly / daily.

Usage (dry run – prints row counts only):
    python3 scripts/promote_staging_to_readings.py --start 2026-02-21 --end 2026-02-27

Usage (execute):
    python3 scripts/promote_staging_to_readings.py --start 2026-02-21 --end 2026-02-27 --execute

The staging tables written by the daily_data_collector with --sink db have the schema:
    (timestamp STRING, deployment_fk INT64, metric_name STRING, value FLOAT64)

This script resolves deployment_fk → native_sensor_id via:
    deployments.deployment_pk → deployments.sensor_fk → sensors_master.sensor_pk

Then inserts into sensor_readings_long with the canonical row_id:
    FARM_FINGERPRINT(CONCAT(CAST(timestamp AS STRING), native_sensor_id, metric_name))

After populating sensor_readings_long, this script runs the hourly/daily aggregation
SQL files (02_hourly_summary.sql, 03_daily_summary.sql) for each date so that
sensor_readings_hourly and sensor_readings_daily are also populated.

This is the correct path for filling raw-data gaps where tsi_raw_materialized is
empty but staging tables were successfully written.
"""

import argparse
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL for promoting staging → sensor_readings_long
# ---------------------------------------------------------------------------
PROMOTE_LONG_SQL = """
-- Delete any existing rows for this date first (idempotent)
DELETE FROM `{project}.{dataset}.sensor_readings_long`
WHERE DATE(timestamp) = DATE('{proc_date}');

-- Insert from staging table.
-- deployment_fk in staging = FARM_FINGERPRINT(native_sensor_id) from sensor_id_map.
-- Join back via that hash to recover the native_sensor_id.
INSERT INTO `{project}.{dataset}.sensor_readings_long`
    (timestamp, timestamp_date, native_sensor_id, metric_name, value, source, row_id)
SELECT
    TIMESTAMP(s.timestamp)                                                         AS timestamp,
    DATE(TIMESTAMP(s.timestamp))                                                   AS timestamp_date,
    sim.native_sensor_id                                                           AS native_sensor_id,
    s.metric_name                                                                  AS metric_name,
    s.value                                                                        AS value,
    'tsi'                                                                          AS source,
    FARM_FINGERPRINT(
        CONCAT(
            CAST(TIMESTAMP(s.timestamp) AS STRING),
            sim.native_sensor_id,
            s.metric_name
        )
    )                                                                              AS row_id
FROM `{project}.{dataset}.{staging_table}` s
JOIN `{project}.{dataset}.sensor_id_map` sim
    ON FARM_FINGERPRINT(sim.native_sensor_id) = s.deployment_fk
WHERE s.timestamp IS NOT NULL
  -- TSI sensors: sensor_id starts with AA- or BS- (not MS- which is WU)
  AND NOT STARTS_WITH(sim.sensor_id, 'MS-');
"""

COUNT_SQL = """
SELECT COUNT(*) AS row_count
FROM `{project}.{dataset}.sensor_readings_long`
WHERE DATE(timestamp) = DATE('{proc_date}')
  AND source = 'tsi'
"""

STAGING_COUNT_SQL = """
SELECT COUNT(*) AS row_count FROM `{project}.{dataset}.{staging_table}`
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def date_range(start: date, end: date) -> List[date]:
    days = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


def staging_table_name(d: date) -> str:
    return f"staging_tsi_{d.strftime('%Y%m%d')}"


def table_exists(client, project: str, dataset: str, table: str) -> bool:
    from google.cloud import bigquery  # noqa: F401

    try:
        client.get_table(f"{project}.{dataset}.{table}")
        return True
    except Exception:
        return False


def execute_query(client, sql: str, proc_date: str):
    """Run a DELETE+INSERT SQL statement with @proc_date parameter."""
    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("proc_date", "DATE", proc_date)
        ],
        use_legacy_sql=False,
    )
    job = client.query(sql, job_config=job_config)
    job.result()  # blocks; raises on failure


def get_count(client, sql: str) -> int:
    rows = list(client.query(sql).result())
    return rows[0].row_count if rows else 0


def run_hourly_daily(
    client, sql_dir: Path, project: str, dataset: str, proc_date: str, dry_run: bool
):
    """Run 02_hourly_summary.sql and 03_daily_summary.sql for this date."""
    import re

    TOKEN_PATTERN = re.compile(r"\$\{(PROJECT|DATASET)\}")

    def render(sql: str) -> str:
        def repl(m):
            return project if m.group(1) == "PROJECT" else dataset

        return TOKEN_PATTERN.sub(repl, sql)

    for script_name in ("02_hourly_summary.sql", "03_daily_summary.sql"):
        script_path = sql_dir / script_name
        if not script_path.exists():
            log.warning("Aggregation script not found, skipping: %s", script_path)
            continue
        if dry_run:
            log.info("[DRY RUN] Would run %s for %s", script_name, proc_date)
            continue
        sql = render(script_path.read_text())
        log.info("Running %s for %s ...", script_name, proc_date)
        execute_query(client, sql, proc_date)
        log.info("  %s done for %s", script_name, proc_date)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args():
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--start", required=True, help="Start date YYYY-MM-DD (inclusive)")
    p.add_argument("--end", required=True, help="End date YYYY-MM-DD (inclusive)")
    p.add_argument(
        "--execute",
        action="store_true",
        help="Actually write to BigQuery (default: dry run)",
    )
    p.add_argument(
        "--project",
        default=os.getenv("BQ_PROJECT") or os.getenv("PROJECT_ID"),
        help="GCP project ID (default: BQ_PROJECT or PROJECT_ID env var)",
    )
    p.add_argument(
        "--dataset",
        default=os.getenv("BQ_DATASET", "sensors"),
        help="BigQuery dataset (default: sensors)",
    )
    return p.parse_args()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    args = parse_args()

    project = args.project
    if not project:
        log.error(
            "No GCP project ID provided. Set BQ_PROJECT env var or pass --project"
        )
        sys.exit(1)

    dataset = args.dataset
    dry_run = not args.execute

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)
    days = date_range(start, end)

    sql_dir = Path(__file__).parent.parent / "transformations" / "sql"

    if dry_run:
        log.info("=== DRY RUN (pass --execute to write) ===")

    log.info(
        "Project=%s  Dataset=%s  Dates=%s → %s  (%d days)",
        project,
        dataset,
        start,
        end,
        len(days),
    )

    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=project)
    except Exception as e:
        log.error("Failed to initialise BigQuery client: %s", e)
        sys.exit(1)

    total_inserted = 0
    skipped = 0

    for d in days:
        proc_date = d.isoformat()
        tbl = staging_table_name(d)

        # Check staging table exists
        if not table_exists(client, project, dataset, tbl):
            log.warning(
                "[SKIP] Staging table missing for %s: %s.%s.%s",
                proc_date,
                project,
                dataset,
                tbl,
            )
            skipped += 1
            continue

        # Row count in staging
        staging_count = get_count(
            client,
            STAGING_COUNT_SQL.format(
                project=project, dataset=dataset, staging_table=tbl
            ),
        )
        log.info("Staging table %s has %d rows", tbl, staging_count)

        if staging_count == 0:
            log.warning("[SKIP] Staging table is empty for %s", proc_date)
            skipped += 1
            continue

        if dry_run:
            log.info(
                "[DRY RUN] Would promote %d staging rows → sensor_readings_long for %s",
                staging_count,
                proc_date,
            )
            log.info("[DRY RUN] Would run hourly/daily aggregation for %s", proc_date)
            continue

        # Execute promotion
        promote_sql = PROMOTE_LONG_SQL.format(
            project=project,
            dataset=dataset,
            staging_table=tbl,
            proc_date=proc_date,
        )
        log.info("Promoting staging → sensor_readings_long for %s ...", proc_date)
        execute_query(client, promote_sql, proc_date)

        # Verify
        inserted = get_count(
            client,
            COUNT_SQL.format(project=project, dataset=dataset, proc_date=proc_date),
        )
        log.info(
            "  Inserted %d rows into sensor_readings_long for %s", inserted, proc_date
        )
        total_inserted += inserted

        # Run hourly + daily aggregations
        run_hourly_daily(client, sql_dir, project, dataset, proc_date, dry_run=False)

    if dry_run:
        log.info("=== DRY RUN complete. Re-run with --execute to apply. ===")
    else:
        log.info(
            "=== Promotion complete: %d total rows inserted, %d dates skipped ===",
            total_inserted,
            skipped,
        )
        log.info("Next step: run the main backfill for the non-gap date ranges:")
        log.info(
            "  python3 scripts/backfill_transformations.py --execute --start 2025-07-04 --end 2026-02-20"
        )
        log.info(
            "  python3 scripts/backfill_transformations.py --execute --start 2026-02-28"
        )


if __name__ == "__main__":
    main()
