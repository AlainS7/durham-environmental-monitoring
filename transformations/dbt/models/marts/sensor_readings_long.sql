{{ config(materialized='table', partition_by={'field': 'timestamp_date', 'data_type': 'date'}, cluster_by=['native_sensor_id','metric_name']) }}
-- Long unified table from staging sources (emulates 01_sensor_readings_long.sql)
with wu_src as (
    select
      obsTimeUtc as timestamp,
      stationID as native_sensor_id,
      cast(tempAvg as float64) as temperature,
      cast(humidityAvg as float64) as humidity,
      cast(precipRate as float64) as precip_rate,
      cast(precipTotal as float64) as precip_total,
      cast(windspeedAvg as float64) as wind_speed_avg,
      cast(windgustAvg as float64) as wind_gust_avg,
      cast(winddirAvg as float64) as wind_direction_avg,
      cast(solarRadiationHigh as float64) as solar_radiation,
      cast(uvHigh as float64) as uv_high
    from {{ ref('stg_wu_raw') }}
    where obsTimeUtc is not null
      and date(obsTimeUtc) between date_sub(var('proc_date'), interval 0 day) and var('proc_date')
), tsi_src as (
    select
      cloud_timestamp as timestamp,
      device_id as native_sensor_id,
      cast(mcpm2x5 as float64) as pm2_5,
      cast(rh as float64) as humidity,
      cast(temperature as float64) as temperature
    from {{ ref('stg_tsi_raw') }}
    where cloud_timestamp is not null
      and date(cloud_timestamp) between date_sub(var('proc_date'), interval 0 day) and var('proc_date')
), wu_long as (
    select timestamp, native_sensor_id, metric_name, value from wu_src
    unpivot (value for metric_name in (temperature, humidity, precip_rate, precip_total, wind_speed_avg, wind_gust_avg, wind_direction_avg, solar_radiation, uv_high))
), tsi_long as (
    select timestamp, native_sensor_id, metric_name, value from tsi_src
    unpivot (value for metric_name in (pm2_5, humidity, temperature))
)
select timestamp,
       date(timestamp) as timestamp_date,
       native_sensor_id,
       metric_name,
       value,
       'WU' as source,
       farm_fingerprint(concat(cast(timestamp as string),'|',native_sensor_id,'|',metric_name)) as row_id
from wu_long
union all
select timestamp,
       date(timestamp) as timestamp_date,
       native_sensor_id,
       metric_name,
       value,
       'TSI' as source,
       farm_fingerprint(concat(cast(timestamp as string),'|',native_sensor_id,'|',metric_name)) as row_id
from tsi_long
