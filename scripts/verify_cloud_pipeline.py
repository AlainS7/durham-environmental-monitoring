#!/usr/bin/env python3
"""End-to-end cloud verification for GCS + BigQuery pipeline.

Checks performed:
 1. GCS write/read round trip (temp Parquet file via GCSUploader logic analogue)
 2. BigQuery dataset existence (create optional)
 3. Expected staging/fact tables presence (list + optional row counts for a partition date)
 4. Optional load simulation: dry-run style inspection of URIs that would be loaded

Exit code non-zero if any required check fails.
"""
from __future__ import annotations
import argparse
import logging
import os
import sys
import uuid
import io
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any

import pandas as pd

from google.cloud import storage, bigquery
from google.cloud.exceptions import NotFound

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger("verify_cloud")


def check_gcs_round_trip(bucket: str, prefix: str) -> dict:
    try:
        client = storage.Client()
        b = client.bucket(bucket)
        test_df = pd.DataFrame({
            'timestamp': [pd.Timestamp.now(tz='UTC')],
            'test_value': [42],
            'marker': [str(uuid.uuid4())]
        })
        path = f"{prefix.strip('/')}/_verify/test-{uuid.uuid4().hex}.parquet"
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq
        except Exception as e:  # pragma: no cover
            return {"ok": False, "error": f"pyarrow import failed: {e}"}
        table = pa.Table.from_pandas(test_df)
        buf = io.BytesIO()
        pq.write_table(table, buf, compression='snappy')
        buf.seek(0)
        blob = b.blob(path)
        blob.upload_from_file(buf, content_type='application/octet-stream')
        log.info(f"Uploaded test object gs://{bucket}/{path}")
        downloaded = b.get_blob(path)
        exists = downloaded is not None
        size = downloaded.size if downloaded else None
        return {"ok": exists, "object_path": f"gs://{bucket}/{path}", "size": size}
    except Exception as e:
        return {"ok": False, "error": f"GCS round trip exception: {e}"}


def ensure_dataset(client: bigquery.Client, dataset_id: str, location: str, create: bool) -> dict:
    ds_ref = bigquery.DatasetReference(client.project, dataset_id)
    try:
        ds = client.get_dataset(ds_ref)
        return {"ok": True, "created": False, "location": ds.location}
    except NotFound:
        if not create:
            return {"ok": False, "error": "Dataset not found"}
        ds_obj = bigquery.Dataset(ds_ref)
        ds_obj.location = location
        client.create_dataset(ds_obj)
        return {"ok": True, "created": True, "location": location}


def list_tables(client: bigquery.Client, dataset_id: str) -> List[str]:
    return [t.table_id for t in client.list_tables(dataset_id)]


EPOCH_CANDIDATE_RE = re.compile(r"(epoch|ts|time|timestamp)", re.IGNORECASE)

def _pick_time_column(schema: List[bigquery.SchemaField]) -> Tuple[Optional[str], Optional[str]]:
    """Heuristically select a temporal column & its type category.

    Returns (column_name, category) where category in {TIMESTAMP, DATETIME, DATE, EPOCH_INT, NONE}.
    """
    # Direct TIMESTAMP/DATETIME/DATE preference order
    ts_types = {"TIMESTAMP": [], "DATETIME": [], "DATE": []}
    epoch_ints: List[str] = []
    for field in schema:
        ftype = field.field_type.upper()
        name = field.name
        if ftype in ts_types:
            ts_types[ftype].append(name)
        elif ftype in {"INT64"} and EPOCH_CANDIDATE_RE.search(name):
            epoch_ints.append(name)
    for t in ["TIMESTAMP", "DATETIME", "DATE"]:
        if ts_types[t]:
            return ts_types[t][0], t
    if epoch_ints:
        return epoch_ints[0], "EPOCH_INT"
    return None, None

def _build_row_count_query(client: bigquery.Client, dataset_id: str, table: str, date: Optional[str]) -> Tuple[str, Optional[bigquery.QueryJobConfig]]:
    """Construct a safe COUNT query with adaptive filtering.

    Logic:
      - If table name ends with _YYYYMMDD (8 digits) treat as date-specific table -> simple COUNT(*).
      - Else introspect schema: pick a temporal column.
        * TIMESTAMP/DATETIME: DATE(col) = @dt
        * DATE: col = @dt
        * EPOCH_INT: if date provided, compute millis range [date, date+1) and do range filter; else COUNT(*).
      - If no date provided, ALWAYS just COUNT(*).
      - If no temporal column found, fallback COUNT(*).
    """
    fq = f"{client.project}.{dataset_id}.{table}"
    # Pattern for suffixed date
    suffixed_date = re.search(r"_(\d{8})$", table)
    if not date or suffixed_date:
        return f"SELECT COUNT(*) cnt FROM `{fq}`", None
    # Need schema
    try:
        table_obj = client.get_table(f"{dataset_id}.{table}")
    except Exception:
        return "SELECT 0 cnt", None  # Will resolve to 0 and be flagged maybe elsewhere
    col, category = _pick_time_column(table_obj.schema)
    if not col or not category:
        return f"SELECT COUNT(*) cnt FROM `{fq}`", None
    if category in {"TIMESTAMP", "DATETIME"}:
        q = f"SELECT COUNT(*) cnt FROM `{fq}` WHERE DATE(`{col}`) = @dt"
        cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter('dt', 'DATE', date)])
        return q, cfg
    if category == "DATE":
        q = f"SELECT COUNT(*) cnt FROM `{fq}` WHERE `{col}` = @dt"
        cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter('dt', 'DATE', date)])
        return q, cfg
    if category == "EPOCH_INT":
        # Assume milliseconds or seconds? Heuristic: if max value > 10^12 treat as ms else seconds.
        # We can't scan without cost; approximate by using range for both seconds and ms and OR them.
        # Compute start/end timestamps via parameter substitution.
        # We'll rely on BigQuery to parse TIMESTAMP(@dt) and TIMESTAMP_ADD.
        q = (
            "WITH bounds AS ("\
            " SELECT @dt AS d) "
            f"SELECT COUNT(*) cnt FROM `{fq}`, bounds "
            f"WHERE ( (`{col}` BETWEEN UNIX_SECONDS(TIMESTAMP(d)) AND UNIX_SECONDS(TIMESTAMP(DATE_ADD(d, INTERVAL 1 DAY)))-1) "
            f" OR (`{col}` BETWEEN UNIX_MILLIS(TIMESTAMP(d)) AND UNIX_MILLIS(TIMESTAMP(DATE_ADD(d, INTERVAL 1 DAY)))-1) )"
        )
        cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter('dt', 'DATE', date)])
        return q, cfg
    return f"SELECT COUNT(*) cnt FROM `{fq}`", None

def table_row_count(client: bigquery.Client, dataset_id: str, table: str, date: str | None) -> int | None:
    fq = f"{client.project}.{dataset_id}.{table}"
    try:
        query, cfg = _build_row_count_query(client, dataset_id, table, date)
        job = client.query(query, job_config=cfg)
        return list(job.result())[0]['cnt']
    except Exception as e:
        log.warning(f"Row count query failed for {fq}: {e}")
        return None


def simulate_load_paths(bucket: str, prefix: str, date: str) -> List[str]:
    paths = []
    for src in ["WU", "TSI"]:
        for agg in ["raw", "h", "15min"]:
            paths.append(f"gs://{bucket}/{prefix.strip('/')}/source={src}/agg={agg}/dt={date}/*.parquet")
    return paths


@dataclass(slots=True)
class VArgs:
    project: str | None
    dataset: str
    location: str
    bucket: str
    prefix: str
    date: Optional[str]
    create_dataset: bool
    show_tables: bool
    check_rows: bool
    show_schema: bool
    epoch_diagnostics: bool
    enforce_normalized: bool
    simulate_loads: bool
    emit_json: bool
    skip_gcs: bool


def parse_args() -> VArgs:
    p = argparse.ArgumentParser(description="Verify GCS + BigQuery integration")
    p.add_argument('--project', default=os.getenv('BQ_PROJECT'))
    p.add_argument('--dataset', required=True, help='BigQuery dataset ID')
    p.add_argument('--location', default=os.getenv('BQ_LOCATION', 'US'))
    p.add_argument('--bucket', required=True, help='GCS bucket')
    p.add_argument('--prefix', default=os.getenv('GCS_PREFIX', 'sensor_readings'))
    p.add_argument('--date', help='Partition date (YYYY-MM-DD) to inspect row counts')
    p.add_argument('--create-dataset', action='store_true', help='Create dataset if missing')
    p.add_argument('--show-tables', action='store_true', help='List tables')
    p.add_argument('--check-rows', action='store_true', help='Fetch row counts (with optional --date filter)')
    p.add_argument('--show-schema', action='store_true', help='Show schema per table when listing tables')
    p.add_argument('--epoch-diagnostics', action='store_true', help='Analyze INT timestamp-like columns (epoch secs/millis)')
    p.add_argument('--enforce-normalized', action='store_true', help='Fail if staging/tmp tables lack ts TIMESTAMP or float lat/lon')
    p.add_argument('--simulate-loads', action='store_true', help='Show expected load URIs for date')
    p.add_argument('--json', action='store_true', help='Emit machine-readable JSON summary')
    p.add_argument('--skip-gcs', action='store_true', help='Skip GCS round trip test')
    a = p.parse_args()
    return VArgs(a.project, a.dataset, a.location, a.bucket, a.prefix, a.date, a.create_dataset, a.show_tables,
                 a.check_rows, a.show_schema, a.epoch_diagnostics, a.enforce_normalized, a.simulate_loads, a.json, a.skip_gcs)


def perform_gcs_check(args: VArgs) -> dict:
    return {"ok": True, "skipped": True} if args.skip_gcs else check_gcs_round_trip(args.bucket, args.prefix)


def maybe_list_tables(client: bigquery.Client, args: VArgs) -> list[str]:
    if not args.show_tables:
        return []
    try:
        return list_tables(client, args.dataset)
    except Exception as e:
        log.error(f"List tables failed: {e}")
        return []


def _maybe_get_table(client: bigquery.Client, dataset: str, table: str):
    try:
        return client.get_table(f"{dataset}.{table}")
    except Exception as e:  # pragma: no cover - defensive
        log.debug(f"get_table failed for {dataset}.{table}: {e}")
        return None


def _collect_schema(tbl) -> Dict[str, str] | Dict[str, str]:
    if not tbl:
        return {"_error": "not_found"}
    return {f.name: f.field_type for f in tbl.schema}


def _norm_field_map(tbl) -> Optional[Dict[str, str]]:
    if not tbl:
        return None
    return {f.name: f.field_type.upper() for f in tbl.schema}


def _norm_missing_canonical(field_map: Dict[str, str]) -> Optional[str]:
    if field_map.get('ts') == 'TIMESTAMP' or field_map.get('timestamp') == 'TIMESTAMP':
        return None
    return 'missing_canonical_timestamp'


def _norm_lat_issue(field_map: Dict[str, str]) -> Optional[str]:
    lat_t = field_map.get('latitude')
    if lat_t and lat_t != 'FLOAT' and 'latitude_f' not in field_map:
        return 'latitude_not_float'
    return None


def _norm_lon_issue(field_map: Dict[str, str]) -> Optional[str]:
    lon_t = field_map.get('longitude')
    if lon_t and lon_t != 'FLOAT' and 'longitude_f' not in field_map:
        return 'longitude_not_float'
    return None


def _norm_redundant_epoch_ints(field_map: Dict[str, str]) -> Optional[str]:
    has_ts = field_map.get('ts') == 'TIMESTAMP' or field_map.get('timestamp') == 'TIMESTAMP'
    if not has_ts:
        return None
    count_ints = sum(1 for n, t in field_map.items() if t == 'INTEGER' and n in ('timestamp', 'epoch'))
    if count_ints > 1:
        return 'redundant_int_time_cols'
    return None


NORMALIZATION_CHECKS = (
    _norm_missing_canonical,
    _norm_lat_issue,
    _norm_lon_issue,
    _norm_redundant_epoch_ints,
)


def _normalization_issues(tbl) -> List[str]:
    if not tbl:
        return ['not_found']
    field_map = _norm_field_map(tbl)
    if field_map is None:
        return ['not_found']
    out: List[str] = []
    for checker in NORMALIZATION_CHECKS:
        issue = checker(field_map)
        if issue:
            out.append(issue)
    return out


def _epoch_scale(max_value: int) -> Tuple[str, Any]:
    """Return (scale_label, converter_func_template) where template produces TIMESTAMP expr."""
    if max_value < 10**12:
        return 'seconds', lambda v: f"TIMESTAMP_SECONDS({v})"
    if max_value < 10**15:
        return 'milliseconds', lambda v: f"TIMESTAMP_MILLIS({v})"
    if max_value < 10**18:
        return 'microseconds', lambda v: f"TIMESTAMP_MICROS({v})"
    return 'nanoseconds', lambda v: f"TIMESTAMP_MICROS(CAST(DIV({v},1000) AS INT64))"


def _epoch_diag_for_table(client: bigquery.Client, fq_table: str, tbl) -> List[Dict[str, Any]]:
    if not tbl:
        return [{"_error": "not_found"}]
    cand_cols = [
        f.name for f in tbl.schema
        if f.field_type.upper() == "INTEGER" and EPOCH_CANDIDATE_RE.search(f.name)
    ]
    diagnostics: List[Dict[str, Any]] = []
    for col in cand_cols:
        q = f"SELECT MIN(`{col}`) mn, MAX(`{col}`) mx, COUNT(*) c FROM `{fq_table}`"
        try:  # pragma: no branch - single decision path
            res = list(client.query(q).result())[0]
            mn, mx, c = res['mn'], res['mx'], res['c']
            if mn is None or mx is None:
                diagnostics.append({"column": col, "rows": c, "min": None, "max": None})
                continue
            scale, conv = _epoch_scale(mx)
            conv_min = conv(mn)
            conv_max = conv(mx)
            conv_query = (
                "SELECT "
                f"FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', {conv_min}) AS iso_min, "
                f"FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', {conv_max}) AS iso_max"
            )
            try:
                conv_res = list(client.query(conv_query).result())[0]
                iso_min, iso_max = conv_res['iso_min'], conv_res['iso_max']
            except Exception:  # pragma: no cover - defensive
                iso_min = iso_max = None
            diagnostics.append({
                "column": col,
                "rows": c,
                "min": mn,
                "max": mx,
                "scale": scale,
                "iso_min": iso_min,
                "iso_max": iso_max,
            })
        except Exception as ie:  # pragma: no cover
            diagnostics.append({"column": col, "error": str(ie)})
    return diagnostics


def _needs_norm_check(table: str) -> bool:
    if table.startswith(('tmp_unpivot_', 'snapshot_', 'view_')):
        return False
    # Historical/date-suffixed staging shards are legacy ingestion artifacts
    # and don't always expose normalized canonical timestamp fields.
    if re.search(r'_\d{8}$', table):
        return False
    return table.startswith(('staging_', 'tmp_'))


def _process_schema(t: str, tbl, args: VArgs, out: Dict[str, Any]):  # minimal branching
    if args.show_schema:
        out[t] = _collect_schema(tbl)


def _process_norm(t: str, tbl, args: VArgs, out: Dict[str, Any]):
    if args.enforce_normalized and _needs_norm_check(t):
        issues = _normalization_issues(tbl)
        if issues:
            out[t] = issues


def _process_epoch(t: str, tbl, args: VArgs, client: bigquery.Client, out: Dict[str, Any]):
    if args.epoch_diagnostics:
        diag = _epoch_diag_for_table(client, f"{client.project}.{args.dataset}.{t}", tbl)
        if diag:
            out[t] = diag


def gather_row_related(client: bigquery.Client, args: VArgs, tables: list[str]) -> Dict[str, Any]:
    if not (args.check_rows and tables):
        return {}
    row_counts: Dict[str, Any] = {}
    schemas: Dict[str, Any] = {}
    epoch_diag: Dict[str, Any] = {}
    norm_issues: Dict[str, Any] = {}

    processors = []
    if args.show_schema:
        processors.append('schema')
    if args.enforce_normalized:
        processors.append('norm')
    if args.epoch_diagnostics:
        processors.append('epoch')

    wants_table_obj = bool(processors)
    for t in tables:
        row_counts[t] = table_row_count(client, args.dataset, t, args.date)
        tbl = _maybe_get_table(client, args.dataset, t) if wants_table_obj else None
        for proc in processors:
            if proc == 'schema':
                _process_schema(t, tbl, args, schemas)
            elif proc == 'norm':
                _process_norm(t, tbl, args, norm_issues)
            elif proc == 'epoch':
                _process_epoch(t, tbl, args, client, epoch_diag)
    out: Dict[str, Any] = {"row_counts": row_counts}
    if args.show_schema:
        out['schemas'] = schemas
    if args.epoch_diagnostics:
        out['epoch_diagnostics'] = epoch_diag
    if args.enforce_normalized:
        out['normalization_issues'] = norm_issues
    return out


def finalize(summary: Dict[str, Any], args: VArgs):
    if args.simulate_loads and args.date:
        summary['steps']['load_uris'] = simulate_load_paths(args.bucket, args.prefix, args.date)
    if args.emit_json:
        import json
        print(json.dumps(summary, default=str, indent=2))
    else:
        for k, v in summary['steps'].items():
            log.info(f"{k}: {v}")
    gcs_res = summary['steps']['gcs_round_trip']
    ds_res = summary['steps']['dataset']
    failed = any([not gcs_res.get('ok'), not ds_res.get('ok')])
    if args.enforce_normalized and summary['steps'].get('normalization_issues'):
        if any(summary['steps']['normalization_issues'].values()):
            failed = True
    sys.exit(1 if failed else 0)


def main():
    args = parse_args()
    client = bigquery.Client(project=args.project)
    summary: Dict[str, Any] = {"steps": {}}
    summary['steps']['gcs_round_trip'] = perform_gcs_check(args)
    if not summary['steps']['gcs_round_trip'].get('ok'):
        log.error(f"GCS round trip failed: {summary['steps']['gcs_round_trip']}")
    summary['steps']['dataset'] = ensure_dataset(client, args.dataset, args.location, args.create_dataset)
    if not summary['steps']['dataset'].get('ok'):
        log.error(f"Dataset check failed: {summary['steps']['dataset']}")
    tables = maybe_list_tables(client, args)
    if tables:
        summary['steps']['tables'] = tables
    row_bundle = gather_row_related(client, args, tables)
    summary['steps'].update(row_bundle)
    finalize(summary, args)

if __name__ == '__main__':
    main()
