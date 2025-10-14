-- Simple staging model selecting from raw TSI table
select * from {{ source('raw_sources', 'tsi_raw_materialized') }}
