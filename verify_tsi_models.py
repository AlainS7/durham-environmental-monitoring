#!/usr/bin/env python3
"""Verify TSI sensor model variations and field coverage."""


from google.cloud import bigquery



client = bigquery.Client(project='durham-weather-466502')

query = """
SELECT 
  native_sensor_id,
  model,
  COUNT(*) as total_records,
  COUNTIF(pm1_0 IS NOT NULL) as has_pm1,
  COUNTIF(pm2_5 IS NOT NULL) as has_pm25,
  COUNTIF(pm10 IS NOT NULL) as has_pm10,
  COUNTIF(co2_ppm IS NOT NULL) as has_co2,
  COUNTIF(voc_mgm3 IS NOT NULL) as has_voc,
  COUNTIF(o3_ppb IS NOT NULL) as has_o3,
  COUNTIF(no2_ppb IS NOT NULL) as has_no2,
  ROUND(COUNTIF(pm2_5 IS NOT NULL) / COUNT(*) * 100, 1) as pm25_coverage_pct,
  ROUND(COUNTIF(co2_ppm IS NOT NULL) / COUNT(*) * 100, 1) as co2_coverage_pct
FROM `durham-weather-466502.sensors.tsi_raw_materialized`
WHERE DATE(ts) >= '2025-07-04'
GROUP BY native_sensor_id, model
ORDER BY pm25_coverage_pct DESC, total_records DESC
"""

print('\n=== TSI Sensor Model and Field Coverage Analysis ===\n')
results = client.query(query).result()

for row in results:
    model_str = str(row.model) if row.model is not None else "NULL"
    print(f'Sensor: {row.native_sensor_id:<20} Model: {model_str:<10}  Records: {row.total_records:>6}')
    print(f'  PM Coverage: PM1.0={row.has_pm1:>6} PM2.5={row.has_pm25:>6} PM10={row.has_pm10:>6} ({row.pm25_coverage_pct:>5.1f}%)')
    print(f'  Gas Sensors: CO2={row.has_co2:>6} VOC={row.has_voc:>6} O3={row.has_o3:>6} NO2={row.has_no2:>6} ({row.co2_coverage_pct:>5.1f}% CO2)')
    print()

print('\n=== Summary by Model ===\n')
query2 = """
SELECT 
  CAST(model AS STRING) as model,
  COUNT(DISTINCT native_sensor_id) as sensor_count,
  COUNT(*) as total_records,
  ROUND(COUNTIF(pm2_5 IS NOT NULL) / COUNT(*) * 100, 1) as pm25_pct,
  ROUND(COUNTIF(co2_ppm IS NOT NULL) / COUNT(*) * 100, 1) as co2_pct,
  ROUND(COUNTIF(voc_mgm3 IS NOT NULL) / COUNT(*) * 100, 1) as voc_pct,
  ROUND(COUNTIF(o3_ppb IS NOT NULL) / COUNT(*) * 100, 1) as o3_pct
FROM `durham-weather-466502.sensors.tsi_raw_materialized`
WHERE DATE(ts) >= '2025-07-04'
GROUP BY model
ORDER BY pm25_pct DESC
"""

results2 = client.query(query2).result()
for row in results2:
    model_str = row.model if row.model else 'NULL'
    print(f'Model: {model_str:<15} Sensors: {row.sensor_count:>2}  Records: {row.total_records:>7}')
    print(f'  Field Coverage: PM2.5={row.pm25_pct:>5.1f}%  CO2={row.co2_pct:>5.1f}%  VOC={row.voc_pct:>5.1f}%  O3={row.o3_pct:>5.1f}%')
    print()

print('\n=== Key Findings ===')
print('If all sensors show the same model number with different field coverage,')
print('then the issue is NOT hardware variations but likely API/configuration.')
print('If sensors show different model numbers correlating with field coverage,')
print('then hardware variation is confirmed.')
