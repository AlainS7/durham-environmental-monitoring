#!/usr/bin/env bash
set -euo pipefail

# Bootstrap infrastructure: (optionally) create Artifact Registry repo, build images, terraform init/apply, pin digests.
# Usage: ./scripts/bootstrap_infra.sh \
#          --project <PROJECT_ID> \
#          --bucket <GCS_BUCKET> \
#          [--region us-central1] \
#          [--repo weather-maintenance-images] \
#          [--create-repo] \
#          [--pin]
#
# Requires: gcloud (authenticated), terraform, docker (for local build if using Cloud Build submit), and Cloud Build API enabled.

PROJECT=""; REGION="us-central1"; REPO="weather-maintenance-images"; BUCKET=""; CREATE_REPO=0; CREATE_BUCKET=0; PIN=0; DATASET="sensors"

while [[ $# -gt 0 ]]; do
  case $1 in
    --project) PROJECT=$2; shift 2;;
    --bucket) BUCKET=$2; shift 2;;
    --region) REGION=$2; shift 2;;
    --repo) REPO=$2; shift 2;;
    --create-repo) CREATE_REPO=1; shift;;
  --pin) PIN=1; shift;;
  --create-bucket) CREATE_BUCKET=1; shift;;
    -h|--help) sed -n '1,40p' "$0"; exit 0;;
    *) echo "Unknown arg: $1" >&2; exit 1;;
  esac
done

if [[ -z "$PROJECT" || -z "$BUCKET" ]]; then
  echo "--project and --bucket required" >&2; exit 2
fi

echo "[bootstrap] Project=$PROJECT Region=$REGION Repo=$REPO Bucket=$BUCKET Dataset=$DATASET"

echo "[bootstrap] Enabling required services (idempotent)"
gcloud services enable \
  artifactregistry.googleapis.com \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com \
  bigquery.googleapis.com \
  storage.googleapis.com \
  --project "$PROJECT" >/dev/null

if [[ $CREATE_BUCKET -eq 1 ]]; then
  echo "[bootstrap] Ensuring GCS bucket exists"
  gsutil ls -p "$PROJECT" gs://$BUCKET >/dev/null 2>&1 || \
    gsutil mb -p "$PROJECT" -l "$REGION" gs://$BUCKET
fi

if [[ $CREATE_REPO -eq 1 ]]; then
  echo "[bootstrap] Ensuring Artifact Registry repo exists";
  gcloud artifacts repositories describe "$REPO" --location="$REGION" --project "$PROJECT" >/dev/null 2>&1 || \
    gcloud artifacts repositories create "$REPO" --repository-format=DOCKER --location="$REGION" --project "$PROJECT" --description "Sensor ingestion & maintenance images";
fi

echo "[bootstrap] Submitting Cloud Build multi-image build"
gcloud builds submit --config=cloudbuild.multi.yaml --substitutions _REGION=$REGION,_REPO=$REPO --project "$PROJECT"

cd infra/terraform
echo "[bootstrap] Terraform init"
terraform init -input=false

echo "[bootstrap] Terraform apply (latest tags)"
terraform apply -auto-approve \
  -var project_id="$PROJECT" -var region="$REGION" \
  -var gcs_bucket="$BUCKET" -var bq_dataset="$DATASET" \
  -var ingestion_image="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/ingestion:latest" \
  -var refresh_image="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/refresh-partitions:latest" \
  -var metrics_image="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/record-metrics:latest"

if [[ $PIN -eq 1 ]]; then
  echo "[bootstrap] Pinning digests"
  cd ../.. # back to repo root
  ./scripts/pin_image_digests.sh "$PROJECT" "$REGION" "$REPO" > /tmp/pin_cmd.txt
  echo "Review and run the following to pin (if script succeeded):"
  grep terraform /tmp/pin_cmd.txt || echo "(pin script did not produce command)"
else
  echo "[bootstrap] Skipping pin step (use --pin to enable)"
fi

echo "[bootstrap] Done"