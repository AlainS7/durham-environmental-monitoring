# NIFC Fire Data Setup

This document adds National Interagency Fire Center (NIFC) wildfire perimeter data to BigQuery and Grafana.

## What This Adds

Running `scripts/ingest_nifc_fire_perimeters.py` creates and refreshes:

- `sensors_shared.nifc_fire_perimeters_raw` (append-only history, deduplicated by `record_hash`)
- `sensors_shared.nifc_fire_perimeters_current` (latest record per incident, incrementally upserted)
- `sensors_shared.nifc_fire_perimeters_map` (map-ready view)
- `sensors_shared.nifc_fire_weather_daily` (weather/fire proximity correlations within radius)
- `sensors_shared.nifc_fire_weather_nearest_daily` (nearest-station correlation, always populated)

The ingestion path uses a temporary staging table + `MERGE` statements so each run only applies deltas. This avoids full-table rebuild scans on every schedule and keeps BigQuery costs predictable as history grows.

## Data Source

### Endpoint (canonical)

- **Layer URL (this repo):**  
  `https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_Current/FeatureServer/0`
- **HTTPS only.** No API key required at this time.

### Authority and verification

- **ArcGIS Online item:** [WFIGS Current Interagency Fire Perimeters](https://www.arcgis.com/home/item.html?id=d1c32af3212341869b3c810f1a215824) (`serviceItemId` matches the FeatureServer metadata).
- **Owner:** `NIFC_Authoritative` (National Interagency Fire Center organization on ArcGIS Online).
- **Program:** WFIGS (Wildland Fire Interagency Geospatial Services), described on that item page; includes IRWIN-related inclusion rules and refresh cadence.

Before changing the layer URL in code or CI, confirm the new URL on that item (or its successor) so you do not follow an unofficial mirror.

### Safe use in this project

- **Ingestion:** `DEFAULT_LAYER_URL` / `NIFC_FEATURE_LAYER_URL` should stay aligned with the item above; ingest stores `source_layer_url` on rows for traceability.
- **BigQuery `incident_id`:** Comes from IRWIN attribute `attr_IrwinID` (see ingest script). Treat it as the IRWIN incident identifier, not as a guaranteed path segment for third-party websites unless you validate a documented URL pattern.
- **Grafana or docs:** Add **data links** only to URLs you can defend—fields supplied by the source, official portals with documented ID mapping, or your own dashboards. Avoid inventing InciWeb or other URLs from UUIDs alone.

### Disclaimer

Use of federal/interagency geospatial products is subject to the **license and disclaimer** on the ArcGIS item (accuracy, timeliness, not a legal document). Operators remain responsible for appropriate use; see the item’s **License / Terms** section.

## One-Time Requirements

- BigQuery dataset exists: `sensors_shared`
- Service account used by automation has:
  - `roles/bigquery.dataEditor` on dataset `sensors_shared`
  - `roles/bigquery.jobUser` on project `durham-weather-466502`
- Weather daily enriched view exists in production dataset: `sensors.sensor_readings_daily_enriched`

## Run Manually

```bash
python scripts/ingest_nifc_fire_perimeters.py \
  --project durham-weather-466502 \
  --dataset sensors_shared \
  --weather-dataset sensors \
  --execute
```

Useful tuning flags:

- `--lookback-hours 12` to avoid missing near-watermark updates
- `--page-size 1000` (increase up to about 2000 if needed)
- `--max-pages 1` for quick debug runs
- `--radius-meters 50000` for correlation view distance

## Automated Schedule

Workflow file: `.github/workflows/nifc-fire-ingest.yml`

- Schedule: every 20 minutes
- Manual trigger available with input overrides
- Uses existing workload identity auth secrets:
  - `GCP_WORKLOAD_IDENTITY_PROVIDER`
  - `GCP_VERIFIER_SA`

## Validation Queries

Fire freshness:

```sql
SELECT
  MAX(source_modified_at) AS max_fire_update_utc,
  TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(source_modified_at), MINUTE) AS lag_minutes
FROM `durham-weather-466502.sensors_shared.nifc_fire_perimeters_current`;
```

Map view row count:

```sql
SELECT COUNT(*) AS incidents
FROM `durham-weather-466502.sensors_shared.nifc_fire_perimeters_map`;
```

Daily weather/fire proximity rows:

```sql
SELECT
  day_date,
  COUNT(*) AS rows_cnt,
  COUNT(DISTINCT incident_id) AS incidents,
  COUNT(DISTINCT native_sensor_id) AS sensors
FROM `durham-weather-466502.sensors_shared.nifc_fire_weather_daily`
WHERE day_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
GROUP BY day_date
ORDER BY day_date DESC;
```

Nearest-station fallback rows:

```sql
SELECT
  day_date,
  COUNT(*) AS rows_cnt,
  COUNT(DISTINCT incident_id) AS incidents,
  APPROX_QUANTILES(distance_meters, 5)[OFFSET(2)] AS median_distance_m
FROM `durham-weather-466502.sensors_shared.nifc_fire_weather_nearest_daily`
WHERE day_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 14 DAY)
GROUP BY day_date
ORDER BY day_date DESC;
```

## Suggested Grafana Panels

- **Research dashboard:** `dashboard/research_dashboard_enhanced.json` (Grafana Dashboard CRD) includes a geomap row **NIFC wildfire perimeters** querying `nifc_fire_perimeters_map` (centroid markers, `source_modified_at` time filter).
- **Fire perimeter map layer:** query `nifc_fire_perimeters_map` and plot by `geog` or centroid fields.
- **Nearby weather metrics:** chart `nifc_fire_weather_daily` filtered by `incident_id`, with metric split by `metric_name`.
- **Nearest weather fallback:** use `nifc_fire_weather_nearest_daily` when there are no local fires near Durham sensors.
- **Containment vs weather timeline:** combine `percent_contained` from fire current table with humidity/wind/temperature from proximity view.
