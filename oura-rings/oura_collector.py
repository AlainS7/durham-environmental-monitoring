# -*- coding: utf-8 -*-
"""
Oura Data Collector
Core logic for fetching and saving Oura data for multiple residents.
"""

from __future__ import annotations

import json
import os
import datetime
import logging
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

from oura_client import OuraClient
from oura_transforms import dict_to_df, combine_daily_dataframes


logger = logging.getLogger(__name__)


def get_resident_token(resident_no: int, env_files_dir: str) -> str | None:
    """Get the access token for a specific resident."""
    env_file_at = Path(env_files_dir) / f"pat_r{resident_no}.env"

    if not env_file_at.exists():
        logger.warning(
            f"Environment file not found for resident {resident_no}: {env_file_at}"
        )
        return None

    load_dotenv(dotenv_path=env_file_at, override=True)
    token = os.getenv("PERSONAL_ACCESS_TOKEN")

    if not token:
        logger.warning(f"No access token found for resident {resident_no}")
        return None

    return token


def collect_oura_data(
    client: OuraClient, params: dict, data_types: dict
) -> dict[str, Any]:
    """Collect all specified Oura data types."""
    data = {}

    if data_types.get("daily_sleep"):
        logger.info("  - Fetching daily sleep data...")
        data["sleep"] = client.get_daily_sleep(**params)

    if data_types.get("sleep_periods"):
        logger.info("  - Fetching sleep periods data...")
        data["sleep_periods"] = client.get_sleep_periods(**params)

    if data_types.get("daily_activity"):
        logger.info("  - Fetching daily activity data...")
        data["activity"] = client.get_daily_activity(**params)

    if data_types.get("daily_readiness"):
        logger.info("  - Fetching daily readiness data...")
        data["readiness"] = client.get_daily_readiness(**params)

    if data_types.get("heart_rate"):
        logger.info("  - Fetching heart rate data...")
        data["heart_rate"] = client.get_heart_rate(**params)

    if data_types.get("sessions"):
        logger.info("  - Fetching sessions data...")
        data["sessions"] = client.get_sessions(**params)

    if data_types.get("workouts"):
        logger.info("  - Fetching workouts data...")
        data["workouts"] = client.get_workouts(**params)

    return data


def save_data(
    resident_no: int, data: dict, output_base: Path, paths: dict, options: dict
) -> dict:
    """Save imported data as JSON and CSV files."""
    results = {"json_files": [], "csv_files": []}

    # Create main directories
    json_base_dir = output_base / paths["json_subdir"]
    csv_dir = output_base / paths["csv_subdir"]

    # Create subdirectories for different JSON types
    separate_dir = json_base_dir / paths["separate_subdir"]
    combined_dir = json_base_dir / paths["combined_subdir"]

    # Ensure all directories exist
    separate_dir.mkdir(parents=True, exist_ok=True)
    combined_dir.mkdir(parents=True, exist_ok=True)
    csv_dir.mkdir(parents=True, exist_ok=True)

    # Save individual JSON files
    if options.get("save_individual_jsons"):
        for data_type, data_content in data.items():
            if data_content:
                json_file = separate_dir / f"R{resident_no}_{data_type}_data.json"
                with open(json_file, "w") as f:
                    json.dump(data_content, f, indent=2)
                results["json_files"].append(str(json_file))

    # Save combined JSON file
    if options.get("save_combined_json"):
        json_file = combined_dir / f"R{resident_no}_all_data.json"
        with open(json_file, "w") as f:
            json.dump(data, f, indent=2)
        results["json_files"].append(str(json_file))

    # Create and save daily CSV
    if options.get("save_daily_csv"):
        df_daily = combine_daily_dataframes(
            data.get("sleep"), data.get("activity"), data.get("readiness")
        )
        if not df_daily.empty:
            csv_file = csv_dir / f"R{resident_no}_daily_oura_values.csv"
            df_daily.to_csv(csv_file, index=False)
            results["csv_files"].append(str(csv_file))
            results["daily_records"] = len(df_daily)

    return results


def process_resident(
    resident_no: int,
    params: dict,
    output_base: Path,
    paths: dict,
    options: dict,
    data_types: dict,
    oura_bq: dict,
) -> dict:
    """Process Oura data for a single resident."""
    logger.info(f"Processing resident {resident_no}...")

    try:
        # Get access token
        token = get_resident_token(resident_no, paths["env_files_dir"])
        if not token:
            return {
                "resident": resident_no,
                "status": "error",
                "message": "No access token available",
            }

        # Collect data
        with OuraClient(token) as client:
            data = collect_oura_data(client, params, data_types)

        # Save data locally
        save_results = save_data(resident_no, data, output_base, paths, options)

        # Optionally export to BigQuery
        bq_results = None
        if options.get("export_to_bigquery"):
            try:
                from oura_bigquery_loader import export_daily_to_bigquery

                bq_results = export_daily_to_bigquery(
                    resident_no,
                    data,
                    dataset=oura_bq.get("dataset", "oura"),
                    table_prefix=oura_bq.get("table_prefix", "oura"),
                    project=os.getenv(oura_bq.get("project_env", "BQ_PROJECT")) or None,
                    location=oura_bq.get("location", os.getenv("BQ_LOCATION", "US")),
                    dry_run=bool(options.get("bq_dry_run", True)),
                )
                logger.info(
                    f"BigQuery export (dry_run={options.get('bq_dry_run', True)}): {bq_results}"
                )
            except Exception as be:
                logger.error(f"BigQuery export failed for resident {resident_no}: {be}")

        logger.info(f"✅ Successfully processed resident {resident_no}")
        return {
            "resident": resident_no,
            "status": "success",
            "data_types": list(data.keys()),
            "daily_records": save_results.get("daily_records", 0),
            "files_created": len(save_results["json_files"])
            + len(save_results["csv_files"]),
            **save_results,
            "bq_export": bq_results,
        }

    except Exception as e:
        logger.error(f"❌ Error processing resident {resident_no}: {e}", exc_info=True)
        return {"resident": resident_no, "status": "error", "message": str(e)}


def create_summary_report(results: list, output_base: Path, params: dict, config: dict):
    """Create a comprehensive summary report."""
    if not config["options"].get("create_summary_report"):
        return

    summary = {
        "processing_timestamp": datetime.datetime.now().isoformat(),
        "date_range": params,
        "configuration": {
            "residents_requested": config["residents"],
            "data_types_enabled": {k: v for k, v in config["data_types"].items() if v},
            "options": config["options"],
        },
        "summary_stats": {
            "total_residents": len(config["residents"]),
            "successful": sum(1 for r in results if r["status"] == "success"),
            "failed": sum(1 for r in results if r["status"] == "error"),
            "total_files_created": sum(
                r.get("files_created", 0) for r in results if r["status"] == "success"
            ),
            "total_daily_records": sum(
                r.get("daily_records", 0) for r in results if r["status"] == "success"
            ),
        },
        "detailed_results": results,
    }

    # Save detailed summary
    summary_file = output_base / "batch_processing_summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    # Create simple status file
    status_file = output_base / "processing_status.txt"
    with open(status_file, "w") as f:
        f.write("Oura Ring Batch Processing Status\n")
        f.write(f"Generated: {datetime.datetime.now()}\n\n")
        f.write(f"Total residents: {summary['summary_stats']['total_residents']}\n")
        f.write(f"Successful: {summary['summary_stats']['successful']}\n")
        f.write(f"Failed: {summary['summary_stats']['failed']}\n")
        f.write(f"Files created: {summary['summary_stats']['total_files_created']}\n")
        f.write(f"Daily records: {summary['summary_stats']['total_daily_records']}\n\n")

        f.write("Individual Results:\n")
        for result in results:
            status_icon = "✅" if result["status"] == "success" else "❌"
            if result["status"] == "success":
                f.write(
                    f"{status_icon} Resident {result['resident']}: {result['daily_records']} daily records\n"
                )
            else:
                f.write(
                    f"{status_icon} Resident {result['resident']}: {result['message']}\n"
                )

    logger.info(f"Summary saved to: {summary_file}")
    logger.info(f"Status file saved to: {status_file}")
