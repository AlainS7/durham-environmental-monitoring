variable "project_id" { 
	type = string 
}
variable "region" { 
	type    = string
	default = "us-central1" 
}
variable "gcs_bucket" { 
	type = string 
}
variable "gcs_prefix" { 
	type    = string 
	default = "sensor_readings" 
}
variable "bq_dataset" { 
	type    = string  
	default = "sensors" 
}
variable "raw_retention_days" { 
	type    = number 
	default = 90 
}
variable "ingestion_job_name" { 
	type    = string 
	default = "sensor-ingestion-job" 
}
variable "ingestion_image" { 
	type        = string 
	description = "Full artifact registry image reference" 
}
variable "ingestion_cron" { 
	type    = string 
	default = "5 * * * *" 
}
variable "cron_timezone" { 
	type    = string 
	default = "UTC" 
}

# Additional maintenance job images (optional if using shared repo + tag)
variable "refresh_job_name" { 
	type    = string 
	default = "refresh-partitions" 
}
variable "refresh_image" { 
	type        = string 
	description = "Image for partition refresh job" 
}
variable "refresh_cron" { 
	type    = string 
	default = "0 4 * * *" 
}

variable "metrics_job_name" { 
	type    = string 
	default = "record-metrics" 
}
variable "metrics_image" { 
	type        = string 
	description = "Image for metrics recording job" 
}
variable "metrics_cron" { 
	type    = string 
	default = "10 4 * * *" 
}

variable "window_days" { 
	type    = number 
	default = 7 
}

# Artifact Registry (optional create)
variable "create_artifact_repo" { 
	type    = bool 
	default = false 
}
variable "artifact_repo" { 
	type    = string 
	default = "weather-maintenance-images" 
}

# Secrets (defaults assume already created in Secret Manager)
variable "wu_api_key_secret" { 
	type    = string 
	default = "wu_api_key" 
}
variable "tsi_client_id_secret" { 
	type    = string 
	default = "tsi_client_id" 
}
variable "tsi_client_secret_secret" { 
	type    = string 
	default = "tsi_client_secret" 
}
variable "tsi_auth_url_secret" { 
	type    = string 
	default = "tsi_auth_url" 
}

# Optional: create empty secrets if they do not already exist
variable "create_secrets" {
	type    = bool
	default = false
}

# Monitoring notification channels to attach to alert policies
variable "notification_channel_ids" {
	type    = list(string)
	default = []
}

# Control whether Terraform creates the BigQuery dataset (set false if it already exists)
variable "create_dataset" {
	type    = bool
	default = false
}

# Control whether to create alert policies (can defer until metrics exist)
variable "create_alert_policies" {
	type    = bool
	default = false
}
