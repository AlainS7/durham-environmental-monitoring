# -*- coding: utf-8 -*-
"""
Oura Data Pipeline CLI
Command-line interface for batch processing Oura Ring data.

Usage:
    python -m oura_rings.cli                           # Process all configured residents
    python -m oura_rings.cli --residents 1 2 3         # Process specific residents
    python -m oura_rings.cli --start 2025-10-01 --end 2025-10-30  # Custom date range
    python -m oura_rings.cli --export-bq --no-dry-run  # Enable BigQuery export
"""

import sys
import argparse
import logging
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from oura_collector import process_resident, create_summary_report
from oura_import_options import (
    RESIDENTS_TO_PROCESS,
    DATE_CONFIG,
    PATHS,
    OPTIONS,
    DATA_TYPES,
    OURA_BQ,
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("batch_processing.log"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def main(args=None):
    """Main function to process residents."""
    parser = argparse.ArgumentParser(
        description="Batch process Oura Ring data for multiple residents"
    )
    parser.add_argument(
        "--residents",
        type=int,
        nargs="+",
        help="Specific resident numbers to process (default: from config)",
    )
    parser.add_argument(
        "--start", type=str, help="Start date YYYY-MM-DD (default: from config)"
    )
    parser.add_argument(
        "--end", type=str, help="End date YYYY-MM-DD (default: from config)"
    )
    parser.add_argument(
        "--export-bq",
        action="store_true",
        help="Enable BigQuery export (overrides config)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Perform real BigQuery upload (default: dry-run)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        help="Override output directory (default: from config)",
    )

    parsed = parser.parse_args(args)

    # Use config or override from CLI
    residents = parsed.residents if parsed.residents else RESIDENTS_TO_PROCESS
    date_params = {
        "start_date": parsed.start if parsed.start else DATE_CONFIG["start_date"],
        "end_date": parsed.end if parsed.end else DATE_CONFIG["end_date"],
    }
    output_base = (
        Path(parsed.output_dir) if parsed.output_dir else Path(PATHS["output_base_dir"])
    )

    # Override BQ options if specified
    options = OPTIONS.copy()
    if parsed.export_bq:
        options["export_to_bigquery"] = True
    if parsed.no_dry_run:
        options["bq_dry_run"] = False

    logger.info("=" * 60)
    logger.info("STARTING BATCH OURA RING DATA PROCESSING")
    logger.info("=" * 60)
    logger.info(f"Residents to process: {residents}")
    logger.info(f"Date range: {date_params['start_date']} to {date_params['end_date']}")
    logger.info(f"Data types: {[k for k, v in DATA_TYPES.items() if v]}")
    if options.get("export_to_bigquery"):
        logger.info(
            f"BigQuery export: ENABLED (dry_run={options.get('bq_dry_run', True)})"
        )

    # Setup output directory
    output_base.mkdir(parents=True, exist_ok=True)

    # Process all residents
    results = []
    for resident_no in residents:
        result = process_resident(
            resident_no,
            date_params,
            output_base,
            PATHS,
            options,
            DATA_TYPES,
            OURA_BQ,
        )
        results.append(result)

        # Continue on error if configured
        if result["status"] == "error" and not options.get("continue_on_error"):
            logger.error("Stopping processing due to error and continue_on_error=False")
            break

    # Create summary
    create_summary_report(
        results,
        output_base,
        date_params,
        {"residents": residents, "data_types": DATA_TYPES, "options": options},
    )

    # Final summary
    successful = sum(1 for r in results if r["status"] == "success")
    failed = len(results) - successful

    logger.info("=" * 60)
    logger.info("BATCH PROCESSING COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Total processed: {len(results)}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")

    if failed > 0:
        logger.info("\nFailed residents:")
        for result in results:
            if result["status"] == "error":
                logger.info(f"  - Resident {result['resident']}: {result['message']}")

    return results


if __name__ == "__main__":
    results = main()
    sys.exit(0 if all(r["status"] == "success" for r in results) else 1)
