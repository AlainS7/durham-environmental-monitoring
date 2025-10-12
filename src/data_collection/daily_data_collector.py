"""Daily data collection orchestrator for WU and TSI sources.

Features:
 - Fetch raw or aggregated data
 - Clean/standardize column names, add canonical ts + float lat/lon copies
 - Upload wide parquet files to GCS (partitioned path layout)
 - Optional legacy DB insertion (wide->long melt)
 - Resilient upload: skip dataframes missing timestamp, tolerate validation issues
 - Local dev mode: set GCS_FAKE_UPLOAD=1 to bypass real network writes (logs intended paths)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import uuid
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, date as date_cls
from typing import Any, Tuple, Optional, List

import pandas as pd
import numpy as np
 # DB logic removed for BigQuery-only mode

from src.config.app_config import app_config
from typing import TYPE_CHECKING
if TYPE_CHECKING:  # only for type checkers; at runtime we may not have DB layer
    # from src.database.db_manager import HotDurhamDB
    # DB logic removed for BigQuery-only mode
    from src.storage.gcs_uploader import GCSUploader
    from src.data_collection.clients.wu_client import WUClient
    from src.data_collection.clients.tsi_client import TSIClient
    from src.utils.config_loader import get_wu_stations, get_tsi_devices
    from src.utils.schema_validation import (
        validate_tsi_schema,
        validate_wu_schema,
        check_tsi_coverage,
        check_wu_coverage,
        get_schema_info
    )

log = logging.getLogger(__name__)

# Allow runtime override of log level via LOG_LEVEL env var (DEBUG, INFO, WARNING, ERROR, CRITICAL)
_lvl = os.getenv('LOG_LEVEL')
if _lvl:
    try:
        logging.getLogger().setLevel(getattr(logging, _lvl.upper()))
    except Exception:  # pragma: no cover - defensive
        pass

# Diagnostic: log presence of critical env vars once (not their values) to verify Cloud Run template propagation.
_diag_logged = False
critical_env = [
    'PROJECT_ID','TSI_CREDS_SECRET_ID','WU_API_KEY_SECRET_ID',
    'GCS_BUCKET','GCS_PREFIX','BQ_PROJECT','BQ_DATASET','BQ_LOCATION','DISABLE_BQ_STAGING'
]
present = [k for k in critical_env if os.getenv(k)]
missing = [k for k in critical_env if k not in present]
logging.info("[Env diagnostic] present=%s missing=%s", present, missing)
for k in critical_env:
    logging.info("[Env var] %s = '%s'", k, os.getenv(k, '<unset>'))


# ---------------- Cleaning -----------------
def clean_and_transform_data(df: pd.DataFrame, source: str) -> pd.DataFrame:
    if df.empty:
        return df
    if source == "WU":
        rename_map = {
            'stationID': 'native_sensor_id', 'obsTimeUtc': 'timestamp',
            'tempAvg': 'temperature', 'tempHigh': 'temperature_high', 'tempLow': 'temperature_low',
            'humidityAvg': 'humidity', 'humidityHigh': 'humidity_high', 'humidityLow': 'humidity_low',
            'precipRate': 'precip_rate', 'precipTotal': 'precip_total',
            'windspeedAvg': 'wind_speed_avg', 'windspeedHigh': 'wind_speed_high', 'windspeedLow': 'wind_speed_low',
            'windgustAvg': 'wind_gust_avg', 'windgustHigh': 'wind_gust_high', 'windgustLow': 'wind_gust_low',
            'winddirAvg': 'wind_direction_avg',
            'pressureMax': 'pressure_max', 'pressureMin': 'pressure_min', 'pressureTrend': 'pressure_trend',
            'solarRadiationHigh': 'solar_radiation', 'uvHigh': 'uv_high',
            'windchillAvg': 'wind_chill_avg', 'windchillHigh': 'wind_chill_high', 'windchillLow': 'wind_chill_low',
            'heatindexAvg': 'heat_index_avg', 'heatindexHigh': 'heat_index_high', 'heatindexLow': 'heat_index_low',
            'dewptAvg': 'dew_point_avg', 'dewptHigh': 'dew_point_high', 'dewptLow': 'dew_point_low',
            'qcStatus': 'qc_status', 'obsTimeLocal': 'obsTimeLocal'
        }
    else:  # TSI
        rename_map = {
            'cloud_device_id': 'native_sensor_id', 'device_id': 'native_sensor_id',
            'cloud_timestamp': 'timestamp', 'cloud_account_id': 'cloud_account_id',
            # PM measurements
            'pm1_0': 'pm1_0', 'pm2_5': 'pm2_5', 'pm4_0': 'pm4_0', 'pm10': 'pm10',
            'pm2_5_aqi': 'pm2_5_aqi', 'pm10_aqi': 'pm10_aqi',
            # Number concentration measurements
            'ncpm0_5': 'ncpm0_5', 'ncpm1_0': 'ncpm1_0', 'ncpm2_5': 'ncpm2_5',
            'ncpm4_0': 'ncpm4_0', 'ncpm10': 'ncpm10',
            # Environmental measurements
            'rh': 'humidity', 'temperature': 'temperature', 'tpsize': 'tpsize',
            # Gas measurements
            'co2_ppm': 'co2_ppm', 'co_ppm': 'co_ppm', 'o3_ppb': 'o3_ppb',
            'no2_ppb': 'no2_ppb', 'so2_ppb': 'so2_ppb', 'ch2o_ppb': 'ch2o_ppb',
            'voc_mgm3': 'voc_mgm3', 'baro_inhg': 'baro_inhg',
            # Metadata
            'model': 'model', 'serial': 'serial', 'is_indoor': 'is_indoor',
            'is_public': 'is_public', 'latitude': 'latitude', 'longitude': 'longitude'
        }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
    if 'timestamp' in df.columns:
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        df['ts'] = df['timestamp']
    # lat/lon float copies
    for pair in [('latitude', 'longitude'), ('lat', 'lon')]:
        lat_col, lon_col = pair
        if lat_col in df.columns and lon_col in df.columns:
            for c in pair:
                try:
                    df[f"{c}_f"] = pd.to_numeric(df[c], errors='coerce').astype(float)
                except Exception:
                    pass
    return df


# ------------- DB Insertion ---------------


def _coerce_to_date(value: Any) -> Optional[date_cls]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        ts = pd.Timestamp(value)
    except Exception:
        return None
    if pd.isna(ts):
        return None
    if ts.tzinfo is not None:
        try:
            ts = ts.tz_convert('UTC')
        except (TypeError, ValueError):
            pass
    return ts.to_pydatetime().date()


def _coerce_to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not pd.isna(value):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _build_sensor_catalog() -> dict[tuple[str, str], dict[str, Any]]:
    catalog: dict[tuple[str, str], dict[str, Any]] = {}
    today = datetime.utcnow().date()

    for station in get_wu_stations() or []:
        sensor_id = station.get('stationId') or station.get('id')
        if not sensor_id:
            continue
        friendly = (station.get('friendly_name') or station.get('name') or str(sensor_id)).strip()
        if not friendly:
            friendly = str(sensor_id)
        location = (station.get('location') or friendly or str(sensor_id)).strip()
        if not location:
            location = str(sensor_id)
        start_hint = station.get('start_date') or station.get('startDate')
        start_date = _coerce_to_date(start_hint) or today
        catalog[(sensor_id, 'WU')] = {
            'native_sensor_id': sensor_id,
            'sensor_type': 'WU',
            'friendly_name': friendly,
            'location': location,
            'latitude': _coerce_to_float(station.get('latitude') or station.get('lat')),
            'longitude': _coerce_to_float(station.get('longitude') or station.get('lon')),
            'start_date': start_date,
        }

    for device_id in get_tsi_devices() or []:
        if not device_id:
            continue
        catalog[(device_id, 'TSI')] = {
            'native_sensor_id': device_id,
            'sensor_type': 'TSI',
            'friendly_name': device_id,
            'location': device_id,
            'latitude': None,
            'longitude': None,
            'start_date': today,
        }

    return catalog


def _augment_catalog_with_data(catalog: dict[tuple[str, str], dict[str, Any]], df: pd.DataFrame, sensor_type: str):
    if df.empty or 'native_sensor_id' not in df.columns or 'timestamp' not in df.columns:
        return
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated()]
    try:
        subset = df[['native_sensor_id', 'timestamp']].dropna()
    except KeyError:
        return
    if subset.empty:
        return
    grouped = subset.groupby('native_sensor_id')['timestamp'].min()
    for sensor_id, first_ts in grouped.items():
        sensor_key = str(sensor_id)
        start_date = _coerce_to_date(first_ts)
        if start_date is None:
            continue
        key = (sensor_key, sensor_type)
        record = catalog.get(key)
        if record is None:
            catalog[key] = {
                'native_sensor_id': sensor_key,
                'sensor_type': sensor_type,
                'friendly_name': sensor_key,
                'location': sensor_key,
                'latitude': None,
                'longitude': None,
                'start_date': start_date,
            }
        elif start_date < record.get('start_date', start_date):
            record['start_date'] = start_date


 # All legacy DB logic removed for BigQuery-only mode
    # DB connectivity check removed for BigQuery-only mode


###########################
# Refactored orchestration
###########################

def _normalize_dates(start_date: datetime | str, end_date: datetime | str) -> tuple[str, str]:
    start_str = start_date if isinstance(start_date, str) else start_date.strftime('%Y-%m-%d')
    end_str = end_date if isinstance(end_date, str) else end_date.strftime('%Y-%m-%d')
    return start_str, end_str


async def _fetch_raw(start_str: str, end_str: str, source: str, aggregate: bool, agg_interval: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    wu_raw = pd.DataFrame()
    tsi_raw = pd.DataFrame()
    if source == 'all':
        async with WUClient(**app_config.wu_api_config) as wu_client, TSIClient(**app_config.tsi_api_config) as tsi_client:
            wu_task = wu_client.fetch_data(start_str, end_str, aggregate=aggregate, agg_interval=agg_interval) if (aggregate or agg_interval != 'h') else wu_client.fetch_data(start_str, end_str)
            tsi_task = tsi_client.fetch_data(start_str, end_str, aggregate=aggregate, agg_interval=agg_interval) if (aggregate or agg_interval != 'h') else tsi_client.fetch_data(start_str, end_str)
            wu_raw, tsi_raw = await asyncio.gather(wu_task, tsi_task, return_exceptions=False)
    elif source == 'wu':
        async with WUClient(**app_config.wu_api_config) as wu_client:
            wu_raw = await (wu_client.fetch_data(start_str, end_str, aggregate=aggregate, agg_interval=agg_interval) if (aggregate or agg_interval != 'h') else wu_client.fetch_data(start_str, end_str))
    elif source == 'tsi':
        async with TSIClient(**app_config.tsi_api_config) as tsi_client:
            tsi_raw = await (tsi_client.fetch_data(start_str, end_str, aggregate=aggregate, agg_interval=agg_interval) if (aggregate or agg_interval != 'h') else tsi_client.fetch_data(start_str, end_str))
    return wu_raw, tsi_raw


def _clean(wu_raw: pd.DataFrame, tsi_raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    wu_df = clean_and_transform_data(wu_raw, 'WU') if not wu_raw.empty else pd.DataFrame()
    tsi_df = clean_and_transform_data(tsi_raw, 'TSI') if not tsi_raw.empty else pd.DataFrame()
    log.info(f"Fetched WU={len(wu_raw)} TSI={len(tsi_raw)} raw rows -> cleaned WU={len(wu_df)} TSI={len(tsi_df)}")
    return wu_df, tsi_df


def _has_ts(df: pd.DataFrame) -> bool:
    return not df.empty and (('ts' in df.columns) or ('timestamp' in df.columns))


def _build_uploader(bucket: str, prefix: str):
    if os.getenv('GCS_FAKE_UPLOAD') == '1':
        class _DummyUploader:
            def __init__(self, bucket: str, prefix: str):
                self.bucket_name = bucket
                self.prefix = prefix
            def upload_parquet(self, df: pd.DataFrame, source: str, aggregated=False, interval='h', ts_column='timestamp', extra_suffix=None):
                if df.empty:
                    log.info(f"[FAKE] skip empty {source}")
                    return ''
                use_col = ts_column if ts_column in df.columns else 'timestamp'
                first_ts = pd.to_datetime(df[use_col]).min()
                date_str = first_ts.strftime('%Y-%m-%d') if not pd.isna(first_ts) else 'unknown-date'
                agg_part = interval if aggregated else 'raw'
                path = f"{self.prefix}/source={source}/agg={agg_part}/dt={date_str}/{source}-{date_str}.parquet"
                log.info(f"[FAKE] Would upload {len(df)} rows to gs://{self.bucket_name}/{path}")
                return f"gs://{self.bucket_name}/{path}"
        return _DummyUploader(bucket, prefix)
    return GCSUploader(bucket=bucket, prefix=prefix)


def _safe_upload(uploader: Any, df: pd.DataFrame, src: str, aggregate: bool, agg_interval: str) -> bool:
    """
    Upload DataFrame to GCS with schema validation and error handling.
    
    Returns True if upload succeeded, False otherwise.
    """
    if df.empty:
        log.info(f"Skip {src}: empty")
        return False
    
    ts_col = 'ts' if 'ts' in df.columns else ('timestamp' if 'timestamp' in df.columns else None)
    if not ts_col:
        log.warning(f"Skip {src}: no ts/timestamp column")
        return False
    
    # Validate schema before upload (non-aggregated data only)
    if not aggregate:
        if src == 'TSI':
            schema_valid = validate_tsi_schema(df)
            coverage_valid = check_tsi_coverage(df)
            if not schema_valid:
                log.error("TSI schema validation failed - uploading anyway but data quality may be impacted")
                log.debug(f"TSI schema info: {get_schema_info(df)}")
            if not coverage_valid:
                log.warning("TSI coverage check failed - some critical fields have low coverage")
        elif src == 'WU':
            schema_valid = validate_wu_schema(df)
            coverage_valid = check_wu_coverage(df)
            if not schema_valid:
                log.error("WU schema validation failed - uploading anyway but data quality may be impacted")
                log.debug(f"WU schema info: {get_schema_info(df)}")
            if not coverage_valid:
                log.warning("WU coverage check failed - some critical fields have low coverage")
    
    try:
        uploader.upload_parquet(df, source=src, aggregated=aggregate, interval=agg_interval, ts_column=ts_col)
        return True
    except ValueError as ve:
        log.warning(f"{src} upload validation skipped: {ve}")
    except Exception:
        log.error(f"Unexpected {src} upload error", exc_info=True)
    return False


def _sink_data(wu_df: pd.DataFrame, tsi_df: pd.DataFrame, sink: str, aggregate: bool, agg_interval: str) -> tuple[bool, bool]:
    wrote_wu = wrote_tsi = False
    wrote_any = False
    # Allow hard disable of any DB interaction (Cloud SQL optional) via env DISABLE_DB_SINK=1
    # In BigQuery-only mode, default to disabled when env var is unset
    disable_db = os.getenv('DISABLE_DB_SINK', '1') == '1'
    if sink in ('gcs', 'both'):
        gcs_cfg = app_config.gcs_config
        bucket = gcs_cfg.get('bucket')
        if not bucket:
            log.error("No GCS bucket configured; skip GCS sink")
        else:
            uploader = _build_uploader(bucket, gcs_cfg.get('prefix', 'sensor_readings'))
            wrote_wu = _safe_upload(uploader, wu_df, 'WU', aggregate, agg_interval) or wrote_wu
            wrote_tsi = _safe_upload(uploader, tsi_df, 'TSI', aggregate, agg_interval) or wrote_tsi
            wrote_any = wrote_wu or wrote_tsi

    if not disable_db and (sink in ('db', 'both') or (sink == 'gcs' and not wrote_any)):
    # DB logic removed for BigQuery-only mode
        if (not _has_ts(wu_df)) and not wu_df.empty:
            log.warning("WU missing ts/timestamp -> not inserting")
        if (not _has_ts(tsi_df)) and not tsi_df.empty:
            log.warning("TSI missing ts/timestamp -> not inserting")
        # All DB logic removed for BigQuery-only mode
        # DB logic removed for BigQuery-only mode
    elif disable_db:
        log.info("DB sink disabled via DISABLE_DB_SINK=1")
    return wrote_wu, wrote_tsi


###########################
# BigQuery staging writer
###########################

def _write_bq_staging(wu_df: pd.DataFrame, tsi_df: pd.DataFrame, start_str: str, end_str: str):
    """Materialize per-source dated staging tables in BigQuery.

    Table pattern: staging_<source>_<YYYYMMDD> with columns (timestamp, deployment_fk, metric_name, value).
    Always enabled by default to unblock downstream merge/backfill unless explicitly disabled via
    DISABLE_BQ_STAGING=1. This avoids needing Cloud Run env var updates.

    If a single run spans multiple days (rare – typical orchestration loops day-by-day), data
    is split per date and each date's table is (re)written (WRITE_TRUNCATE) to maintain idempotency.
    """
    if os.getenv('DISABLE_BQ_STAGING') == '1':  # opt-out switch
        log.info("BQ staging disabled via DISABLE_BQ_STAGING=1")
        return
    if os.getenv('DISABLE_DB_SINK') == '1':
        # Deployment mapping currently sourced from DB; skip quietly when DB disabled.
        log.info("BQ staging skipped because DB sink disabled (needs deployment mapping refactor).")
        return
    if wu_df.empty and tsi_df.empty:
        log.info("No dataframes to stage to BigQuery (both empty).")
        return
    try:
        from google.cloud import bigquery  # lazy import to keep optional
    except Exception as e:  # pragma: no cover
        log.error(f"BigQuery client import failed – cannot write staging tables: {e}")
        return

    bq_project = os.getenv('BQ_PROJECT') or None  # ADC if None
    dataset = os.getenv('BQ_DATASET', 'sensors')
    client = bigquery.Client(project=bq_project)

    # Fetch deployment mapping (active only)
    deployment_map_df = pd.DataFrame()
    # DB logic removed for BigQuery-only mode
    if deployment_map_df.empty:
        log.error("Deployment map empty – cannot build BigQuery staging tables.")
        return

    def _prepare_long(df: pd.DataFrame, sensor_type: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=['timestamp','deployment_fk','metric_name','value'])
        if df.columns.duplicated().any():
            working = df.loc[:, ~df.columns.duplicated()].copy()
        else:
            working = df.copy()
        type_map = deployment_map_df[deployment_map_df.sensor_type == sensor_type]
        if type_map.empty:
            log.warning(f"No active deployments for type {sensor_type} – skipping staging long melt")
            return pd.DataFrame(columns=['timestamp','deployment_fk','metric_name','value'])
        merged = working.merge(type_map, on='native_sensor_id', how='inner')
        if merged.empty:
            log.warning(f"No rows matched deployments for {sensor_type} – skipping")
            return pd.DataFrame(columns=['timestamp','deployment_fk','metric_name','value'])
        merged = merged.rename(columns={'deployment_pk': 'deployment_fk'})
        id_vars = ['timestamp', 'deployment_fk']
        candidate_vars = [c for c in merged.columns if c not in id_vars + ['native_sensor_id','sensor_type']]
        numeric_vars: list[str] = []
        for col in candidate_vars:
            coerced = pd.to_numeric(merged[col], errors='coerce')
            if coerced.notna().any():
                merged[col] = coerced
                numeric_vars.append(col)
        if not numeric_vars:
            return pd.DataFrame(columns=['timestamp','deployment_fk','metric_name','value'])
        long_df = pd.melt(merged, id_vars=id_vars, value_vars=numeric_vars, var_name='metric_name', value_name='value')
        long_df['value'] = pd.to_numeric(long_df['value'], errors='coerce')
        long_df = long_df.dropna(subset=['value']).drop_duplicates(subset=['timestamp','deployment_fk','metric_name'], keep='last')
        return long_df

    wu_long = _prepare_long(wu_df, 'WU')
    tsi_long = _prepare_long(tsi_df, 'TSI')

    def _split_and_load(long_df: pd.DataFrame, source_label: str):
        if long_df.empty:
            return 0
        long_df['date'] = pd.to_datetime(long_df['timestamp']).dt.date
        distinct_dates: List[date_cls] = sorted(long_df['date'].unique())  # type: ignore[arg-type]
        total_rows = 0
        for d in distinct_dates:
            day_df = long_df[long_df['date'] == d].drop(columns=['date']).copy()
            if 'timestamp' not in day_df.columns:
                log.warning("Skipping %s staging for %s – no timestamp column", source_label, d)
                continue
            ts_series = day_df['timestamp']
            if pd.api.types.is_numeric_dtype(ts_series):
                numeric = pd.to_numeric(ts_series, errors='coerce')
                max_abs = numeric.abs().max()
                if pd.isna(max_abs):
                    ts_converted = pd.to_datetime(numeric, utc=True, errors='coerce')
                elif max_abs > 9_007_199_254_740_992:  # larger than float64 safe range -> assume nanoseconds
                    ts_converted = pd.to_datetime(numeric, utc=True, errors='coerce', unit='ns')
                elif max_abs > 9_007_199_254_740:  # microseconds range
                    ts_converted = pd.to_datetime(numeric, utc=True, errors='coerce', unit='us')
                else:
                    ts_converted = pd.to_datetime(numeric, utc=True, errors='coerce', unit='s')
            else:
                ts_converted = pd.to_datetime(ts_series, utc=True, errors='coerce')
            ts_converted = ts_converted.dt.tz_convert('UTC') if ts_converted.dt.tz is not None else ts_converted.dt.tz_localize('UTC')
            ts_py = pd.Series(
                [
                    value.to_pydatetime() if pd.notna(value) else None
                    for value in ts_converted
                ],
                index=ts_converted.index,
                dtype=object,
            )
            day_df['timestamp'] = ts_py

            def _ensure_py_datetime(value: Any) -> Optional[datetime]:
                if value is None or (isinstance(value, float) and pd.isna(value)):
                    return None
                if isinstance(value, datetime):
                    # Return timezone-naive datetime (BigQuery TIMESTAMP is implicitly UTC)
                    return value.replace(tzinfo=None) if value.tzinfo is not None else value
                if isinstance(value, pd.Timestamp):
                    ts_val = value.tz_convert('UTC') if value.tzinfo is not None else value.tz_localize('UTC')
                    # Return timezone-naive datetime
                    return ts_val.to_pydatetime().replace(tzinfo=None)
                if isinstance(value, (np.integer, int)):
                    magnitude = abs(int(value))
                    if magnitude > 9_007_199_254_740_992:
                        dt = pd.to_datetime(int(value), utc=True, errors='coerce', unit='ns')
                    elif magnitude > 9_007_199_254_740:
                        dt = pd.to_datetime(int(value), utc=True, errors='coerce', unit='us')
                    else:
                        dt = pd.to_datetime(int(value), utc=True, errors='coerce', unit='s')
                    if pd.isna(dt):
                        return None
                    # Return timezone-naive datetime
                    return dt.to_pydatetime().replace(tzinfo=None)
                if isinstance(value, (np.floating, float)):
                    if pd.isna(value):
                        return None
                    return _ensure_py_datetime(int(value))
                if isinstance(value, str):
                    parsed = pd.to_datetime(value, utc=True, errors='coerce')
                    if pd.isna(parsed):
                        return None
                    # Return timezone-naive datetime
                    return parsed.to_pydatetime().replace(tzinfo=None)
                return None

            ensured_py = pd.Series(
                [
                    _ensure_py_datetime(value) for value in day_df['timestamp']
                ],
                index=day_df.index,
                dtype=object,
            )
            coerced_ts = pd.to_datetime(ensured_py, utc=True, errors='coerce')
            invalid_mask = coerced_ts.isna()
            if invalid_mask.any():
                dropped = int(invalid_mask.sum())
                sample_bad = day_df.loc[invalid_mask, 'timestamp'].head().tolist()
                log.warning(
                    "Dropped %s rows with invalid timestamps for %s on %s (raw samples=%s)",
                    dropped,
                    source_label,
                    d,
                    sample_bad,
                )
                day_df = day_df.loc[~invalid_mask].copy()
            if day_df.empty:
                log.warning("No valid timestamps remain for %s on %s after coercion", source_label, d)
                continue
            coerced_ts = coerced_ts.loc[day_df.index]
            if coerced_ts.dt.tz is None:
                coerced_ts = coerced_ts.dt.tz_localize('UTC')
            else:
                coerced_ts = coerced_ts.dt.tz_convert('UTC')
            py_ts = pd.Series(
                [ts.to_pydatetime() for ts in coerced_ts],
                index=coerced_ts.index,
                dtype=object,
            )
            day_df['timestamp'] = py_ts
            numeric_mask = day_df['timestamp'].apply(lambda v: isinstance(v, (np.integer, int, np.floating, float)))
            if numeric_mask.any():
                numeric_count = int(numeric_mask.sum())
                log.warning(
                    "Re-coercing %s numeric timestamp values for %s on %s after initial conversion",
                    numeric_count,
                    source_label,
                    d,
                )
                day_df.loc[numeric_mask, 'timestamp'] = day_df.loc[numeric_mask, 'timestamp'].apply(_ensure_py_datetime)
            non_dt_mask = day_df['timestamp'].apply(lambda v: v is not None and not isinstance(v, datetime))
            if non_dt_mask.any():
                samples = day_df.loc[non_dt_mask, 'timestamp'].head().tolist()
                log.warning(
                    "Unexpected non-datetime values persisted for %s on %s: %s",
                    source_label,
                    d,
                    samples,
                )
                day_df.loc[non_dt_mask, 'timestamp'] = day_df.loc[non_dt_mask, 'timestamp'].apply(_ensure_py_datetime)
            ensured_final = pd.Series(
                [
                    _ensure_py_datetime(value) for value in day_df['timestamp']
                ],
                index=day_df.index,
                dtype=object,
            )
            invalid_final = ensured_final.isna()
            if invalid_final.any():
                dropped_final = int(invalid_final.sum())
                log.warning(
                    "Dropping %s rows with invalid timestamps after final coercion for %s on %s",
                    dropped_final,
                    source_label,
                    d,
                )
                day_df = day_df.loc[~invalid_final].copy()
                ensured_final = ensured_final.loc[day_df.index]
                if day_df.empty:
                    log.warning("No valid timestamps remain for %s on %s after final coercion", source_label, d)
                    continue
            type_counts = ensured_final.apply(lambda v: type(v).__name__).value_counts().to_dict()
            log.warning(
                "Timestamp type distribution for %s on %s: %s",
                source_label,
                d,
                type_counts,
            )
            # Use ensured_final (object dtype with Python datetimes) directly
            day_df['timestamp'] = ensured_final
            table_name = f"staging_{source_label.lower()}_{d.strftime('%Y%m%d')}"
            fq = f"{client.project}.{dataset}.{table_name}"
            
            # Convert timezone-naive datetime objects to formatted strings for BigQuery
            # ISO format is parseable by BigQuery's TIMESTAMP type
            day_df['timestamp'] = day_df['timestamp'].apply(
                lambda dt: dt.strftime('%Y-%m-%d %H:%M:%S') if isinstance(dt, datetime) else None
            )
            
            schema = [
                bigquery.SchemaField('timestamp','TIMESTAMP'),
                bigquery.SchemaField('deployment_fk','INT64'),
                bigquery.SchemaField('metric_name','STRING'),
                bigquery.SchemaField('value','FLOAT64'),
            ]
            # Create table if missing (no partitioning needed – table is per-date)
            try:
                client.get_table(fq)
            except Exception:
                tbl = bigquery.Table(fq, schema=schema)
                client.create_table(tbl)
                log.info(f"Created staging table {fq}")
            # Use autodetect instead of explicit schema to avoid PyArrow type conflicts
            job_config = bigquery.LoadJobConfig(
                write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
                autodetect=True,
            )
            if not day_df.empty:
                sample_ts = day_df['timestamp'].iloc[0]
                log.warning(
                    "Prepared %s staging frame for %s: dtype=%s sample=%s type=%s",
                    source_label,
                    d,
                    day_df['timestamp'].dtype,
                    sample_ts,
                    type(sample_ts)
                )
            log.info(f"Loading {len(day_df)} rows into {fq} (truncate replace)")
            load_job = client.load_table_from_dataframe(day_df[['timestamp','deployment_fk','metric_name','value']], fq, job_config=job_config)
            load_job.result()
            total_rows += len(day_df)
        return total_rows

    wu_rows = _split_and_load(wu_long, 'WU')
    tsi_rows = _split_and_load(tsi_long, 'TSI')
    log.info(f"BigQuery staging write complete: WU rows={wu_rows} TSI rows={tsi_rows}")


def _log_run_metadata(run_id: str, start_str: str, end_str: str, run_started: datetime, wu_raw: pd.DataFrame, tsi_raw: pd.DataFrame, wu_df: pd.DataFrame, tsi_df: pd.DataFrame, wrote_wu: bool, wrote_tsi: bool, aggregate: bool, agg_interval: str, sink: str, source: str):
    if os.getenv('BQ_RUN_METADATA') != '1':
        return
    try:
        from google.cloud import bigquery  # lazy import
        bq_project = os.getenv('BQ_PROJECT') or None
        bq_dataset = os.getenv('BQ_DATASET', 'sensors')
        table_id = os.getenv('BQ_RUN_METADATA_TABLE', 'ingestion_runs')
        client = bigquery.Client(project=bq_project)
        fq = f"{client.project}.{bq_dataset}.{table_id}"
        try:
            client.get_table(fq)
        except Exception:
            schema = [
                bigquery.SchemaField('run_id','STRING'),
                bigquery.SchemaField('start_date','DATE'),
                bigquery.SchemaField('end_date','DATE'),
                bigquery.SchemaField('run_started','TIMESTAMP'),
                bigquery.SchemaField('run_finished','TIMESTAMP'),
                bigquery.SchemaField('wu_rows','INT64'),
                bigquery.SchemaField('tsi_rows','INT64'),
                bigquery.SchemaField('wu_written','BOOL'),
                bigquery.SchemaField('tsi_written','BOOL'),
                bigquery.SchemaField('aggregate','BOOL'),
                bigquery.SchemaField('agg_interval','STRING'),
                bigquery.SchemaField('sink','STRING'),
                bigquery.SchemaField('source','STRING'),
                bigquery.SchemaField('status','STRING'),
            ]
            tbl = bigquery.Table(fq, schema=schema)
            client.create_table(tbl, exists_ok=True)
        rows_to_insert = [{
            'run_id': run_id,
            'start_date': start_str,
            'end_date': end_str,
            'run_started': run_started,
            'run_finished': datetime.utcnow(),
            'wu_rows': int(len(wu_raw)),
            'tsi_rows': int(len(tsi_raw)),
            'wu_written': bool(not wu_df.empty and wrote_wu),
            'tsi_written': bool(not tsi_df.empty and wrote_tsi),
            'aggregate': bool(aggregate),
            'agg_interval': agg_interval,
            'sink': sink,
            'source': source,
            'status': 'success'
        }]
        errors = client.insert_rows_json(fq, rows_to_insert)
        if errors:
            log.error(f"Run metadata insert errors: {errors}")
        else:
            log.info(f"Logged run metadata to {fq} run_id={run_id}")
    except Exception as e:
        log.error(f"Failed to log run metadata: {e}")


@dataclass(slots=True)
class RunConfig:
    start_date: datetime | str
    end_date: datetime | str
    is_dry_run: bool = False
    aggregate: bool = False
    agg_interval: str = 'h'
    sink: str = 'gcs'
    source: str = 'all'

    # Backward compat helper to allow existing call style
    @classmethod
    def from_legacy(cls, start: datetime | str, end: datetime | str, **kwargs):
        return cls(start_date=start, end_date=end, **kwargs)


def _maybe_show_samples(wu_df: pd.DataFrame, tsi_df: pd.DataFrame):
    if not wu_df.empty:
        print("WU sample:\n", wu_df.head())
    if not tsi_df.empty:
        print("TSI sample:\n", tsi_df.head())


async def run_collection_process(
    start_date: datetime | str,
    end_date: datetime | str,
    is_dry_run: bool = False,
    aggregate: bool = False,
    agg_interval: str = 'h',
    sink: str = 'gcs',
    source: str = 'all',
    config: Optional[RunConfig] = None,
):
    """Primary orchestration entrypoint.

    Either supply legacy individual parameters (maintained for backward compatibility & tests)
    or pass a RunConfig via the config parameter (preferred going forward) which reduces the
    CodeScene flagged long argument list.
    """
    if config is None:
        config = RunConfig.from_legacy(start_date, end_date, is_dry_run=is_dry_run, aggregate=aggregate, agg_interval=agg_interval, sink=sink, source=source)
    # Local variable aliasing for readability
    start_date = config.start_date
    end_date = config.end_date
    log.info(
        "Run collection %s -> %s dry=%s aggregate=%s interval=%s sink=%s source=%s",
        start_date, end_date, config.is_dry_run, config.aggregate, config.agg_interval, config.sink, config.source
    )

    # Refactored: process each day in the range individually
    start_dt = start_date if isinstance(start_date, datetime) else datetime.strptime(start_date, '%Y-%m-%d')
    end_dt = end_date if isinstance(end_date, datetime) else datetime.strptime(end_date, '%Y-%m-%d')
    total_days = (end_dt.date() - start_dt.date()).days + 1
    log.info(f"Processing {total_days} days: {start_dt.date()} to {end_dt.date()}")
    for i in range(total_days):
        day = start_dt + timedelta(days=i)
        day_str = day.strftime('%Y-%m-%d')
        log.info(f"--- Processing day {day_str} ---")
        run_id = uuid.uuid4().hex
        run_started = datetime.utcnow()
        try:
            log.info(f"[DEBUG] Starting TSI fetch for all devices on {day_str}")
            wu_raw, tsi_raw = await _fetch_raw(day_str, day_str, config.source, config.aggregate, config.agg_interval)
            log.info(f"[DEBUG] Completed TSI fetch for {day_str}. wu_raw rows: {len(wu_raw) if wu_raw is not None else 'None'}, tsi_raw rows: {len(tsi_raw) if tsi_raw is not None else 'None'}")
            if tsi_raw is not None and hasattr(tsi_raw, 'empty') and tsi_raw.empty:
                log.warning(f"[DEBUG] No TSI data returned for {day_str}")
            wu_df, tsi_df = _clean(wu_raw, tsi_raw)
            if config.is_dry_run:
                log.info(f"DRY RUN: showing head only for {day_str}")
                _maybe_show_samples(wu_df, tsi_df)
                continue
            wrote_wu, wrote_tsi = _sink_data(wu_df, tsi_df, config.sink, config.aggregate, config.agg_interval)
            try:
                _write_bq_staging(wu_df, tsi_df, day_str, day_str)
            except Exception:
                log.error(f"Unhandled error while writing BigQuery staging tables for {day_str}", exc_info=True)
            if not (wrote_wu or wrote_tsi):
                log.warning(f"No data written to any sink for {day_str}.")
            else:
                log.info(f"Data written for {day_str}: WU={wrote_wu}, TSI={wrote_tsi}")
            _log_run_metadata(
                run_id, day_str, day_str, run_started,
                wu_raw, tsi_raw, wu_df, tsi_df,
                wrote_wu, wrote_tsi,
                config.aggregate, config.agg_interval, config.sink, config.source
            )
        except Exception as e:
            log.error(f"Exception processing {day_str}: {e}", exc_info=True)
    log.info("Collection complete for all days.")


# ------------- CLI ---------------
def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Collect daily sensor data")
    p.add_argument('--days', type=int, default=0, help='How many days back from today (start inclusive)')
    p.add_argument('--start', type=str, help='Explicit start date YYYY-MM-DD (overrides --days)')
    p.add_argument('--end', type=str, help='Explicit end date YYYY-MM-DD (default today)')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--aggregate', action='store_true')
    p.add_argument('--agg-interval', default='h')
    p.add_argument('--sink', choices=['gcs','db','both'], default='gcs')
    p.add_argument('--source', choices=['all','wu','tsi'], default='all')
    return p.parse_args(argv)


def compute_date_range(args: argparse.Namespace) -> Tuple[datetime, datetime]:
    if args.start:
        start = datetime.strptime(args.start, '%Y-%m-%d')
        end = datetime.strptime(args.end, '%Y-%m-%d') if args.end else datetime.utcnow()
    else:
        # days=0 means today only
        ingest_env = os.getenv('INGEST_DATE')
        if ingest_env and args.days == 0:  # environment-provided explicit date
            try:
                start = datetime.strptime(ingest_env, '%Y-%m-%d')
                end = start  # single day
                log.info(f"Using INGEST_DATE env override: {ingest_env}")
            except Exception:
                log.warning(f"Invalid INGEST_DATE '{ingest_env}' – falling back to days offset")
                end = datetime.utcnow()
                start = end - timedelta(days=args.days)
        else:
            end = datetime.utcnow()
            start = end - timedelta(days=args.days)
    return start, end


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    start, end = compute_date_range(args)
    asyncio.run(run_collection_process(start, end, is_dry_run=args.dry_run, aggregate=args.aggregate, agg_interval=args.agg_interval, sink=args.sink, source=args.source))


if __name__ == '__main__':  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    main()