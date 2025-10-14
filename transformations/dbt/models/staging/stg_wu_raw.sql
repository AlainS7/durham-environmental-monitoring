-- Simple staging model selecting from raw WU table
select * from {{ source('raw_sources', 'wu_raw_materialized') }}
