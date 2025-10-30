# -*- coding: utf-8 -*-
"""
Oura -> BigQuery export helpers

Safe-by-default utilities to transform Oura daily data to pandas DataFrames and
optionally upload them to BigQuery. Network upload is disabled unless explicitly enabled.

Environment conventions:
- BQ_PROJECT (optional): the target GCP project; if unset, Application Default Credentials will determine the project
- BQ_LOCATION (optional): defaults to 'US'

Tables created (by default with prefix 'oura'):
- oura_daily_sleep
- oura_daily_activity
- oura_daily_readiness

Usage pattern:
  from oura_bigquery_loader import build_daily_frames, upload_frames_to_bigquery
  frames = build_daily_frames(data_dict_from_api, resident_no=3)
  upload_frames_to_bigquery(frames, dataset='oura', table_prefix='oura', dry_run=True)

"""

from __future__ import annotations
from typing import Dict, Any
import os
import pandas as pd
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

# Reuse the small flattener from batch module at runtime import to avoid circular import


def _dict_to_df(data, label: str, score_label: str = "score") -> pd.DataFrame:
    """Local copy used if importing from batch fails."""
    records = []
    for entry in data:
        flat_entry = {
            "day": entry["day"],
            "source": label,
            score_label: entry.get("score", None),
        }
        flat_entry.update(entry.get("contributors", {}))
        records.append(flat_entry)
    df = pd.DataFrame(records)
    if not df.empty:
        df["day"] = pd.to_datetime(df["day"])
    return df


def build_daily_frames(
    data: Dict[str, Any], resident_no: int
) -> Dict[str, pd.DataFrame]:
    """
    Build per-type daily DataFrames for upload to BigQuery.

    Input contract:
    - data: dict possibly including keys 'sleep', 'activity', 'readiness' with lists of dicts from Oura API
    - resident_no: integer id to attribute rows to

    Output:
    - dict mapping table suffixes to DataFrames with columns [resident, day, ...]
    """
    # Attempt to import the flattener from batch file if present
    try:
        from .batch_oura_enhanced import dict_to_df as _shared_dict_to_df  # type: ignore

        to_df = _shared_dict_to_df
    except Exception:
        to_df = _dict_to_df

    frames: Dict[str, pd.DataFrame] = {}

    # Sleep
    if "sleep" in data and data["sleep"]:
        df = to_df(data["sleep"], "sleep", "sleep_score").drop(
            columns=["source"], errors="ignore"
        )
        df.insert(0, "resident", int(resident_no))
        frames["daily_sleep"] = df

    # Activity
    if "activity" in data and data["activity"]:
        df = to_df(data["activity"], "activity", "activity_score").drop(
            columns=["source"], errors="ignore"
        )
        df.insert(0, "resident", int(resident_no))
        frames["daily_activity"] = df

    # Readiness
    if "readiness" in data and data["readiness"]:
        df = to_df(data["readiness"], "readiness", "readiness_score").drop(
            columns=["source"], errors="ignore"
        )
        df.insert(0, "resident", int(resident_no))
        frames["daily_readiness"] = df

    return frames


def _ensure_dataset(client: bigquery.Client, dataset_id: str) -> None:
    try:
        client.get_dataset(dataset_id)
    except NotFound:
        ds = bigquery.Dataset(f"{client.project}.{dataset_id}")
        client.create_dataset(ds, exists_ok=True)


def upload_frames_to_bigquery(
    frames: Dict[str, pd.DataFrame],
    dataset: str,
    table_prefix: str = "oura",
    project: str | None = None,
    location: str | None = None,
    dry_run: bool = True,
) -> Dict[str, int]:
    """
    Upload each frame to BigQuery as table: {table_prefix}_{name}

    - frames: dict[str, DataFrame]
    - dataset: target dataset (created if missing)
    - project: optional project override (defaults to ADC project)
    - location: optional BQ location (defaults to env BQ_LOCATION or 'US')
    - dry_run: when True, does not perform network calls, returns row counts

    Returns a mapping of table_name -> rows uploaded (or would upload, for dry-run)
    """
    project = project or os.getenv("BQ_PROJECT") or None
    location = location or os.getenv("BQ_LOCATION", "US")

    results: Dict[str, int] = {}

    # Validate content
    for name, df in frames.items():
        if df.empty:
            continue
        if "resident" not in df.columns or "day" not in df.columns:
            raise ValueError(
                f"Frame '{name}' missing required columns 'resident' and 'day'"
            )

    if dry_run:
        for name, df in frames.items():
            results[f"{table_prefix}_{name}"] = int(len(df))
        return results

    client = bigquery.Client(project=project, location=location)
    _ensure_dataset(client, dataset)

    for name, df in frames.items():
        if df.empty:
            continue
        table_name = f"{table_prefix}_{name}"
        table_ref = client.dataset(dataset).table(table_name)
        job = client.load_table_from_dataframe(df, table_ref)
        job.result()
        results[table_name] = int(len(df))

    return results


def export_daily_to_bigquery(
    resident_no: int,
    data: Dict[str, Any],
    *,
    dataset: str,
    table_prefix: str = "oura",
    project: str | None = None,
    location: str | None = None,
    dry_run: bool = True,
) -> Dict[str, int]:
    """Convenience wrapper to build frames then upload them."""
    frames = build_daily_frames(data, resident_no)
    return upload_frames_to_bigquery(
        frames,
        dataset=dataset,
        table_prefix=table_prefix,
        project=project,
        location=location,
        dry_run=dry_run,
    )
