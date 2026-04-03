# Terraform Infrastructure Skeleton

This module provisions core infra for the Durham Environmental Monitoring pipeline.

## Resources

- GCS bucket (raw Parquet). Infinite retention by default (no lifecycle rule). Enable time-based deletion by setting `raw_retention_days` > 0.
- BigQuery dataset for raw & transformed tables.
- Ingestion & verifier service accounts with least privilege example roles.
- Cloud Run Jobs: ingestion, partition refresh, metrics recording.
- Cloud Scheduler jobs invoking each Cloud Run job via OIDC.
- Secret Manager integration for API keys (WU / TSI credentials) injected as env.
- Basic Monitoring alert policies (ingestion job inactivity, dataset freshness placeholder).
- Optional auto-creation of empty Secret Manager secrets (set `create_secrets=true`).
- Pluggable notification channels for alert policies via `notification_channel_ids`.

## Usage

```hcl
module "sensor_pipeline" {
  source              = "./infra/terraform"
  project_id          = var.project_id
  region              = var.region
  gcs_bucket          = "my-sensor-raw-bucket"
  bq_dataset          = "sensors"
  gcs_prefix          = "sensor_readings"
  raw_retention_days  = 0 # infinite retention (no lifecycle block rendered)

  # Images (built separately by Cloud Build multi-image pipeline)
  ingestion_image     = "us-central1-docker.pkg.dev/${var.project_id}/weather-maintenance-images/ingestion:latest"
  refresh_image       = "us-central1-docker.pkg.dev/${var.project_id}/weather-maintenance-images/refresh-partitions:latest"
  metrics_image       = "us-central1-docker.pkg.dev/${var.project_id}/weather-maintenance-images/record-metrics:latest"

  # Optional override secret names (defaults shown)
  wu_api_key_secret         = "wu_api_key"
  tsi_client_id_secret      = "tsi_client_id"
  tsi_client_secret_secret  = "tsi_client_secret"
  tsi_auth_url_secret       = "tsi_auth_url"

  # Create placeholder secrets if not already present
  create_secrets = true

  # Attach existing notification channels (Monitoring channel full resource names)
  notification_channel_ids = [
    "projects/${var.project_id}/notificationChannels/1234567890123"
  ]

  # Schedules (UTC cron)
  ingestion_cron      = "5 * * * *"   # Hourly ingestion
  refresh_cron        = "0 4 * * *"   # 04:00 UTC partition refresh
  metrics_cron        = "10 4 * * *"  # 04:10 UTC metrics capture
}
```

Then:

```bash
terraform init
terraform plan -var project_id=YOUR_PROJECT -var gcs_bucket=your-bucket-name
terraform apply -var project_id=YOUR_PROJECT -var gcs_bucket=your-bucket-name
```

## Next Steps

- Add Workload Identity Federation provider & IAM binding conditions.
- Split roles into custom minimal roles if needed.
- Add Cloud Scheduler + Cloud Run job resources for end-to-end automation.
- Optionally pin images to immutable SHAs/digests instead of :latest (update \*\_image vars after Cloud Build).
- Configure Notification Channels (email/SMS/PagerDuty) in GCP and attach their resource names to alert policies if needed.

## Cloud Build (multi-image) Example

Create a trigger pointing at `cloudbuild.multi.yaml` with substitutions `_REGION`, `_REPO`, and `_TAG` (choose a tag strategy: date, commit, etc.).

Excerpt (simplified) from `cloudbuild.multi.yaml` now using `_TAG` substitution:

```yaml
steps:
  - id: Build ingestion image
    name: gcr.io/cloud-builders/docker
    args:
      [
        "build",
        "-t",
        "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPO}/ingestion:${_TAG}",
        "-t",
        "${_REGION}-docker.pkg.dev/$PROJECT_ID/${_REPO}/ingestion:latest",
        "--build-arg",
        "APP_SCRIPT=src/data_collection/daily_data_collector.py",
        ".",
      ]
  # ... refresh & metrics steps similar
substitutions:
  _REGION: us-central1
  _REPO: weather-maintenance-images
  _TAG: manual
```

Trigger example (manual tag injection):

```bash
gcloud builds submit --config=cloudbuild.multi.yaml --substitutions=_TAG=$(date +%Y%m%d%H%M)
```

After a successful build, optionally update Terraform vars to freeze versions (swap `:latest` for `:<tag>` or digests):

```bash
./scripts/pin_image_digests.sh "$PROJECT_ID" us-central1 weather-maintenance-images
"# Copy the terraform apply command above to pin all three images"
```

## Artifact Registry Creation

Option A (Terraform): set `create_artifact_repo=true` and supply `artifact_repo` (defaults to weather-maintenance-images).

Option B (gcloud manual):

```bash
gcloud artifacts repositories create weather-maintenance-images \
  --repository-format=DOCKER --location=us-central1 \
  --description="Sensor ingestion + maintenance images"
```

## One-Shot Bootstrap Script

To provision everything (optional repo creation, build images, apply Terraform, optional digest pin):

```bash
./scripts/bootstrap_infra.sh \
  --project YOUR_PROJECT_ID \
  --bucket YOUR_GCS_BUCKET \
  --create-repo \
  --pin
```

Flags:

- `--create-repo` ensures Artifact Registry exists (skip if pre-created)
- `--pin` prints a terraform command with image digests to lock versions

## Secrets

Create secrets (example):

```bash
echo -n "WU_KEY_VALUE" | gcloud secrets create wu_api_key --data-file=-
echo -n "TSI_CLIENT_ID_VALUE" | gcloud secrets create tsi_client_id --data-file=-
echo -n "TSI_CLIENT_SECRET_VALUE" | gcloud secrets create tsi_client_secret --data-file=-
echo -n "https://auth.tsi.example/oauth/token" | gcloud secrets create tsi_auth_url --data-file=-
```

Terraform grants `roles/secretmanager.secretAccessor` to the ingestion service account; rotate secrets by updating the secret versions (no infra change needed).

If you prefer Terraform to create placeholder secrets (no versions) set `create_secrets=true` then add versions with the helper script below.

### Helper Script to Create / Rotate Secrets

The repo includes `scripts/create_secrets.sh` to idempotently create secrets and add new versions.

Example usage:

```bash
export WU_API_KEY=your-wu-api-key \
  TSI_CLIENT_ID=cid \
  TSI_CLIENT_SECRET=csecret \
  TSI_AUTH_URL=https://auth.example.com/oauth/token
./scripts/create_secrets.sh --project $PROJECT_ID
```

If env vars are omitted you'll be prompted securely. Each invocation adds new versions (old versions remain for rollback until disabled / destroyed).

## Notification Channels

Create channels (email, SMS, PagerDuty, Pub/Sub, etc.) in Cloud Monitoring first. Then pass their resource names:

```bash
variable "notification_channel_ids" { default = ["projects/your-project/notificationChannels/123"] }
```

These will be attached to all provided alert policies.

## Alerts

Two baseline alert policies are provisioned:

1. Ingestion job inactivity (no completed executions in last hour).
2. Dataset freshness placeholder (no table modification signal within a 36h window).

Customize by editing the MQL queries or adding notification channels. For production, replace placeholder freshness logic with a custom metric (e.g., latest partition timestamp exported via metrics job).
