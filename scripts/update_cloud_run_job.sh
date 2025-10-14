#!/usr/bin/env bash
set -euo pipefail

# Purpose: One-shot atomic update of Cloud Run Job environment variables required for ingestion.
# Edit the VARIABLE VALUES section then run:
#   bash scripts/update_cloud_run_job.sh
# Requires: gcloud auth with deploy perms, project set (or pass --project flag)

JOB_NAME="weather-data-uploader"
REGION="us-east1"   # adjust if different
PROJECT="durham-weather-466502"  # set explicitly to avoid PROJECT_ID=None in container

# VARIABLE VALUES (plain values; DO NOT use KEY=VALUE literal strings copied from console)
PROJECT_ID="$PROJECT"
TSI_CREDS_SECRET_ID="tsi_creds"
WU_API_KEY_SECRET_ID="wu_api_key"
GCS_BUCKET="sensor-data-to-bigquery"   # existing bucket
GCS_PREFIX="raw"                       # logical prefix (matches workflow expectations)
BQ_PROJECT="$PROJECT"
BQ_DATASET="sensors"
BQ_LOCATION="US"

# Optional run controls
DISABLE_BQ_STAGING="0"   # set to 1 to skip staging table writes

echo "Updating Cloud Run job $JOB_NAME in $PROJECT ($REGION) with required env vars..."

gcloud run jobs update "$JOB_NAME" \
  --region "$REGION" \
  --project "$PROJECT" \
  --set-env-vars "PROJECT_ID=$PROJECT_ID,TSI_CREDS_SECRET_ID=$TSI_CREDS_SECRET_ID,WU_API_KEY_SECRET_ID=$WU_API_KEY_SECRET_ID,GCS_BUCKET=$GCS_BUCKET,GCS_PREFIX=$GCS_PREFIX,BQ_PROJECT=$BQ_PROJECT,BQ_DATASET=$BQ_DATASET,BQ_LOCATION=$BQ_LOCATION,DISABLE_BQ_STAGING=$DISABLE_BQ_STAGING" \
  --execution-environment gen2

echo "(Optional) Set a one-off ingest date for next execution via INGEST_DATE (YYYY-MM-DD)"
echo "Run single-date test example:"
echo "  gcloud run jobs execute $JOB_NAME --region $REGION --project $PROJECT --set-env-vars INGEST_DATE=2025-08-30"

echo "Fetch recent logs (last 50 lines) to verify Config init line:"
echo "  gcloud logs read run.googleapis.com%2Fjobs/$JOB_NAME --project $PROJECT --region $REGION --limit=50 | grep 'Config init' || true"

echo "Done."
