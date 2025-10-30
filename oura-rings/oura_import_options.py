# -*- coding: utf-8 -*-
"""
9-29-25 dw/ vs code
Optional configuration file for Oura Ring importing & saving
Modify these settings to change date or resident #'s when using code ""oura_import_save.py".

(Based on processing for 1 resident, scaled to all originally from Oura_test_R3.py)

"""

import datetime

# Residents to process (modify this list as needed)
# Example: RESIDENTS_TO_PROCESS = [1, 2, 3]  # Process specific residents
# Example: RESIDENTS_TO_PROCESS = list(range(1, 10))  # Process residents 1-9
RESIDENTS_TO_PROCESS = []  # Empty by default - configure before running

# Date range for data collection
DATE_CONFIG = {
    "start_date": "2025-01-01",  # Format: YYYY-MM-DD
    "end_date": str(
        datetime.date.today()
    ),  # Use 'today' - so is recent to when code is run
}

# File paths configuration
PATHS = {
    "env_files_dir": "../../../../Secure Files",  # Directory containing pat_r*.env files (kept OUT of repo)
    "output_base_dir": "../../../Oura Ring",  # Base directory for local outputs (kept OUT of repo)
    "json_subdir": "DataDictionaries",  # Main subdirectory for JSON files
    "combined_subdir": "combined data",  # Subfolder for combined dictionaries
    "separate_subdir": "separate dictionaries",  # Subfolder for separate dictionaries
    "csv_subdir": "DailyValues",  # Subdirectory for CSV files
}

# Processing options
OPTIONS = {
    "continue_on_error": True,  # Continue processing other residents if one fails
    "save_individual_jsons": True,  # Save separate JSON for each data type
    "save_combined_json": True,  # Save all data types in one JSON per resident
    "save_daily_csv": True,  # Save daily summary CSV
    "create_summary_report": True,  # Create batch processing summary
    # BigQuery export settings (safe defaults)
    "export_to_bigquery": False,  # If True, will attempt to export daily data to BigQuery
    "bq_dry_run": True,  # When True, validates upload path without network calls
}

# Data types to collect (set to False to skip)
DATA_TYPES = {
    "daily_sleep": True,
    "sleep_periods": True,
    "daily_activity": True,
    "daily_readiness": True,
    "heart_rate": True,
    "sessions": True,
    "workouts": True,
}

# BigQuery configuration for Oura exports
# Uses existing repo conventions: BQ_PROJECT, BQ_LOCATION. Dataset can be customized here.
OURA_BQ = {
    "project_env": "BQ_PROJECT",  # Use env var BQ_PROJECT if present; else ADC default
    "dataset": "oura",  # Default dataset for Oura data
    "location": "US",  # BigQuery location
    "table_prefix": "oura",  # Tables will be like oura_daily_sleep, etc.
}
