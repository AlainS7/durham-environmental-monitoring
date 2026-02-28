#!/bin/bash
# Refresh TSI materialized table in sensors_shared dataset
# Run daily (e.g., after your daily staging job) to sync with sensors.tsi_raw_materialized
# Matches your current daily staging + weekly promotion workflow

set -euo pipefail

PROJECT_ID="${GCP_PROJECT_ID:-durham-weather-466502}"
LOCATION="US"

echo "[$(date)] Starting TSI materialized table refresh..."

bq --project_id="$PROJECT_ID" query --nouse_legacy_sql \
  "CREATE OR REPLACE TABLE \`$PROJECT_ID.sensors_shared.tsi_raw_materialized\` \
   PARTITION BY DATE(ts) \
   CLUSTER BY native_sensor_id AS \
   SELECT ts, cloud_account_id, native_sensor_id, model, serial, \
          latitude, longitude, is_indoor, is_public, \
          pm1_0, pm2_5, pm4_0, pm10, pm2_5_aqi, pm10_aqi, \
          ncpm0_5, ncpm1_0, ncpm2_5, ncpm4_0, ncpm10, \
          temperature, humidity, tpsize, co2_ppm, co_ppm, baro_inhg, \
          o3_ppb, no2_ppb, so2_ppb, ch2o_ppb, voc_mgm3, latitude_f, longitude_f \
   FROM \`$PROJECT_ID.sensors_shared.tsi_raw_view\`"

ROW_COUNT=$(bq --project_id="$PROJECT_ID" query --nouse_legacy_sql --format=csv --use_legacy_sql=false \
  "SELECT COUNT(*) FROM \`$PROJECT_ID.sensors_shared.tsi_raw_materialized\`" | tail -1)

echo "[$(date)] Refresh complete. Rows: $ROW_COUNT"
