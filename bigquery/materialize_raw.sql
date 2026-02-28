-- Variables: ${PROJECT} (GCP project ID), substituted at runtime by envsubst or shell
-- Create or replace partitioned native tables from external sources.
-- Run ad-hoc for backfill; afterwards use incremental refresh script for daily partitions.

CREATE SCHEMA IF NOT EXISTS `${PROJECT}.sensors`;

CREATE OR REPLACE TABLE `${PROJECT}.sensors.wu_raw_materialized`
PARTITION BY DATE(ts) AS
SELECT
  COALESCE(
    SAFE_CAST(t.timestamp AS TIMESTAMP),
    CASE
      WHEN ABS(SAFE_CAST(t.timestamp AS INT64)) >= 100000000000000000 THEN TIMESTAMP_MICROS(DIV(SAFE_CAST(t.timestamp AS INT64), 1000))
      WHEN ABS(SAFE_CAST(t.timestamp AS INT64)) >= 100000000000000 THEN TIMESTAMP_MICROS(SAFE_CAST(t.timestamp AS INT64))
      WHEN ABS(SAFE_CAST(t.timestamp AS INT64)) >= 100000000000 THEN TIMESTAMP_MILLIS(SAFE_CAST(t.timestamp AS INT64))
      ELSE TIMESTAMP_SECONDS(SAFE_CAST(t.timestamp AS INT64))
    END
  ) AS ts,
  t.* EXCEPT(timestamp)
FROM `${PROJECT}.sensors.wu_raw_external` t;

CREATE OR REPLACE TABLE `${PROJECT}.sensors.tsi_raw_materialized`
PARTITION BY DATE(ts) AS
SELECT
  COALESCE(
    SAFE_CAST(t.timestamp AS TIMESTAMP),
    CASE
      WHEN ABS(SAFE_CAST(t.timestamp AS INT64)) >= 100000000000000000 THEN TIMESTAMP_MICROS(DIV(SAFE_CAST(t.timestamp AS INT64), 1000))
      WHEN ABS(SAFE_CAST(t.timestamp AS INT64)) >= 100000000000000 THEN TIMESTAMP_MICROS(SAFE_CAST(t.timestamp AS INT64))
      WHEN ABS(SAFE_CAST(t.timestamp AS INT64)) >= 100000000000 THEN TIMESTAMP_MILLIS(SAFE_CAST(t.timestamp AS INT64))
      ELSE TIMESTAMP_SECONDS(SAFE_CAST(t.timestamp AS INT64))
    END
  ) AS ts,
  t.* EXCEPT(timestamp)
FROM `${PROJECT}.sensors.tsi_raw_external` t;
