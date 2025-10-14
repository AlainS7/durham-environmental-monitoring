{{ config(materialized='table', partition_by={'field': 'day_date', 'data_type': 'date'}, cluster_by=['native_sensor_id','metric_name']) }}
-- 7-day rolling daily summary
with grouped as (
  select
    timestamp_trunc(timestamp, day) as day_ts,
    date(timestamp_trunc(timestamp, day)) as day_date,
    native_sensor_id,
    source,
    metric_name,
    avg(value) as avg_value,
    min(value) as min_value,
    max(value) as max_value,
    count(*) as samples
  from {{ ref('sensor_readings_long') }}
  where date(timestamp) between date_sub(date('{{ var("proc_date") }}'), interval 6 day) and date('{{ var("proc_date") }}')
  group by
    day_ts,
    day_date,
    native_sensor_id,
    source,
    metric_name
)
select
  day_ts,
  day_date,
  native_sensor_id,
  source,
  metric_name,
  avg_value,
  min_value,
  max_value,
  samples,
  -- include source to ensure uniqueness across different data sources
  farm_fingerprint(concat(cast(day_ts as string),'|',native_sensor_id,'|',metric_name,'|',source)) as row_id
from grouped
