{{ config(materialized='table', partition_by={'field': 'hour_date', 'data_type': 'date'}, cluster_by=['native_sensor_id','metric_name']) }}
-- Hourly summary from long
select
  timestamp_trunc(timestamp, hour) as hour_ts,
  date(timestamp_trunc(timestamp, hour)) as hour_date,
  native_sensor_id,
  source,
  metric_name,
  avg(value) as avg_value,
  min(value) as min_value,
  max(value) as max_value,
  count(*) as samples,
  farm_fingerprint(concat(cast(timestamp_trunc(timestamp, hour) as string),'|',native_sensor_id,'|',metric_name)) as row_id
from {{ ref('sensor_readings_long') }}
where date(timestamp) = '{{ var("proc_date") }}'
group by
  timestamp_trunc(timestamp, hour),
  date(timestamp_trunc(timestamp, hour)),
  native_sensor_id,
  source,
  metric_name
