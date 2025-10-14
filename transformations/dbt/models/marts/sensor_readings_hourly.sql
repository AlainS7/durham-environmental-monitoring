{{ config(materialized='table', partition_by={'field': 'hour_date', 'data_type': 'date'}, cluster_by=['native_sensor_id','metric_name']) }}
-- Hourly summary from long
with grouped as (
  select
    timestamp_trunc(timestamp, hour) as hour_ts,
    date(timestamp_trunc(timestamp, hour)) as hour_date,
    native_sensor_id,
    source,
    metric_name,
    avg(value) as avg_value,
    min(value) as min_value,
    max(value) as max_value,
    count(*) as samples
  from {{ ref('sensor_readings_long') }}
  where date(timestamp) = '{{ var("proc_date") }}'
  group by
    hour_ts,
    hour_date,
    native_sensor_id,
    source,
    metric_name
)
select
  hour_ts,
  hour_date,
  native_sensor_id,
  source,
  metric_name,
  avg_value,
  min_value,
  max_value,
  samples,
  -- include source to ensure uniqueness across different data sources
  farm_fingerprint(concat(cast(hour_ts as string),'|',native_sensor_id,'|',metric_name,'|',source)) as row_id
from grouped
