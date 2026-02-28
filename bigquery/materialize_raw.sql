-- Variables: ${PROJECT} (GCP project ID), substituted at runtime by envsubst or shell
-- Create or replace partitioned native tables from external sources.
-- Run ad-hoc for backfill; afterwards use incremental refresh script for daily partitions.

CREATE SCHEMA IF NOT EXISTS `${PROJECT}.sensors`;

CREATE OR REPLACE TABLE `${PROJECT}.sensors.wu_raw_materialized`
PARTITION BY DATE(timestamp) AS
SELECT * FROM `${PROJECT}.sensors.wu_raw_external`;

CREATE OR REPLACE TABLE `${PROJECT}.sensors.tsi_raw_materialized`
PARTITION BY DATE(timestamp) AS
SELECT * FROM `${PROJECT}.sensors.tsi_raw_external`;
