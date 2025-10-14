{{ config(materialized='table', partition_by={'field': 'timestamp_date', 'data_type': 'date'}, cluster_by=['native_sensor_id','metric_name']) }}
-- Long unified table from staging sources (emulates 01_sensor_readings_long.sql)
with wu_src as (
    select
      timestamp,
      native_sensor_id,
      temperature,
      humidity,
      precip_rate,
      precip_total,
      wind_speed_avg,
      wind_gust_avg,
      wind_direction_avg,
      solar_radiation,
      uv_high
    from {{ ref('stg_wu_raw') }}
    where timestamp is not null
      and date(timestamp) between date_sub(var('proc_date'), interval 0 day) and var('proc_date')
), tsi_src as (
    select
      timestamp,
      native_sensor_id,
      pm2_5,
      humidity,
      temperature
    from {{ ref('stg_tsi_raw') }}
    where timestamp is not null
      and date(timestamp) between date_sub(var('proc_date'), interval 0 day) and var('proc_date')
), wu_long as (
    select * from wu_src
    unpivot (value for metric_name in (temperature, humidity, precip_rate, precip_total, wind_speed_avg, wind_gust_avg, wind_direction_avg, solar_radiation, uv_high))
), tsi_long as (
    select * from tsi_src
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
