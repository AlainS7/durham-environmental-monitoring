#!/usr/bin/env bash
set -euo pipefail

# Fetch digests for ingestion, refresh, metrics images and output terraform apply command.
# Usage:
#   ./scripts/pin_image_digests.sh <PROJECT_ID> [REGION] [REPO] [TAG]
# If TAG provided, pin the digest corresponding to that tag (fails if tag not found).

PROJECT_ID=${1:?"PROJECT_ID required"}
REGION=${2:-us-central1}
REPO=${3:-weather-maintenance-images}
TAG_FILTER=${4:-}

function latest_digest() {
  local image=$1
  if [[ -n "$TAG_FILTER" ]]; then
    # List all tags and digests, filter exact tag match
    gcloud artifacts docker images list ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${image} \
      --format='value(DIGEST, TAGS)' \
      --sort-by=~CREATE_TIME | awk -v tag="$TAG_FILTER" 'index($2, tag) {print $1; exit}'
  else
    gcloud artifacts docker images list ${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${image} \
      --format='value(DIGEST)' \
      --sort-by=~CREATE_TIME | head -n1
  fi
}

INGEST_DIGEST=$(latest_digest ingestion || true)
REFRESH_DIGEST=$(latest_digest refresh-partitions || true)
METRICS_DIGEST=$(latest_digest record-metrics || true)

if [[ -z "$INGEST_DIGEST" || -z "$REFRESH_DIGEST" || -z "$METRICS_DIGEST" ]]; then
  if [[ -n "$TAG_FILTER" ]]; then
    echo "Failed to find one or more digests for tag '$TAG_FILTER'." >&2
  else
    echo "One or more digests missing. Ensure images are built (cloudbuild.multi.yaml)." >&2
  fi
  exit 1
fi

BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"

if [[ -n "$TAG_FILTER" ]]; then
  echo "# Tag -> digest resolution (tag: $TAG_FILTER)" >&2
fi
echo "# Apply with pinned digests:" >&2
echo "terraform apply \"-var=ingestion_image=${BASE}/ingestion@${INGEST_DIGEST}\" \\
  \"-var=refresh_image=${BASE}/refresh-partitions@${REFRESH_DIGEST}\" \\
  \"-var=metrics_image=${BASE}/record-metrics@${METRICS_DIGEST}\"" 