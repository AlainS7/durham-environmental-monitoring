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
- oura_daily_spo2 (NEW: blood oxygen levels)
- oura_daily_stress (NEW: stress/recovery metrics)
- oura_daily_cardiovascular_age (NEW: vascular age estimates)
 - oura_sleep_periods (NEW: individual sleep periods per day)
 - oura_sessions (NEW: guided/breathing/meditation sessions with start/end)
 - oura_workouts (NEW: workout events with start/end)
 - oura_daily_heart_rate (NEW: daily summary of heart rate min/max/avg)

Usage pattern:
  from oura_bigquery_loader import build_daily_frames, upload_frames_to_bigquery
  frames = build_daily_frames(data_dict_from_api, resident_no=3)
  upload_frames_to_bigquery(frames, dataset='oura', table_prefix='oura', dry_run=True)

"""

from __future__ import annotations
from typing import Dict, Any
import os
import logging
import pandas as pd
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

logger = logging.getLogger(__name__)

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
    - data: dict possibly including keys:
      - 'sleep', 'activity', 'readiness' (original)
      - 'daily_spo2', 'daily_stress', 'daily_cardiovascular_age' (NEW)
      with lists of dicts from Oura API
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

    # NEW: SpO2 (blood oxygen)
    if "daily_spo2" in data and data["daily_spo2"]:
        records = []
        for entry in data["daily_spo2"]:
            flat = {
                "day": entry.get("day"),
                "id": entry.get("id"),
                "breathing_disturbance_index": entry.get("breathing_disturbance_index"),
            }
            # Extract nested spo2_percentage
            if "spo2_percentage" in entry and entry["spo2_percentage"]:
                flat["spo2_average"] = entry["spo2_percentage"].get("average")
            records.append(flat)

        df = pd.DataFrame(records)
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            df.insert(0, "resident", int(resident_no))
            frames["daily_spo2"] = df

    # NEW: Stress
    if "daily_stress" in data and data["daily_stress"]:
        df = pd.DataFrame(data["daily_stress"])
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            df.insert(0, "resident", int(resident_no))
            frames["daily_stress"] = df

    # NEW: Cardiovascular Age
    if "daily_cardiovascular_age" in data and data["daily_cardiovascular_age"]:
        df = pd.DataFrame(data["daily_cardiovascular_age"])
        if not df.empty:
            df["day"] = pd.to_datetime(df["day"])
            df.insert(0, "resident", int(resident_no))
            frames["daily_cardiovascular_age"] = df

    # NEW: Sleep Periods (event-level with start/end)
    if "sleep_periods" in data and data["sleep_periods"]:
        df = pd.DataFrame(data["sleep_periods"])  # keys vary by API; keep flexible
        if not df.empty:
            # Determine start timestamp column
            start_col = None
            for cand in ["start_datetime", "start_time", "start", "timestamp"]:
                if cand in df.columns:
                    start_col = cand
                    break
            if start_col is not None:
                df[start_col] = pd.to_datetime(df[start_col], errors="coerce")
                df["day"] = df[start_col].dt.normalize()
            elif "day" in df.columns:
                df["day"] = pd.to_datetime(df["day"], errors="coerce")
            else:
                # Fallback: cannot infer day; skip to avoid schema errors
                df = pd.DataFrame()
        if not df.empty:
            # Drop nested list/dict columns (BigQuery load rejects ragged arrays with nulls)
            nested_cols = [
                c
                for c in df.columns
                if not df[c].empty and isinstance(df[c].iloc[0], (list, dict))
            ]
            if nested_cols:
                df = df.drop(columns=nested_cols, errors="ignore")
            df.insert(0, "resident", int(resident_no))
            frames["sleep_periods"] = df

    # NEW: Sessions (event-level with start/end)
    if "sessions" in data and data["sessions"]:
        df = pd.DataFrame(
            data["sessions"]
        )  # includes type, start_datetime, end_datetime, etc.
        if not df.empty:
            start_col = None
            for cand in ["start_datetime", "start_time", "start", "timestamp"]:
                if cand in df.columns:
                    start_col = cand
                    break
            if start_col is not None:
                df[start_col] = pd.to_datetime(df[start_col], errors="coerce")
                df["day"] = df[start_col].dt.normalize()
            elif "day" in df.columns:
                df["day"] = pd.to_datetime(df["day"], errors="coerce")
            else:
                df = pd.DataFrame()
        if not df.empty:
            nested_cols = [
                c
                for c in df.columns
                if not df[c].empty and isinstance(df[c].iloc[0], (list, dict))
            ]
            if nested_cols:
                df = df.drop(columns=nested_cols, errors="ignore")
            df.insert(0, "resident", int(resident_no))
            frames["sessions"] = df

    # NEW: Workouts (event-level with start/end)
    if "workouts" in data and data["workouts"]:
        df = pd.DataFrame(
            data["workouts"]
        )  # includes start_datetime, end_datetime, activity, etc.
        if not df.empty:
            start_col = None
            for cand in ["start_datetime", "start_time", "start", "timestamp"]:
                if cand in df.columns:
                    start_col = cand
                    break
            if start_col is not None:
                df[start_col] = pd.to_datetime(df[start_col], errors="coerce")
                df["day"] = df[start_col].dt.normalize()
            elif "day" in df.columns:
                df["day"] = pd.to_datetime(df["day"], errors="coerce")
            else:
                df = pd.DataFrame()
        if not df.empty:
            nested_cols = [
                c
                for c in df.columns
                if not df[c].empty and isinstance(df[c].iloc[0], (list, dict))
            ]
            if nested_cols:
                df = df.drop(columns=nested_cols, errors="ignore")
            df.insert(0, "resident", int(resident_no))
            frames["workouts"] = df

    # NEW: Heart Rate daily summary (min/avg/max/count)
    if "heart_rate" in data and data["heart_rate"]:
        hr = pd.DataFrame(data["heart_rate"])  # expected columns: timestamp, bpm
        if not hr.empty:
            # Normalize column names
            if "timestamp" in hr.columns:
                hr["timestamp"] = pd.to_datetime(hr["timestamp"], errors="coerce")
                hr["day"] = hr["timestamp"].dt.normalize()
            elif "day" in hr.columns:
                hr["day"] = pd.to_datetime(hr["day"], errors="coerce")
            else:
                # Cannot compute daily summary without time or day
                hr = pd.DataFrame()

        if not hr.empty and "bpm" in hr.columns:
            grp = hr.dropna(subset=["day", "bpm"]).groupby("day")["bpm"]
            df = pd.DataFrame(
                {
                    "day": grp.mean().index,
                    "hr_avg": grp.mean().values,
                    "hr_min": grp.min().values,
                    "hr_max": grp.max().values,
                    "hr_samples": grp.count().values,
                }
            )
            df["day"] = pd.to_datetime(df["day"])  # ensure datetime64[ns]
            df.insert(0, "resident", int(resident_no))
            frames["daily_heart_rate"] = df

            # Optional: include raw heart rate samples table if enabled
            if os.getenv("OURA_INCLUDE_HEART_RATE_SAMPLES") == "1":
                hr_samples = hr.copy()
                # Retain essential columns only when present
                cols = [
                    c
                    for c in ["timestamp", "bpm", "source", "day"]
                    if c in hr_samples.columns
                ]
                hr_samples = hr_samples[cols]
                # Ensure timestamp and day types
                if "timestamp" in hr_samples.columns:
                    hr_samples["timestamp"] = pd.to_datetime(
                        hr_samples["timestamp"], errors="coerce"
                    )
                if (
                    "day" not in hr_samples.columns
                    and "timestamp" in hr_samples.columns
                ):
                    hr_samples["day"] = hr_samples["timestamp"].dt.normalize()
                if "day" in hr_samples.columns:
                    hr_samples["day"] = pd.to_datetime(
                        hr_samples["day"], errors="coerce"
                    )
                # Insert resident and add to frames if not empty
                hr_samples.insert(0, "resident", int(resident_no))
                if not hr_samples.empty:
                    frames["heart_rate_samples"] = hr_samples

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
    track_costs: bool = True,
) -> Dict[str, Any]:
    """
    Upload each frame to BigQuery as table: {table_prefix}_{name}

    - frames: dict[str, DataFrame]
    - dataset: target dataset (created if missing)
    - project: optional project override (defaults to ADC project)
    - location: optional BQ location (defaults to env BQ_LOCATION or 'US')
    - dry_run: when True, does not perform network calls, returns row counts
    - track_costs: when True, includes cost estimation in results

    Returns a dict with:
      - 'tables': mapping of table_name -> rows uploaded
      - 'cost_metrics': cost tracking information (if track_costs=True)
    """
    project = project or os.getenv("BQ_PROJECT") or None
    location = location or os.getenv("BQ_LOCATION", "US")

    results: Dict[str, int] = {}
    cost_metrics: Dict[str, Any] = {
        "total_bytes_processed": 0,
        "total_bytes_billed": 0,
        "estimated_cost_usd": 0.0,
        "tables": {},
    }

    # Validate content
    for name, df in frames.items():
        if df.empty:
            continue
        if "resident" not in df.columns or "day" not in df.columns:
            raise ValueError(
                f"Frame '{name}' missing required columns 'resident' and 'day'"
            )

    if dry_run:
        total_bytes = 0
        for name, df in frames.items():
            table_name = f"{table_prefix}_{name}"
            row_count = int(len(df))
            results[table_name] = row_count

            # Estimate data size for dry-run
            if track_costs:
                est_bytes = df.memory_usage(deep=True).sum()
                total_bytes += est_bytes
                cost_metrics["tables"][table_name] = {
                    "rows": row_count,
                    "estimated_bytes": int(est_bytes),
                }

        if track_costs:
            cost_metrics["total_bytes_processed"] = total_bytes
            # BigQuery pricing: $5 per TB processed (as of 2024)
            cost_metrics["estimated_cost_usd"] = (total_bytes / 1e12) * 5.0
            logger.info(
                f"[DRY-RUN] Would upload {len(results)} tables, "
                f"~{total_bytes / 1e6:.2f} MB, "
                f"estimated cost: ${cost_metrics['estimated_cost_usd']:.6f}"
            )

        return {"tables": results, "cost_metrics": cost_metrics}

    client = bigquery.Client(project=project, location=location)
    _ensure_dataset(client, dataset)

    total_bytes_processed = 0
    for name, df in frames.items():
        if df.empty:
            continue
        table_name = f"{table_prefix}_{name}"
        table_ref = client.dataset(dataset).table(table_name)

        # Configure load job to track statistics
        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )

        job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
        job.result()  # Wait for completion

        row_count = int(len(df))
        results[table_name] = row_count

        # Track cost metrics
        if track_costs:
            # Estimate bytes from DataFrame memory usage
            bytes_processed = df.memory_usage(deep=True).sum()
            total_bytes_processed += bytes_processed

            cost_metrics["tables"][table_name] = {
                "rows": row_count,
                "bytes_processed": int(bytes_processed),
                "job_id": job.job_id,
            }

            logger.info(
                f"Uploaded {table_name}: {row_count} rows, "
                f"{bytes_processed / 1e6:.2f} MB processed"
            )

    if track_costs:
        cost_metrics["total_bytes_processed"] = total_bytes_processed
        cost_metrics["total_bytes_billed"] = total_bytes_processed
        # BigQuery pricing: $5 per TB for data ingestion (streaming/batch loads are free)
        # Cost is mainly for queries, but we track it for monitoring
        cost_metrics["estimated_cost_usd"] = (total_bytes_processed / 1e12) * 5.0

        logger.info(
            f"Total upload: {len(results)} tables, "
            f"{total_bytes_processed / 1e6:.2f} MB processed, "
            f"estimated query cost: ${cost_metrics['estimated_cost_usd']:.6f}"
        )

    return {"tables": results, "cost_metrics": cost_metrics}


def export_daily_to_bigquery(
    resident_no: int,
    data: Dict[str, Any],
    *,
    dataset: str,
    table_prefix: str = "oura",
    project: str | None = None,
    location: str | None = None,
    dry_run: bool = True,
    track_costs: bool = True,
) -> Dict[str, Any]:
    """Convenience wrapper to build frames then upload them with cost tracking."""
    frames = build_daily_frames(data, resident_no)
    return upload_frames_to_bigquery(
        frames,
        dataset=dataset,
        table_prefix=table_prefix,
        project=project,
        location=location,
        dry_run=dry_run,
        track_costs=track_costs,
    )
