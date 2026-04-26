#!/usr/bin/env python3
"""Ingest NIFC wildfire perimeters into BigQuery for Grafana analysis.

This script pulls fire perimeters from the public ArcGIS FeatureServer endpoint,
stores an append-only raw history table, materializes a "current" table keyed by
incident ID, and refreshes map/correlation views.

Usage:
  python scripts/ingest_nifc_fire_perimeters.py \
    --project durham-weather-466502 \
    --dataset sensors_shared \
    --execute
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import logging
from typing import Any

import requests
from google.cloud import bigquery
from google.cloud.exceptions import NotFound


DEFAULT_LAYER_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Interagency_Perimeters_Current/FeatureServer/0"
)
RAW_TABLE_NAME = "nifc_fire_perimeters_raw"
CURRENT_TABLE_NAME = "nifc_fire_perimeters_current"
MAP_VIEW_NAME = "nifc_fire_perimeters_map"
CORRELATION_VIEW_NAME = "nifc_fire_weather_daily"
NEAREST_CORRELATION_VIEW_NAME = "nifc_fire_weather_nearest_daily"

OUT_FIELDS = [
    "OBJECTID",
    "poly_IncidentName",
    "poly_Acres_AutoCalc",
    "poly_GISAcres",
    "attr_IrwinID",
    "attr_IncidentTypeCategory",
    "attr_IncidentTypeKind",
    "attr_FireDiscoveryDateTime",
    "attr_ModifiedOnDateTime_dt",
    "attr_PercentContained",
    "attr_IncidentSize",
    "attr_GACC",
    "attr_POOState",
]

log = logging.getLogger("ingest_nifc_fire_perimeters")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        default="durham-weather-466502",
        help="GCP project ID",
    )
    parser.add_argument(
        "--dataset",
        default="sensors_shared",
        help="BigQuery dataset for fire tables/views",
    )
    parser.add_argument(
        "--weather-dataset",
        default=None,
        help=(
            "Dataset containing sensor_readings_daily_enriched. "
            "Defaults to --dataset."
        ),
    )
    parser.add_argument(
        "--layer-url",
        default=DEFAULT_LAYER_URL,
        help="ArcGIS FeatureServer layer URL (without /query)",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=12,
        help="Safety window when resuming from watermark",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=1000,
        help="ArcGIS query page size (max typically 2000)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=0,
        help="Optional page cap for debugging (0 = no limit)",
    )
    parser.add_argument(
        "--radius-meters",
        type=int,
        default=50000,
        help="Distance for fire/weather correlation view",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute ingestion. Without this flag, only logs planned actions.",
    )
    return parser.parse_args()


def ensure_raw_table(client: bigquery.Client, project: str, dataset: str) -> None:
    table_id = f"{project}.{dataset}.{RAW_TABLE_NAME}"
    schema = [
        bigquery.SchemaField("ingest_ts", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("source_modified_at", "TIMESTAMP"),
        bigquery.SchemaField("incident_id", "STRING"),
        bigquery.SchemaField("incident_name", "STRING"),
        bigquery.SchemaField("incident_type_category", "STRING"),
        bigquery.SchemaField("incident_type_kind", "STRING"),
        bigquery.SchemaField("fire_discovery_at", "TIMESTAMP"),
        bigquery.SchemaField("percent_contained", "FLOAT64"),
        bigquery.SchemaField("incident_size_acres", "FLOAT64"),
        bigquery.SchemaField("perimeter_acres", "FLOAT64"),
        bigquery.SchemaField("gacc", "STRING"),
        bigquery.SchemaField("state", "STRING"),
        bigquery.SchemaField("source_object_id", "INT64"),
        bigquery.SchemaField("geometry_json", "STRING"),
        bigquery.SchemaField("properties_json", "STRING"),
        bigquery.SchemaField("source_layer_url", "STRING"),
        bigquery.SchemaField("record_hash", "STRING"),
    ]
    table = bigquery.Table(table_id, schema=schema)
    table.time_partitioning = bigquery.TimePartitioning(field="ingest_ts")
    table.clustering_fields = ["incident_id", "incident_type_category"]
    client.create_table(table, exists_ok=True)
    log.info("Ensured table exists: %s", table_id)


def get_watermark(
    client: bigquery.Client, project: str, dataset: str, lookback_hours: int
) -> dt.datetime:
    fallback = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)
    table_id = f"{project}.{dataset}.{RAW_TABLE_NAME}"
    try:
        client.get_table(table_id)
    except NotFound:
        return fallback

    sql = f"SELECT MAX(source_modified_at) AS max_ts FROM `{table_id}`"
    row = next(iter(client.query(sql).result()), None)
    max_ts = row["max_ts"] if row else None
    if max_ts is None:
        return fallback
    return max_ts - dt.timedelta(hours=max(lookback_hours, 0))


def format_arcgis_timestamp(ts: dt.datetime) -> str:
    return ts.astimezone(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def fetch_features(
    layer_url: str,
    watermark: dt.datetime,
    page_size: int,
    max_pages: int,
) -> list[dict[str, Any]]:
    where = f"attr_ModifiedOnDateTime_dt >= TIMESTAMP '{format_arcgis_timestamp(watermark)}'"
    params = {
        "where": where,
        "outFields": ",".join(OUT_FIELDS),
        "returnGeometry": "true",
        "f": "geojson",
        "orderByFields": "attr_ModifiedOnDateTime_dt ASC,OBJECTID ASC",
        "resultRecordCount": str(page_size),
    }
    query_url = f"{layer_url.rstrip('/')}/query"

    log.info("Fetching features with where clause: %s", where)
    all_features: list[dict[str, Any]] = []
    offset = 0
    page = 0
    session = requests.Session()

    while True:
        page += 1
        if max_pages > 0 and page > max_pages:
            break

        req_params = dict(params)
        req_params["resultOffset"] = str(offset)

        response = session.get(query_url, params=req_params, timeout=90)
        response.raise_for_status()
        payload = response.json()

        if payload.get("error"):
            raise RuntimeError(f"ArcGIS query error: {payload['error']}")

        batch = payload.get("features", [])
        if not batch:
            break

        all_features.extend(batch)
        offset += len(batch)
        log.info("Fetched page %d: %d features (total=%d)", page, len(batch), len(all_features))

        if len(batch) < page_size:
            break

    return all_features


def _to_iso(ts_ms: Any) -> str | None:
    if ts_ms is None:
        return None
    try:
        ts_int = int(ts_ms)
    except (TypeError, ValueError):
        return None
    parsed = dt.datetime.fromtimestamp(ts_int / 1000, tz=dt.timezone.utc)
    return parsed.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_incident_id(raw: Any) -> str | None:
    if raw is None:
        return None
    normalized = str(raw).strip().strip("{}").upper()
    return normalized or None


def build_rows(
    features: list[dict[str, Any]],
    layer_url: str,
    ingest_iso: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str | None, str | None, str]] = set()

    for feature in features:
        props = feature.get("properties", {})
        geometry = feature.get("geometry")

        geometry_json = json.dumps(geometry, separators=(",", ":")) if geometry else None
        properties_json = json.dumps(props, separators=(",", ":"), default=str)

        incident_id = _normalize_incident_id(props.get("attr_IrwinID"))
        source_modified = _to_iso(props.get("attr_ModifiedOnDateTime_dt"))

        raw_hash = "|".join(
            [incident_id or "", source_modified or "", geometry_json or "", properties_json]
        )
        record_hash = hashlib.sha256(raw_hash.encode("utf-8")).hexdigest()
        dedupe_key = (incident_id, source_modified, record_hash)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        rows.append(
            {
                "ingest_ts": ingest_iso,
                "source_modified_at": source_modified,
                "incident_id": incident_id,
                "incident_name": props.get("poly_IncidentName"),
                "incident_type_category": props.get("attr_IncidentTypeCategory"),
                "incident_type_kind": props.get("attr_IncidentTypeKind"),
                "fire_discovery_at": _to_iso(props.get("attr_FireDiscoveryDateTime")),
                "percent_contained": _to_float(props.get("attr_PercentContained")),
                "incident_size_acres": _to_float(props.get("attr_IncidentSize")),
                "perimeter_acres": _to_float(
                    props.get("poly_Acres_AutoCalc") or props.get("poly_GISAcres")
                ),
                "gacc": props.get("attr_GACC"),
                "state": props.get("attr_POOState"),
                "source_object_id": props.get("OBJECTID"),
                "geometry_json": geometry_json,
                "properties_json": properties_json,
                "source_layer_url": layer_url,
                "record_hash": record_hash,
            }
        )

    return rows


def insert_raw_rows(
    client: bigquery.Client, project: str, dataset: str, rows: list[dict[str, Any]]
) -> int:
    if not rows:
        return 0

    table_id = f"{project}.{dataset}.{RAW_TABLE_NAME}"
    row_ids = [row["record_hash"] for row in rows]
    errors = client.insert_rows_json(table_id, rows, row_ids=row_ids)
    if errors:
        raise RuntimeError(f"Failed inserting NIFC rows: {errors[:3]}")
    return len(rows)


def refresh_current_table(client: bigquery.Client, project: str, dataset: str) -> None:
    raw_id = f"{project}.{dataset}.{RAW_TABLE_NAME}"
    current_id = f"{project}.{dataset}.{CURRENT_TABLE_NAME}"
    sql = f"""
CREATE OR REPLACE TABLE `{current_id}`
PARTITION BY DATE(snapshot_ts)
CLUSTER BY incident_id, incident_type_category AS
WITH ranked AS (
  SELECT
    ingest_ts AS snapshot_ts,
    source_modified_at,
    incident_id,
    incident_name,
    incident_type_category,
    incident_type_kind,
    fire_discovery_at,
    percent_contained,
    incident_size_acres,
    perimeter_acres,
    gacc,
    state,
    source_object_id,
    geometry_json,
    properties_json,
    source_layer_url,
    record_hash,
    ROW_NUMBER() OVER (
      PARTITION BY incident_id
      ORDER BY source_modified_at DESC, ingest_ts DESC
    ) AS rn
  FROM `{raw_id}`
  WHERE incident_id IS NOT NULL
),
latest AS (
  SELECT * EXCEPT(rn)
  FROM ranked
  WHERE rn = 1
),
with_geog AS (
  SELECT
    *,
    SAFE.ST_GEOGFROMGEOJSON(geometry_json) AS geog
  FROM latest
)
SELECT
  snapshot_ts,
  source_modified_at,
  incident_id,
  incident_name,
  incident_type_category,
  incident_type_kind,
  fire_discovery_at,
  percent_contained,
  incident_size_acres,
  perimeter_acres,
  gacc,
  state,
  source_object_id,
  geometry_json,
  properties_json,
  source_layer_url,
  record_hash,
  geog,
  CASE WHEN geog IS NULL THEN NULL ELSE ST_Y(ST_CENTROID(geog)) END AS centroid_latitude,
  CASE WHEN geog IS NULL THEN NULL ELSE ST_X(ST_CENTROID(geog)) END AS centroid_longitude
FROM with_geog
"""
    client.query(sql).result()
    log.info("Refreshed table: %s", current_id)


def resolve_weather_view(
    client: bigquery.Client, project: str, weather_dataset: str
) -> tuple[str, str]:
    """Return weather view ID and geog expression for proximity joins.

    Prefers the requested dataset. Falls back to `sensors` if the requested
    view lacks spatial columns.
    """
    candidate_datasets = [weather_dataset]
    if weather_dataset != "sensors":
        candidate_datasets.append("sensors")

    for candidate in candidate_datasets:
        view_id = f"{project}.{candidate}.sensor_readings_daily_enriched"
        try:
            client.get_table(view_id)
        except NotFound:
            continue

        col_sql = (
            f"SELECT column_name FROM `{project}.{candidate}.INFORMATION_SCHEMA.COLUMNS` "
            "WHERE table_name='sensor_readings_daily_enriched'"
        )
        cols = {row["column_name"] for row in client.query(col_sql).result()}

        if "geog" in cols:
            log.info("Using weather source %s with GEOGRAPHY column", view_id)
            return view_id, "w.geog"
        if {"latitude", "longitude"}.issubset(cols):
            log.info("Using weather source %s with latitude/longitude columns", view_id)
            return view_id, "ST_GEOGPOINT(w.longitude, w.latitude)"

        log.warning(
            "Weather source %s found but has no spatial columns; trying fallback",
            view_id,
        )

    raise RuntimeError(
        "Could not find a usable sensor_readings_daily_enriched view with geospatial columns. "
        f"Tried datasets: {candidate_datasets}"
    )


def refresh_views(
    client: bigquery.Client,
    project: str,
    dataset: str,
    weather_dataset: str,
    radius_meters: int,
) -> None:
    current_id = f"{project}.{dataset}.{CURRENT_TABLE_NAME}"
    map_view_id = f"{project}.{dataset}.{MAP_VIEW_NAME}"
    corr_view_id = f"{project}.{dataset}.{CORRELATION_VIEW_NAME}"
    nearest_corr_view_id = f"{project}.{dataset}.{NEAREST_CORRELATION_VIEW_NAME}"
    weather_view_id, weather_geog_expr = resolve_weather_view(
        client=client,
        project=project,
        weather_dataset=weather_dataset,
    )

    map_sql = f"""
CREATE OR REPLACE VIEW `{map_view_id}` AS
SELECT
  incident_id,
  incident_name,
  incident_type_category,
  incident_type_kind,
  fire_discovery_at,
  source_modified_at,
  percent_contained,
  incident_size_acres,
  perimeter_acres,
  gacc,
  state,
  centroid_latitude,
  centroid_longitude,
  geog
FROM `{current_id}`
"""

    corr_sql = f"""
CREATE OR REPLACE VIEW `{corr_view_id}` AS
WITH weather AS (
  SELECT
    w.day_ts,
    w.native_sensor_id,
    w.sensor_id,
    w.metric_name,
    w.avg_value,
    w.min_value,
    w.max_value,
    w.samples,
    {weather_geog_expr} AS sensor_geog
  FROM `{weather_view_id}` w
)
SELECT
  DATE(w.day_ts) AS day_date,
  f.incident_id,
  f.incident_name,
  f.incident_type_category,
  f.incident_type_kind,
  f.fire_discovery_at,
  f.source_modified_at AS fire_last_modified_at,
  f.percent_contained,
  f.perimeter_acres,
  f.gacc,
  f.state,
  w.native_sensor_id,
  w.sensor_id,
  w.metric_name,
  w.avg_value,
  w.min_value,
  w.max_value,
  w.samples,
  ST_DISTANCE(w.sensor_geog, f.geog) AS distance_meters
FROM `{current_id}` f
JOIN weather w
  ON f.geog IS NOT NULL
 AND w.sensor_geog IS NOT NULL
 AND ST_DWITHIN(w.sensor_geog, f.geog, {int(radius_meters)})
WHERE w.metric_name IN (
  'temperature',
  'humidity',
  'wind_speed_avg',
  'precip_total',
  'pm2_5'
)
"""
    nearest_corr_sql = f"""
CREATE OR REPLACE VIEW `{nearest_corr_view_id}` AS
WITH weather AS (
  SELECT
    w.day_ts,
    w.native_sensor_id,
    w.sensor_id,
    w.metric_name,
    w.avg_value,
    w.min_value,
    w.max_value,
    w.samples,
    {weather_geog_expr} AS sensor_geog
  FROM `{weather_view_id}` w
  WHERE w.metric_name IN (
    'temperature',
    'humidity',
    'wind_speed_avg',
    'precip_total',
    'pm2_5'
  )
),
fire AS (
  SELECT
    incident_id,
    incident_name,
    incident_type_category,
    incident_type_kind,
    fire_discovery_at,
    source_modified_at AS fire_last_modified_at,
    percent_contained,
    perimeter_acres,
    gacc,
    state,
    geog
  FROM `{current_id}`
  WHERE geog IS NOT NULL
),
paired AS (
  SELECT
    DATE(w.day_ts) AS day_date,
    f.incident_id,
    f.incident_name,
    f.incident_type_category,
    f.incident_type_kind,
    f.fire_discovery_at,
    f.fire_last_modified_at,
    f.percent_contained,
    f.perimeter_acres,
    f.gacc,
    f.state,
    w.native_sensor_id,
    w.sensor_id,
    w.metric_name,
    w.avg_value,
    w.min_value,
    w.max_value,
    w.samples,
    ST_DISTANCE(w.sensor_geog, f.geog) AS distance_meters,
    ROW_NUMBER() OVER (
      PARTITION BY DATE(w.day_ts), f.incident_id, w.metric_name
      ORDER BY ST_DISTANCE(w.sensor_geog, f.geog) ASC
    ) AS distance_rank
  FROM fire f
  JOIN weather w
    ON w.sensor_geog IS NOT NULL
)
SELECT
  day_date,
  incident_id,
  incident_name,
  incident_type_category,
  incident_type_kind,
  fire_discovery_at,
  fire_last_modified_at,
  percent_contained,
  perimeter_acres,
  gacc,
  state,
  native_sensor_id,
  sensor_id,
  metric_name,
  avg_value,
  min_value,
  max_value,
  samples,
  distance_meters
FROM paired
WHERE distance_rank = 1
"""
    client.query(map_sql).result()
    client.query(corr_sql).result()
    client.query(nearest_corr_sql).result()
    log.info(
        "Refreshed views: %s, %s, %s",
        map_view_id,
        corr_view_id,
        nearest_corr_view_id,
    )


def main() -> None:
    args = parse_args()
    weather_dataset = args.weather_dataset or args.dataset
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = bigquery.Client(project=args.project)
    ensure_raw_table(client, args.project, args.dataset)

    watermark = get_watermark(
        client=client,
        project=args.project,
        dataset=args.dataset,
        lookback_hours=args.lookback_hours,
    )
    features = fetch_features(
        layer_url=args.layer_url,
        watermark=watermark,
        page_size=args.page_size,
        max_pages=args.max_pages,
    )
    log.info("Fetched %d total features from NIFC", len(features))

    ingest_ts = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    rows = build_rows(features=features, layer_url=args.layer_url, ingest_iso=ingest_ts)
    log.info("Prepared %d deduplicated rows for ingestion", len(rows))

    if not args.execute:
        log.info("Dry run complete. Re-run with --execute to write data.")
        return

    inserted = insert_raw_rows(client, args.project, args.dataset, rows)
    log.info("Inserted %d rows into %s.%s.%s", inserted, args.project, args.dataset, RAW_TABLE_NAME)

    refresh_current_table(client, args.project, args.dataset)
    refresh_views(
        client=client,
        project=args.project,
        dataset=args.dataset,
        weather_dataset=weather_dataset,
        radius_meters=args.radius_meters,
    )
    log.info("NIFC ingestion complete.")


if __name__ == "__main__":
    main()
