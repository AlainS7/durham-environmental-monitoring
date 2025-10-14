#!/bin/bash
# Fetch the instance connection name from Secret Manager
PROJECT_ID="${GCP_PROJECT_ID:-durham-weather-466502}"  # <-- Set your GCP project ID here or via env var
SECRET_NAME="${INSTANCE_CONNECTION_NAME_SECRET:-postgresql_INSTANCE_CONNECTION_NAME}"  # <-- Set your secret name here or via env var

if ! command -v /usr/local/bin/cloud-sql-proxy &> /dev/null; then
  echo "Error: /usr/local/bin/cloud-sql-proxy not found. Please ensure it is installed."
  exit 1
fi

echo "Fetching Cloud SQL instance connection name from Secret Manager..."
INSTANCE_CONNECTION_NAME=$(gcloud secrets versions access latest --secret="$SECRET_NAME" --project="$PROJECT_ID")

# Start the Cloud SQL Auth Proxy
exec /usr/local/bin/cloud-sql-proxy --address 0.0.0.0 "$INSTANCE_CONNECTION_NAME"