#!/usr/bin/env bash
# Targeted TSI backfill for explicit native device IDs (e.g. AA-16..AA-20).
#
# Usage:
#   bash scripts/backfill_tsi_device_ids.sh
#   bash scripts/backfill_tsi_device_ids.sh --start 2026-05-14 --end 2026-05-20
#   TSI_DEVICE_IDS="id1,id2" bash scripts/backfill_tsi_device_ids.sh --local
#   bash scripts/backfill_tsi_device_ids.sh --cloud   # Cloud Run (deploy image with --tsi-device-ids first)
#
set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-durham-weather-466502}"
BQ_DATASET="${BQ_DATASET:-sensors}"
BQ_SHARED="${BQ_SHARED_DATASET:-sensors_shared}"
GCS_BUCKET="${GCS_BUCKET:-sensor-data-to-bigquery}"
GCS_PREFIX="${GCS_PREFIX:-raw}"
JOB_NAME="${JOB_NAME:-weather-data-uploader}"
REGION="${REGION:-us-east1}"

# AA-16 .. AA-20 (Air Assure) native TSI device IDs
DEFAULT_DEVICE_IDS="d3ruqfpc660c73e6t89g,d3ruqu1c660c73e6t8a0,d7kj0nb8c00s73di18r0,d7kj16j8c00s73di18rg,d7kj0ovtna1s73fe1uq0"
TSI_DEVICE_IDS="${TSI_DEVICE_IDS:-$DEFAULT_DEVICE_IDS}"
MODE="local"
START_DATE="2026-05-14"
END_DATE=""

usage() {
  cat >&2 <<EOF
Usage: $(basename "$0") [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--local|--cloud]
  --start   First day (default: 2026-05-14, AA-16 map effective date)
  --end     Last day inclusive (default: yesterday UTC)
  --local   Run collector on this machine (default)
  --cloud   Run via gcloud run jobs execute (requires deployed job image)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --start) START_DATE="$2"; shift 2 ;;
    --end) END_DATE="$2"; shift 2 ;;
    --local) MODE="local"; shift ;;
    --cloud) MODE="cloud"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$END_DATE" ]]; then
  END_DATE=$(date -u -d 'yesterday' +%F 2>/dev/null || date -u -v-1d +%F)
fi

echo "=============================================="
echo "TSI targeted backfill"
echo "  devices: $TSI_DEVICE_IDS"
echo "  range:   $START_DATE -> $END_DATE"
echo "  mode:    $MODE"
echo "=============================================="

echo ""
echo "Current BigQuery row counts (sensors_shared.tsi_raw_materialized):"
bq query --nouse_legacy_sql --project_id="$PROJECT_ID" "
SELECT m.sensor_id, COUNT(*) AS row_count, MIN(DATE(ts)) AS first_day, MAX(DATE(ts)) AS last_day
FROM \`${PROJECT_ID}.${BQ_SHARED}.tsi_raw_materialized\` t
JOIN \`${PROJECT_ID}.${BQ_SHARED}.sensor_id_map\` m
  ON CAST(t.native_sensor_id AS STRING) = m.native_sensor_id
WHERE CAST(t.native_sensor_id AS STRING) IN UNNEST(SPLIT('${TSI_DEVICE_IDS}', ','))
GROUP BY m.sensor_id
ORDER BY m.sensor_id
" || true

run_local_day() {
  local day="$1"
  echo ""
  echo "[$day] Local TSI collect..."
  export PYTHONPATH=.
  export PROJECT_ID="$PROJECT_ID"
  export SOURCE=tsi
  export BQ_PROJECT="$PROJECT_ID"
  export TSI_CREDS_SECRET_ID="${TSI_CREDS_SECRET_ID:-tsi_creds}"
  export BQ_DATASET="$BQ_DATASET"
  export GCS_BUCKET="$GCS_BUCKET"
  export GCS_PREFIX="$GCS_PREFIX"
  export GCS_FORCE_OVERWRITE=1
  uv run python src/data_collection/daily_data_collector.py \
    --start "$day" \
    --end "$day" \
    --source tsi \
    --sink both \
    --tsi-device-ids "$TSI_DEVICE_IDS"
}

run_cloud_day() {
  local day="$1"
  echo ""
  echo "[$day] Cloud Run TSI collect..."
  gcloud run jobs execute "$JOB_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --args="src/data_collection/daily_data_collector.py" \
    --args="--start=$day" \
    --args="--end=$day" \
    --args="--source=tsi" \
    --args="--sink=both" \
    --args="--tsi-device-ids=$TSI_DEVICE_IDS" \
    --update-env-vars="TSI_DEVICE_IDS=${TSI_DEVICE_IDS}" \
    --wait
}

cur="$START_DATE"
while [[ "$cur" < "$END_DATE" || "$cur" == "$END_DATE" ]]; do
  if [[ "$MODE" == "local" ]]; then
    run_local_day "$cur"
  else
    run_cloud_day "$cur"
  fi
  cur=$(uv run python -c "import datetime as dt,sys; d=dt.date.fromisoformat(sys.argv[1]); print((d+dt.timedelta(days=1)).isoformat())" "$cur")
done

echo ""
echo "Publishing staging -> GCS (force) for days that already have AA staging rows ..."
uv run python scripts/publish_staging_tsi_to_gcs.py --start "$START_DATE" --end "$END_DATE"

echo ""
echo "Materializing TSI partitions $START_DATE -> $END_DATE ..."
uv run python scripts/materialize_partitions.py \
  --project "$PROJECT_ID" \
  --dataset "$BQ_DATASET" \
  --start "$START_DATE" \
  --end "$END_DATE" \
  --sources TSI \
  --bucket "$GCS_BUCKET" \
  --prefix "${GCS_PREFIX%/}" \
  --execute

echo ""
echo "Refreshing sensors_shared.tsi_raw_materialized ..."
bash scripts/refresh_tsi_shared.sh

echo ""
echo "Post-backfill counts:"
bq query --nouse_legacy_sql --project_id="$PROJECT_ID" "
SELECT m.sensor_id, COUNT(*) AS row_count, MIN(DATE(ts)) AS first_day, MAX(DATE(ts)) AS last_day
FROM \`${PROJECT_ID}.${BQ_SHARED}.tsi_raw_materialized\` t
JOIN \`${PROJECT_ID}.${BQ_SHARED}.sensor_id_map\` m
  ON CAST(t.native_sensor_id AS STRING) = m.native_sensor_id
WHERE CAST(t.native_sensor_id AS STRING) IN UNNEST(SPLIT('${TSI_DEVICE_IDS}', ','))
GROUP BY m.sensor_id
ORDER BY m.sensor_id
"

echo ""
echo "Done. If row_count still 0, check TSI API returns telemetry for these devices on each day."
