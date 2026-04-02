# Durham Environmental Monitoring - Architecture Overview

This document is the evergreen system overview for the project. It explains how data moves through the platform, which components own each stage, and where to look for operational procedures.

For step-by-step setup, backfills, refreshes, and verification commands, use [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md).

## System Architecture

### System Map

The diagram below shows the control plane, ingestion path, warehouse layers, data export, downstream dashboards, and the isolated Oura utility path.

```mermaid
flowchart LR
  %% Core sources
  TSI[Triangle Sensors API]
  WU[Weather Underground API]
  GSM[Google Secret Manager]

  %% Control plane
  subgraph CONTROL[Control Plane]
    subgraph INGEST_CTRL[Ingestion Triggers]
      TF[Terraform<br/>infra/terraform]
      CS[Cloud Scheduler<br/>optional direct trigger]
      GHA1[GitHub Actions<br/>daily-ingest.yml]
    end
    subgraph MAINT_CTRL[Maintenance & Export]
      GHA2[GitHub Actions<br/>transformations-execute.yml]
      GHA3[GitHub Actions<br/>daily-verify.yml<br/>data-quality-check.yml]
      GHA4[GitHub Actions<br/>daily-refresh-shared.yml]
      GHA5[GitHub Actions<br/>sync-to-sharepoint.yml]
    end
  end

  %% Ingestion
  subgraph INGEST[Ingestion and Landing]
    CR[Cloud Run Job<br/>weather-data-uploader]
    GCS[Google Cloud Storage<br/>raw/source/date parquet]
    BQRAW[BigQuery sensors<br/>external, staging, and raw materialized tables]
  end

  %% Transformation + serving
  subgraph SERVE[Transformation and Serving]
    SQL[dbt, SQL, and Python transforms<br/>transformations/dbt & scripts/]
    BQAN[BigQuery analytics and shared layers<br/>derived tables, views, Grafana-ready tables]
    DASH[Dashboards and analysis<br/>Grafana, Looker Studio, notebooks]
  end

  %% Export
  subgraph EXPORT[Data Export]
    SP[SharePoint<br/>Curated Research Packs]
  end

  %% Observability
  subgraph OBS[Verification and Alerting]
    CHECKS[Freshness, staging presence,<br/>row thresholds, quality checks]
    ALERTS[MS Teams notifications,<br/>artifacts, GitHub issues]
  end

  %% Sidecar project
  subgraph OURA[Isolated sidecar]
    OCLI[oura-rings CLI and collectors]
    OBQ[Manual Oura BigQuery loads]
  end

  %% Triggers
  TF --> CS
  TF --> CR
  CS -->|scheduled run| CR
  GHA1 -->|scheduled or manual run| CR
  GHA1 -->|materialize raw partitions| BQRAW
  GHA2 --> SQL
  GHA3 --> CHECKS
  GHA4 --> BQAN
  GHA5 -->|generate & upload packs| SP

  %% Data Flow
  GSM --> CR
  TSI --> CR
  WU --> CR
  CR -->|write parquet| GCS
  GCS -->|external tables and staging| BQRAW
  BQRAW --> SQL
  SQL --> BQAN
  BQAN --> DASH

  %% Exports
  GCS -.->|sync parquet| SP

  %% Observability Flow
  BQRAW --> CHECKS
  BQAN --> CHECKS
  CHECKS --> ALERTS

  %% Sidecar flow
  OCLI -. exploratory/manual .-> OBQ
  OBQ -. optional separate analysis .-> BQAN

  classDef control fill:#0f766e,stroke:#134e4a,color:#ffffff,stroke-width:2px;
  classDef ingest fill:#1d4ed8,stroke:#1e3a8a,color:#ffffff,stroke-width:2px;
  classDef serve fill:#7c3aed,stroke:#4c1d95,color:#ffffff,stroke-width:2px;
  classDef export fill:#0369a1,stroke:#0c4a6e,color:#ffffff,stroke-width:2px;
  classDef observe fill:#ea580c,stroke:#9a3412,color:#ffffff,stroke-width:2px;
  classDef sidecar fill:#6b7280,stroke:#374151,color:#ffffff,stroke-width:2px,stroke-dasharray: 6 3;
  classDef source fill:#f8fafc,stroke:#475569,color:#0f172a,stroke-width:1.5px;

  class TF,CS,GHA1,GHA2,GHA3,GHA4,GHA5 control;
  class CR,GCS,BQRAW ingest;
  class SQL,BQAN,DASH serve;
  class SP export;
  class CHECKS,ALERTS observe;
  class OCLI,OBQ sidecar;
  class TSI,WU,GSM source;
```

## Core Data Flow

1. GitHub Actions or Cloud Scheduler triggers the Cloud Run job `weather-data-uploader`.
2. The collector fetches TSI and WU data and writes Parquet files to Google Cloud Storage.
3. External and staging tables are materialized into native BigQuery raw tables.
4. Transformation jobs (primarily SQL via Python runners, with dbt validation scaffolding) build analytics-ready tables and views in BigQuery.
5. Shared BigQuery objects are refreshed for Grafana and related downstream consumers.
6. A workflow-driven export process packages data into research packs and syncs them to SharePoint.
7. Verification workflows check freshness, row thresholds, and data quality; failures trigger MS Teams notifications and GitHub issues.

## Key Components

### 1\. Orchestration and Control Plane

Primary workflows:

- [`.github/workflows/daily-ingest.yml`](../.github/workflows/daily-ingest.yml) triggers Cloud Run ingestion every 6 hours and can optionally redeploy, materialize, merge, and run checks.
- [`.github/workflows/transformations-execute.yml`](../.github/workflows/transformations-execute.yml) runs the data transformation layer.
- [`.github/workflows/sync-to-sharepoint.yml`](../.github/workflows/sync-to-sharepoint.yml) handles manual exports to external researchers.
- [`.github/workflows/daily-verify.yml`](../.github/workflows/daily-verify.yml) and [`.github/workflows/data-quality-check.yml`](../.github/workflows/data-quality-check.yml) validate the pipeline.
- [`.github/workflows/daily-refresh-shared.yml`](../.github/workflows/daily-refresh-shared.yml) refreshes Grafana-facing shared tables.

Terraform under `infra/terraform` owns the long-lived cloud infrastructure. Cloud Scheduler remains an optional direct production trigger when GitHub Actions is not the preferred scheduler.

### 2\. Cloud Run Ingestion Job

The ingestion job runs the collector for one day or a supplied date range.

- Job name: `weather-data-uploader`
- Region: `us-east1`
- Collector entry point: [`src/data_collection/daily_data_collector.py`](../src/data_collection/daily_data_collector.py)
- Cloud Run execution wrapper: [`scripts/run_cr_job.sh`](../scripts/run_cr_job.sh)
- GCS writer and schema coercion: [`src/storage/gcs_uploader.py`](../src/storage/gcs_uploader.py)

The collector fetches source data, writes Parquet to GCS, and feeds the downstream raw-materialization process.

### 3\. Storage and Warehouse Layers

#### Raw landing in GCS

- Bucket pattern: `gs://<bucket>/raw/...`
- Layout: `raw/source=<SOURCE>/agg=raw/dt=<YYYY-MM-DD>/`
- Format: Parquet

GCS is the durable landing zone for raw ingested files and the source for BigQuery external or staging loads, as well as the source for SharePoint exports.

#### BigQuery production dataset: `sensors`

The `sensors` dataset contains the core warehouse objects:

- external and staging tables used during load and recovery flows
- native partitioned raw tables such as `tsi_raw_materialized` and `wu_raw_materialized`
- enriched and transformed analytics tables used for analysis and sharing

Key materialization script:

- [`scripts/materialize_partitions.py`](../scripts/materialize_partitions.py)

#### BigQuery shared dataset: `sensors_shared`

The `sensors_shared` dataset exposes dashboard-friendly objects and copied or refreshed tables for downstream tools such as Grafana.

Key refresh scripts:

- [`scripts/refresh_tsi_shared.sh`](../scripts/refresh_tsi_shared.sh)
- [`scripts/refresh_wu_shared.sh`](../scripts/refresh_wu_shared.sh)
- [`scripts/sync_to_grafana.py`](../scripts/sync_to_grafana.py)

### 4\. Transformation Layer

Transformations render and execute logic over the warehouse to produce analytics-ready tables.

- primary production runner: SQL via [`scripts/run_transformations.py`](../scripts/run_transformations.py)
- validation/migration path: dbt scaffold in `transformations/dbt/`
- batch wrapper: [`scripts/run_transformations_batch.sh`](../scripts/run_transformations_batch.sh)

This layer separates ingestion concerns from reporting and analysis concerns.

### 5\. Data Export (SharePoint)

To support external researchers, the pipeline packages curated parquet files and syncs them to Microsoft SharePoint.

- Sync scripts: [`scripts/sync_parquet_to_sharepoint.py`](../scripts/sync_parquet_to_sharepoint.py) and [`scripts/upload_research_pack_to_sharepoint.py`](../scripts/upload_research_pack_to_sharepoint.py)
- Configuration: [`config/sharepoint_sync_scope.json`](../config/sharepoint_sync_scope.json)

### 6\. Verification and Alerting

Verification is handled by scheduled workflows and scripts that check whether expected data arrived and whether derived tables remain healthy.

Representative checks:

- freshness
- staging-table presence
- row-count thresholds
- transformation output validation
- data-quality assertions

Representative scripts:

- [`scripts/check_freshness.py`](../scripts/check_freshness.py)
- [`scripts/notify_teams.py`](../scripts/notify_teams.py) (MS Teams integration for alerts)
- [`scripts/check_data_quality.py`](../scripts/check_data_quality.py)
- [`scripts/verify_cloud_pipeline.py`](../scripts/verify_cloud_pipeline.py)

### 7\. Dashboard and Analytics Consumers

The primary consumer pattern is:

- BigQuery `sensors_shared` dataset
- Grafana dashboards using BigQuery queries shaped as `time`, `metric`, and `value`
- additional consumers such as Looker Studio, notebooks, and ad hoc BigQuery analysis

See [GRAFANA_SETUP.md](GRAFANA_SETUP.md) and [DATA_QUICK_START.md](DATA_QUICK_START.md) for consumer-facing guidance.

### 8\. Oura Sidecar

The `oura-rings/` directory is intentionally separate from the core production pipeline. It supports manual or exploratory collection and optional analysis, but it is not part of the default scheduled ingestion path.

## Design Notes

- The architecture keeps raw ingestion, warehouse materialization, transformations, dashboard serving, exports, and verification as separate concerns.
- Shared dashboard tables exist to isolate consumers from production-schema churn.
- Operational details such as backfill windows, row counts, and current freshness are intentionally kept out of this document because they go stale quickly.

## Related Docs

- [OPERATIONS_RUNBOOK.md](OPERATIONS_RUNBOOK.md) - reproducible procedures for setup, ingestion, backfill, refresh, and verification
- [GRAFANA_SETUP.md](GRAFANA_SETUP.md) - Grafana data source setup and example queries
- [DATA_QUICK_START.md](DATA_QUICK_START.md) - query-first guide for common analyses
- [DAILY_AUTOMATION.md](DAILY_AUTOMATION.md) - scheduler-specific automation notes
- [Monitoring-Alerts.md](Monitoring-Alerts.md) - monitoring and alerting references
- [SHAREPOINT_SYNC.md](SHAREPOINT_SYNC.md) - details on the external researcher export process
