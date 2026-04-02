#!/usr/bin/env bash
set -euo pipefail

# Idempotently ensure required secrets exist, then add new versions.
# Usage:
#   export WU_API_KEY=...
#   export TSI_CLIENT_ID=...
#   export TSI_CLIENT_SECRET=...
#   export TSI_AUTH_URL=...
#   ./scripts/create_secrets.sh --project <PROJECT_ID>

PROJECT_ID=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --project)
      PROJECT_ID="${2:-}"
      shift 2
      ;;
    -h|--help)
      sed -n '1,24p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$PROJECT_ID" ]]; then
  echo "--project is required" >&2
  exit 2
fi

prompt_secret() {
  local var_name="$1"
  local prompt="$2"
  if [[ -z "${!var_name:-}" ]]; then
    read -r -s -p "$prompt: " "$var_name"
    echo
  fi
  if [[ -z "${!var_name:-}" ]]; then
    echo "$var_name cannot be empty" >&2
    exit 3
  fi
}

ensure_secret() {
  local secret_name="$1"
  if ! gcloud secrets describe "$secret_name" --project "$PROJECT_ID" >/dev/null 2>&1; then
    echo "Creating secret: $secret_name"
    gcloud secrets create "$secret_name" --replication-policy="automatic" --project "$PROJECT_ID" >/dev/null
  fi
}

add_version() {
  local secret_name="$1"
  local secret_value="$2"
  printf "%s" "$secret_value" | gcloud secrets versions add "$secret_name" --data-file=- --project "$PROJECT_ID" >/dev/null
  echo "Added new version to: $secret_name"
}

prompt_secret "WU_API_KEY" "Enter WU_API_KEY"
prompt_secret "TSI_CLIENT_ID" "Enter TSI_CLIENT_ID"
prompt_secret "TSI_CLIENT_SECRET" "Enter TSI_CLIENT_SECRET"
prompt_secret "TSI_AUTH_URL" "Enter TSI_AUTH_URL"

ensure_secret "wu_api_key"
ensure_secret "tsi_client_id"
ensure_secret "tsi_client_secret"
ensure_secret "tsi_auth_url"

add_version "wu_api_key" "$WU_API_KEY"
add_version "tsi_client_id" "$TSI_CLIENT_ID"
add_version "tsi_client_secret" "$TSI_CLIENT_SECRET"
add_version "tsi_auth_url" "$TSI_AUTH_URL"

echo "Done. Secrets are ensured and versioned in project: $PROJECT_ID"
