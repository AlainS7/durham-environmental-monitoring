{{ config(materialized='table', partition_by={'field': 'day_date', 'data_type': 'date'}, cluster_by=['native_sensor_id','metric_name']) }}
-- 7-day rolling daily summary
select
  timestamp_trunc(timestamp, day) as day_ts,
  date(timestamp_trunc(timestamp, day)) as day_date,
  native_sensor_id,
  source,
  metric_name,
  avg(value) as avg_value,
  min(value) as min_value,
  max(value) as max_value,
  count(*) as samples,
  farm_fingerprint(concat(cast(timestamp_trunc(timestamp, day) as string),'|',native_sensor_id,'|',metric_name)) as row_id
from {{ ref('sensor_readings_long') }}
where date(timestamp) between date_sub(date('{{ var("proc_date") }}'), interval 6 day) and date('{{ var("proc_date") }}')
group by
  timestamp_trunc(timestamp, day),
  date(timestamp_trunc(timestamp, day)),
  native_sensor_id,
  source,
  metric_name
