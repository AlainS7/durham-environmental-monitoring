terraform {
  required_version = ">= 1.6.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Optionally create placeholder secrets (no versions) so env refs don't fail
resource "google_secret_manager_secret" "wu_api_key" {
  count     = var.create_secrets ? 1 : 0
  secret_id = var.wu_api_key_secret
  replication {
    user_managed {
      replicas { location = var.region }
    }
  }
}
resource "google_secret_manager_secret" "tsi_client_id" {
  count     = var.create_secrets ? 1 : 0
  secret_id = var.tsi_client_id_secret
  replication {
    user_managed {
      replicas { location = var.region }
    }
  }
}
resource "google_secret_manager_secret" "tsi_client_secret" {
  count     = var.create_secrets ? 1 : 0
  secret_id = var.tsi_client_secret_secret
  replication {
    user_managed {
      replicas { location = var.region }
    }
  }
}
resource "google_secret_manager_secret" "tsi_auth_url" {
  count     = var.create_secrets ? 1 : 0
  secret_id = var.tsi_auth_url_secret
  replication {
    user_managed {
      replicas { location = var.region }
    }
  }
}


# Optional Artifact Registry repository
resource "google_artifact_registry_repository" "images" {
  count         = var.create_artifact_repo ? 1 : 0
  location      = var.region
  repository_id = var.artifact_repo
  format        = "DOCKER"
  description   = "Container images for ingestion & maintenance jobs"
}

# GCS bucket for raw sensor parquet
resource "google_storage_bucket" "raw_bucket" {
  name                         = var.gcs_bucket
  location                     = var.region
  force_destroy                = false
  uniform_bucket_level_access  = true

  dynamic "lifecycle_rule" {
    for_each = var.raw_retention_days > 0 ? [1] : []
    content {
      action { type = "Delete" }
      condition { age = var.raw_retention_days }
    }
  }
}

# BigQuery dataset for sensor tables
resource "google_bigquery_dataset" "sensors" {
  count       = var.create_dataset ? 1 : 0
  dataset_id  = var.bq_dataset
  location    = var.region
  description = "Environmental sensor raw and transformed data"
  delete_contents_on_destroy = false
}

# Service accounts
resource "google_service_account" "ingestion" {
  account_id   = "sensor-ingestion"
  display_name = "Sensor Ingestion"
}

resource "google_service_account" "verifier" {
  account_id   = "sensor-verifier"
  display_name = "Pipeline Verifier"
}

# IAM bindings (least privilege coarse example)
resource "google_project_iam_member" "ingestion_bq_jobuser" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_project_iam_member" "verifier_bq_jobuser" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.verifier.email}"
}

resource "google_bigquery_dataset_iam_member" "ingestion_dataset_editor" {
  dataset_id = var.bq_dataset
  role       = "roles/bigquery.dataEditor"
  member     = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_bigquery_dataset_iam_member" "verifier_dataset_viewer" {
  dataset_id = var.bq_dataset
  role       = "roles/bigquery.dataViewer"
  member     = "serviceAccount:${google_service_account.verifier.email}"
}

resource "google_storage_bucket_iam_member" "ingestion_bucket_writer" {
  bucket = google_storage_bucket.raw_bucket.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.ingestion.email}"
}

resource "google_storage_bucket_iam_member" "verifier_bucket_viewer" {
  bucket = google_storage_bucket.raw_bucket.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.verifier.email}"
}

# Allow verifier SA to access Secret Manager (so GitHub Actions OIDC can read secrets)
resource "google_project_iam_member" "verifier_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.verifier.email}"
}

# Optional combined TSI creds secret expected by application (JSON payload)
resource "google_secret_manager_secret" "tsi_creds" {
  count     = var.create_secrets ? 1 : 0
  secret_id = "tsi_creds"
  replication {
    user_managed {
      replicas { location = var.region }
    }
  }
}

# Cloud Run Job for ingestion (container image assumed built externally)
resource "google_cloud_run_v2_job" "ingestion_job" {
  name     = var.ingestion_job_name
  location = var.region
  deletion_protection = false
  template {
    template {
      containers {
        image = var.ingestion_image
        env {
          name  = "GCS_BUCKET"
          value = var.gcs_bucket
        }
        env {
          name  = "GCS_PREFIX"
          value = var.gcs_prefix
        }
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset
        }
        env {
          name  = "BQ_PROJECT"
          value = var.project_id
        }
        # Ensure application sees PROJECT_ID (some components rely on this exact var name)
        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        # Secret env vars
        env {
          name = "WU_API_KEY"
          value_source {
            secret_key_ref {
              secret  = var.wu_api_key_secret
              version = "latest"
            }
          }
        }
  # Application expects secret id environment variables referencing Secret Manager ids containing JSON docs.
  # For now map WU key secret id to same secret; TSI expects JSON secret containing key+secret, but we only have separate secrets.
        env {
          name  = "TSI_CREDS_SECRET_ID"
          value = "tsi_creds"
        }
        env {
          name  = "WU_API_KEY_SECRET_ID"
          value = var.wu_api_key_secret
        }
        env {
          name = "TSI_CLIENT_ID"
          value_source {
            secret_key_ref {
              secret  = var.tsi_client_id_secret
              version = "latest"
            }
          }
        }
        env {
          name = "TSI_CLIENT_SECRET"
          value_source {
            secret_key_ref {
              secret  = var.tsi_client_secret_secret
              version = "latest"
            }
          }
        }
        env {
          name = "TSI_AUTH_URL"
          value_source {
            secret_key_ref {
              secret  = var.tsi_auth_url_secret
              version = "latest"
            }
          }
        }
      }
      service_account = google_service_account.ingestion.email
    }
  }
}

# Partition refresh job
resource "google_cloud_run_v2_job" "refresh_job" {
  name     = var.refresh_job_name
  location = var.region
  template {
    template {
      containers {
        image = var.refresh_image
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset
        }
        env {
          name  = "BQ_PROJECT"
          value = var.project_id
        }
      }
      service_account = google_service_account.ingestion.email
    }
  }
}

# Metrics recording job
resource "google_cloud_run_v2_job" "metrics_job" {
  name     = var.metrics_job_name
  location = var.region
  template {
    template {
      containers {
        image = var.metrics_image
        env {
          name  = "BQ_DATASET"
          value = var.bq_dataset
        }
        env {
          name  = "BQ_PROJECT"
          value = var.project_id
        }
        env {
          name  = "WINDOW_DAYS"
          value = tostring(var.window_days)
        }
      }
      service_account = google_service_account.ingestion.email
    }
  }
}

# IAM binding for secret access
resource "google_project_iam_member" "ingestion_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.ingestion.email}"
}

# Basic alert: Ingestion job failures (log-based metric not defined here; using Cloud Run Error Count policy placeholder)
resource "google_monitoring_alert_policy" "ingestion_failures" {
  count        = var.create_alert_policies ? 1 : 0
  display_name = "Ingestion Job Failures"
  combiner     = "OR"
  conditions {
    display_name = "Run job execution errors"
    condition_monitoring_query_language {
      query = <<-EOT
fetch cloud_run_job
| metric 'run.googleapis.com/job/completed_count'
| filter resource.job_name == '${var.ingestion_job_name}'
| align rate(1h)
| every 1h
| group_by [], sum
| condition val < 1 '1/h'
EOT
      duration = "3600s"
      trigger {
        count = 1
      }
    }
  }
  notification_channels = var.notification_channel_ids
  documentation {
    content  = "Ingestion job appears not to have completed in the last hour. Investigate Cloud Run executions."
    mime_type = "text/markdown"
  }
  user_labels = { system = "sensor-pipeline" }
}

# Basic freshness alert (placeholder metric; expects custom metric ingestion_metrics table lag handled externally)
resource "google_monitoring_alert_policy" "data_freshness" {
  count        = var.create_alert_policies ? 1 : 0
  display_name = "Data Freshness Lag"
  combiner     = "OR"
  conditions {
    display_name = "Partition freshness > 36h"
    condition_monitoring_query_language {
      query = <<-EOT
fetch bigquery_table
| metric 'bigquery.googleapis.com/table/modified_count'
| filter resource.dataset_id == '${var.bq_dataset}'
| align next_older(36h)
| every 6h
| group_by [], sum
| condition val == 0
EOT
      duration = "21600s"
      trigger { count = 1 }
    }
  }
  notification_channels = var.notification_channel_ids
  documentation {
    content  = "No table modifications detected in the dataset window; check ingestion & refresh jobs."
    mime_type = "text/markdown"
  }
  user_labels = { system = "sensor-pipeline" }
}

# Cloud Scheduler direct HTTP trigger of the Cloud Run Job (run endpoint)
resource "google_cloud_scheduler_job" "daily_ingestion" {
  name        = "${var.ingestion_job_name}-daily"
  description = "Daily sensor ingestion trigger (HTTP)"
  schedule    = var.ingestion_cron
  time_zone   = var.cron_timezone
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.ingestion_job.name}:run"
    oidc_token {
      service_account_email = google_service_account.ingestion.email
    }
    headers = {
      Content-Type = "application/json"
    }
    body = base64encode("{}")
  }
}

resource "google_cloud_scheduler_job" "daily_refresh" {
  name        = "${var.refresh_job_name}-daily"
  description = "Daily partition refresh"
  schedule    = var.refresh_cron
  time_zone   = var.cron_timezone
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.refresh_job.name}:run"
    oidc_token { service_account_email = google_service_account.ingestion.email }
    headers = { Content-Type = "application/json" }
    body    = base64encode("{}")
  }
}

resource "google_cloud_scheduler_job" "daily_metrics" {
  name        = "${var.metrics_job_name}-daily"
  description = "Daily ingestion metrics recording"
  schedule    = var.metrics_cron
  time_zone   = var.cron_timezone
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/${google_cloud_run_v2_job.metrics_job.name}:run"
    oidc_token { service_account_email = google_service_account.ingestion.email }
    headers = { Content-Type = "application/json" }
    body    = base64encode("{}")
  }
}

