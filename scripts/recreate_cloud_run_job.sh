#!/usr/bin/env bash
set -euo pipefail

# Recreate the Cloud Run Job from scratch if 'gcloud run jobs describe' shows a null template
# or env vars refuse to persist. This will DELETE the existing job first.
#
# Prereqs:
#  - gcloud auth login (or workload identity) with run.admin + artifactregistry.writer (if pushing image)
#  - PROJECT_ID set below or via environment
#  - IMAGE already built & pushed OR build via the optional block

PROJECT_ID=${PROJECT_ID:-durham-weather-466502}
# Some shells / copy-paste operations can yield PROJECT_ID like 'PROJECT_ID=durham-weather-466502'.
# Sanitize by stripping leading 'PROJECT_ID=' if present.
if [[ "$PROJECT_ID" == PROJECT_ID=* ]]; then
  PROJECT_ID="${PROJECT_ID#PROJECT_ID=}"
fi
if [[ -z "$PROJECT_ID" ]]; then
  echo "[recreate][fatal] PROJECT_ID is empty after sanitization" >&2
  exit 1
fi
REGION=${REGION:-us-east1}
JOB_NAME=${JOB_NAME:-weather-data-uploader}

# Artifact Registry repo (adjust if different). Existing repo confirmed earlier: weather-data-images
# To create (only if missing):
#   gcloud artifacts repositories create weather-data-images \
#     --repository-format=docker --location=us-east1 \
#     --description="Docker repository for weather data images"
REPO_NAME=${REPO_NAME:-weather-data-images}
IMAGE_TAG=${IMAGE_TAG:-latest}
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${JOB_NAME}:${IMAGE_TAG}"

# Env vars
ENV_VARS=(
  PROJECT_ID=${PROJECT_ID}
  TSI_CREDS_SECRET_ID=tsi_creds
  WU_API_KEY_SECRET_ID=wu_api_key
  GCS_BUCKET=sensor-data-to-bigquery
  GCS_PREFIX=raw
  BQ_PROJECT=${PROJECT_ID}
  BQ_DATASET=sensors
  BQ_LOCATION=US
  DISABLE_BQ_STAGING=1
  DISABLE_DB_SINK=1
  LOG_LEVEL=INFO
)

echo "[recreate] Project: $PROJECT_ID Region: $REGION Job: $JOB_NAME"
gcloud config set project "$PROJECT_ID" >/dev/null 2>&1 || true
echo "[recreate] Image: $IMAGE"

# Optional build & push (uncomment if you want to rebuild locally)
# echo "[recreate] Building image locally..."
# docker build -t "$IMAGE" .
# gcloud auth configure-docker ${REGION}-docker.pkg.dev -q
# docker push "$IMAGE"

echo "[recreate] Deleting existing job (if present)" || true
gcloud run jobs delete "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" --quiet || true

echo "[recreate] Creating job with env vars"
JOINED=$(IFS=,; echo "${ENV_VARS[*]}")
echo "[recreate] Env var list: $JOINED"
gcloud run jobs create "$JOB_NAME" \
  --image "$IMAGE" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --set-env-vars="$JOINED" \
  --execution-environment=gen2

# Some environments ignore env vars on create intermittently; force an explicit update to ensure persistence.
echo "[recreate] Forcing env var persistence with explicit update"
gcloud run jobs update "$JOB_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --update-env-vars "$JOINED" \
  --execution-environment=gen2 || true

echo "[recreate] Job created. Verifying env vars..."
gcloud run jobs describe "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" \
  --format="table(template.template.containers[0].env[].name, template.template.containers[0].env[].value)" || true

# Fallback JSON dump (helps if table path changes in future gcloud versions)
ENV_JSON=$(gcloud run jobs describe "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" --format=json | sed 's/\\n/ /g') || true
echo "$ENV_JSON" | grep -q '"env"' || echo "[recreate][warn] Could not locate env array via describe format; dumping JSON snippet:" && \
  echo "$ENV_JSON" | grep -E 'env|image' | head -n 50 || true

echo "[recreate] Test execute (no date args)"
gcloud run jobs execute "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" --wait || true

echo "[recreate] Recent logs (tail)"
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=$JOB_NAME" \
  --project "$PROJECT_ID" --limit=50 --format='value(textPayload)' | tail -n 50 || true

echo "[recreate] Done. To run for a specific date:"
echo "gcloud run jobs execute $JOB_NAME --region $REGION --project $PROJECT_ID --args=\"--start=2025-08-30\",\"--end=2025-08-30\" --wait"
