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
from sqlalchemy import text

from src.config.app_config import app_config
from src.database.db_manager import HotDurhamDB
from src.storage.gcs_uploader import GCSUploader
from src.data_collection.clients.wu_client import WUClient
from src.data_collection.clients.tsi_client import TSIClient

log = logging.getLogger(__name__)


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
            'qcStatus': 'qc_status'
        }
    else:  # TSI
        rename_map = {
            'cloud_device_id': 'native_sensor_id', 'device_id': 'native_sensor_id', 'cloud_timestamp': 'timestamp',
            'mcpm10': 'pm10', 'mcpm10_aqi': 'pm10_aqi', 'mcpm1x0': 'pm1_0', 'mcpm2x5': 'pm2_5', 'mcpm2x5_aqi': 'pm2_5_aqi',
            'mcpm4x0': 'ncpm4_0', 'ncpm0x5': 'ncpm0_5', 'ncpm10': 'ncpm10', 'ncpm1x0': 'ncpm1_0', 'ncpm2x5': 'ncpm2_5', 'ncpm4x0': 'ncpm4_0',
            'rh': 'humidity', 'temperature': 'temperature', 'tpsize': 'tpsize', 'co2_ppm': 'co2_ppm', 'co_ppm': 'co_ppm',
            'baro_inhg': 'baro_inhg', 'o3_ppb': 'o3_ppb', 'no2_ppb': 'no2_ppb', 'so2_ppb': 'so2_ppb', 'ch2o_ppb': 'ch2o_ppb', 'voc_mgm3': 'voc_mgm3'
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
def insert_data_to_db(db: HotDurhamDB, wu_df: pd.DataFrame, tsi_df: pd.DataFrame):
    if wu_df.empty and tsi_df.empty:
        log.info("No data to insert.")
        return
    try:
        with db.engine.connect() as conn:
            sql = text("""
                SELECT d.deployment_pk, sm.native_sensor_id, sm.sensor_type
                FROM deployments d
                JOIN sensors_master sm ON d.sensor_fk = sm.sensor_pk
                WHERE d.end_date IS NULL;""")
            deployment_map_df = pd.read_sql(sql, conn)
    except Exception as e:
        log.error(f"Failed to fetch deployment map: {e}")
        return
    if deployment_map_df.empty:
        log.error("No active deployments found.")
        return
    all_long = []
    for df, typ in [(wu_df, 'WU'), (tsi_df, 'TSI')]:
        if df.empty:
            continue
        type_map = deployment_map_df[deployment_map_df.sensor_type == typ]
        merged = df.merge(type_map, on='native_sensor_id', how='inner')
        if merged.empty:
            log.warning(f"No {typ} rows matched deployments.")
            continue
        merged = merged.rename(columns={'deployment_pk': 'deployment_fk'})
        id_vars = ['timestamp', 'deployment_fk']
        value_vars = [c for c in merged.columns if c not in id_vars + ['native_sensor_id', 'sensor_type']]
        if not value_vars:
            continue
        long_df = pd.melt(merged, id_vars=id_vars, value_vars=value_vars, var_name='metric_name', value_name='value')
        all_long.append(long_df)
    if not all_long:
        log.warning("Nothing to insert after deployment matching.")
        return
    final = pd.concat(all_long, ignore_index=True)
    final = final.dropna(subset=['value']).drop_duplicates(subset=['timestamp', 'deployment_fk', 'metric_name'], keep='last')
    if final.empty:
        log.info("Final DataFrame empty after cleaning.")
        return
    try:
        db.insert_sensor_readings(final)
        log.info(f"Inserted/upserted {len(final)} sensor readings.")
    except Exception as e:
        log.error(f"DB insertion failed: {e}")
        raise


def check_db_connection(db: HotDurhamDB) -> bool:
    try:
        with db.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        log.error(f"Database connectivity check failed: {e}")
        return False


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
    if df.empty:
        log.info(f"Skip {src}: empty")
        return False
    ts_col = 'ts' if 'ts' in df.columns else ('timestamp' if 'timestamp' in df.columns else None)
    if not ts_col:
        log.warning(f"Skip {src}: no ts/timestamp column")
        return False
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

    if sink in ('db', 'both') or (sink == 'gcs' and not wrote_any):
        wu_db = wu_df if _has_ts(wu_df) else pd.DataFrame()
        tsi_db = tsi_df if _has_ts(tsi_df) else pd.DataFrame()
        if (not _has_ts(wu_df)) and not wu_df.empty:
            log.warning("WU missing ts/timestamp -> not inserting")
        if (not _has_ts(tsi_df)) and not tsi_df.empty:
            log.warning("TSI missing ts/timestamp -> not inserting")
        db = HotDurhamDB()
        if check_db_connection(db):
            insert_data_to_db(db, wu_db, tsi_db)
            if (not wu_db.empty):
                wrote_wu = True
            if (not tsi_db.empty):
                wrote_tsi = True
        else:
            log.critical("DB connection failed; skipped DB sink")
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
    try:
        from sqlalchemy import text as _bq_text  # reuse existing DB connection logic if available
        db = HotDurhamDB()
        with db.engine.connect() as conn:
            deployment_map_df = pd.read_sql(_bq_text("""
                SELECT d.deployment_pk, sm.native_sensor_id, sm.sensor_type
                FROM deployments d
                JOIN sensors_master sm ON d.sensor_fk = sm.sensor_pk
                WHERE d.end_date IS NULL
            """), conn)
    except Exception as e:
        log.error(f"Unable to fetch deployment mapping for staging tables: {e}")
        return
    if deployment_map_df.empty:
        log.error("Deployment map empty – cannot build BigQuery staging tables.")
        return

    def _prepare_long(df: pd.DataFrame, sensor_type: str) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=['timestamp','deployment_fk','metric_name','value'])
        type_map = deployment_map_df[deployment_map_df.sensor_type == sensor_type]
        if type_map.empty:
            log.warning(f"No active deployments for type {sensor_type} – skipping staging long melt")
            return pd.DataFrame(columns=['timestamp','deployment_fk','metric_name','value'])
        merged = df.merge(type_map, on='native_sensor_id', how='inner')
        if merged.empty:
            log.warning(f"No rows matched deployments for {sensor_type} – skipping")
            return pd.DataFrame(columns=['timestamp','deployment_fk','metric_name','value'])
        merged = merged.rename(columns={'deployment_pk': 'deployment_fk'})
        id_vars = ['timestamp', 'deployment_fk']
        value_vars = [c for c in merged.columns if c not in id_vars + ['native_sensor_id','sensor_type']]
        if not value_vars:
            return pd.DataFrame(columns=['timestamp','deployment_fk','metric_name','value'])
        long_df = pd.melt(merged, id_vars=id_vars, value_vars=value_vars, var_name='metric_name', value_name='value')
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
            day_df = long_df[long_df['date'] == d].drop(columns=['date'])
            table_name = f"staging_{source_label.lower()}_{d.strftime('%Y%m%d')}"
            fq = f"{client.project}.{dataset}.{table_name}"
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
            job_config = bigquery.LoadJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE, schema=schema)
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
    run_id = uuid.uuid4().hex
    run_started = datetime.utcnow()
    start_str, end_str = _normalize_dates(start_date, end_date)
    wu_raw, tsi_raw = await _fetch_raw(start_str, end_str, config.source, config.aggregate, config.agg_interval)
    wu_df, tsi_df = _clean(wu_raw, tsi_raw)

    if config.is_dry_run:
        log.info("DRY RUN: showing head only")
        _maybe_show_samples(wu_df, tsi_df)
        return

    wrote_wu, wrote_tsi = _sink_data(wu_df, tsi_df, config.sink, config.aggregate, config.agg_interval)
    # Always attempt staging table write (opt-out via DISABLE_BQ_STAGING=1)
    try:
        _write_bq_staging(wu_df, tsi_df, start_str, end_str)
    except Exception:
        log.error("Unhandled error while writing BigQuery staging tables", exc_info=True)
    if not (wrote_wu or wrote_tsi):
        log.warning("No data written to any sink.")

    _log_run_metadata(
        run_id, start_str, end_str, run_started,
        wu_raw, tsi_raw, wu_df, tsi_df,
        wrote_wu, wrote_tsi,
        config.aggregate, config.agg_interval, config.sink, config.source
    )
    log.info("Collection complete")


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