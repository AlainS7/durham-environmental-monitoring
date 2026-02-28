#!/bin/bash
set -euo pipefail
# Create the sensor calibration configuration table in BigQuery

PROJECT_ID="${BQ_PROJECT:-durham-weather-466502}"
DATASET="${BQ_DATASET:-sensors}"

echo "Creating calibration_config table in ${DATASET}..."

bq query --project_id="${PROJECT_ID}" --nouse_legacy_sql --display_name="Create calibration_config" << 'EOF'
CREATE OR REPLACE TABLE `${PROJECT_ID}.${DATASET}.calibration_config`
(
  native_sensor_id STRING,
  metric_name STRING,
  slope FLOAT64,
  intercept FLOAT64,
  effective_date DATE,
  end_date DATE,
  description STRING,
  created_at TIMESTAMP
)
PARTITION BY effective_date
CLUSTER BY native_sensor_id, metric_name;

-- Insert example calibration rules
INSERT INTO `${PROJECT_ID}.${DATASET}.calibration_config`
(native_sensor_id, metric_name, slope, intercept, effective_date, end_date, description, created_at)
VALUES
  -- DEFAULT rules (slope=1.0, intercept=0.0 = no calibration)
  ('DEFAULT', 'DEFAULT', 1.0, 0.0, DATE('2025-01-01'), NULL, 'Default: no calibration applied', CURRENT_TIMESTAMP()),
  
  -- Example: Sensor d14rfblfk2973f196c5g PM2.5 calibration (from Jan 1, 2025 onwards)
  ('d14rfblfk2973f196c5g', 'pm2_5', 0.91, 0.5, DATE('2025-01-01'), NULL, 'TSI Gen2 Outdoor - humidity bias correction', CURRENT_TIMESTAMP())
  
  -- Add more sensors and metrics as needed:
  -- ('curotklveott0jmp5agg', 'pm2_5', 0.95, 0.2, DATE('2025-11-17'), NULL, 'TSI sensor - calibration applied', CURRENT_TIMESTAMP()),
  -- ('curp515veott0jmp5ajg', 'pm2_5', 0.88, 1.0, DATE('2025-11-17'), NULL, 'TSI sensor - drift correction', CURRENT_TIMESTAMP()),
;

SELECT 'Calibration config table created successfully!' as status;
EOF

echo "Done!"
