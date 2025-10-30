# -*- coding: utf-8 -*-
"""
Oura Data Transformations
Utilities to flatten and transform Oura API responses into DataFrames.
"""

import pandas as pd


def dict_to_df(
    data: list[dict], label: str, score_label: str = "score"
) -> pd.DataFrame:
    """
    Convert list of dicts into a DataFrame with flattened contributors.

    Args:
        data: List of Oura API response objects (e.g., daily_sleep records)
        label: Source label for the data (e.g., "sleep", "activity")
        score_label: Name for the score column (e.g., "sleep_score", "activity_score")

    Returns:
        DataFrame with columns: day, source, <score_label>, and flattened contributors
    """
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


def combine_daily_dataframes(
    sleep_data: list[dict] | None = None,
    activity_data: list[dict] | None = None,
    readiness_data: list[dict] | None = None,
) -> pd.DataFrame:
    """
    Combine sleep, activity, and readiness data into a single daily DataFrame.

    Returns a wide DataFrame with one row per day containing all metrics.
    """
    daily_dfs = []

    if sleep_data:
        daily_dfs.append(dict_to_df(sleep_data, "sleep", "sleep_score"))
    if activity_data:
        daily_dfs.append(dict_to_df(activity_data, "activity", "activity_score"))
    if readiness_data:
        daily_dfs.append(dict_to_df(readiness_data, "readiness", "readiness_score"))

    if not daily_dfs:
        return pd.DataFrame()

    df_daily = pd.concat(daily_dfs, ignore_index=True)
    df_daily = (
        df_daily.drop(columns=["source"], errors="ignore")
        .groupby("day", as_index=False)
        .first()
    )
    return df_daily
