#!/bin/bash
# This script is executed after the container is created.

echo "Starting post-create setup..."

# Install Google Cloud CLI
echo "Installing Google Cloud CLI..."
sudo apt-get update && sudo apt-get install -y lsb-release apt-transport-https ca-certificates gnupg

echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee -a /etc/apt/sources.list.d/google-cloud-sdk.list

curl https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key --keyring /usr/share/keyrings/cloud.google.gpg add -

sudo apt-get update && sudo apt-get install -y google-cloud-cli

# Create and activate a virtual environment
echo "Creating Python virtual environment in .venv..."
python3 -m venv .venv
source .venv/bin/activate


# Install uv (fast Python package manager)
echo "Installing uv..."
pip install uv

# Install Python dependencies using uv inside the venv
echo "Installing Python dependencies from requirements.txt and requirements-dev.txt using uv in venv..."
uv pip install -r requirements.txt
if [ -f "requirements-dev.txt" ]; then
    uv pip install -r requirements-dev.txt
fi

# Ensure ruff is installed (redundant if in requirements, but safe)
uv pip install ruff

# Install supervisord and Cloud SQL Auth Proxy if not already installed
if ! command -v supervisord &> /dev/null; then
  pip install supervisor
fi

# Determine the system's OS and architecture
OS=$(uname -s)
ARCH=$(uname -m)

# Map architecture to Cloud SQL Auth Proxy naming conventions
if [ "$ARCH" = "x86_64" ]; then
  ARCH="amd64"
elif [ "$ARCH" = "arm64" ]; then
  ARCH="arm64"
fi

# Set the download URL based on the OS and architecture
if [ "$OS" = "Linux" ]; then
  PROXY_URL="https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.10.1/cloud-sql-proxy.linux.$ARCH"
elif [ "$OS" = "Darwin" ]; then
  PROXY_URL="https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.10.1/cloud-sql-proxy.darwin.$ARCH"
else
  echo "Unsupported OS: $OS"
  exit 1
fi

# Install Cloud SQL Auth Proxy if not already installed
if ! command -v cloud-sql-proxy &> /dev/null; then
  sudo curl -o /usr/local/bin/cloud-sql-proxy "$PROXY_URL"
  sudo chmod +x /usr/local/bin/cloud-sql-proxy
fi

# Ensure the Cloud SQL Proxy wrapper script is executable
chmod +x /workspaces/tsi-data-uploader/.devcontainer/start-cloud-sql-proxy.sh


# Authenticate with GCP using service account key from Codespace secret
echo "Authenticating with GCP using service account key from Codespace secret..."
if [ -z "$GCP_SERVICE_ACCOUNT_KEY_DB_ACCESS" ]; then
  echo "ERROR: GCP_SERVICE_ACCOUNT_KEY_DB_ACCESS environment variable is not set. Please add your service account JSON key as a Codespace secret."
  exit 1
fi
echo "$GCP_SERVICE_ACCOUNT_KEY_DB_ACCESS" | base64 -d > /tmp/gcp-sa-key.json
gcloud auth activate-service-account --key-file=/tmp/gcp-sa-key.json

# Set GCP project and derive DATABASE_URL from structured prod-db-credentials secret
echo "Setting GCP project and deriving DATABASE_URL from prod-db-credentials secret..."
gcloud config set project durham-weather-466502

# The application code now uses the JSON secret prod-db-credentials directly via DB_CREDS_SECRET_ID.
# We still export DATABASE_URL here purely for developer convenience (manual psql/sqlalchemy usage).
# The old standalone DATABASE_URL secret is deprecated and can be deleted after confirming no other tooling depends on it.
if command -v jq >/dev/null 2>&1; then
  CREDS_JSON="$(gcloud secrets versions access latest --secret=prod-db-credentials 2>/dev/null || true)"
  if [ -n "$CREDS_JSON" ] && echo "$CREDS_JSON" | jq -e 'type=="object" and has("DB_USER") and has("DB_PASSWORD") and has("DB_HOST") and has("DB_PORT") and has("DB_NAME")' >/dev/null 2>&1; then
    export DATABASE_URL="$(echo "$CREDS_JSON" | jq -r '"postgresql://\(.DB_USER):\(.DB_PASSWORD)@\(.DB_HOST):\(.DB_PORT)/\(.DB_NAME)"')"
    echo "Derived DATABASE_URL for local convenience."
    printf "export DATABASE_URL='%s'\n" "$DATABASE_URL" >> ~/.bashrc
  else
    echo "WARNING: prod-db-credentials secret missing required keys; skipping DATABASE_URL export." >&2
  fi
else
  echo "jq not installed; skipping DATABASE_URL derivation." >&2
fi

# Start supervisord with the config (will manage cloud-sql-proxy)
# supervisord -c /workspaces/tsi-data-uploader/.devcontainer/supervisord.conf

echo "Post-create setup complete."

# Ensure PYTHONPATH is set for all shells in Codespace
echo 'export PYTHONPATH=$PWD' >> ~/.bashrc
echo 'export PYTHONPATH=$PWD' >> ~/.zshrc
echo 'export PYTHONPATH=$PWD' >> /etc/profile.d/pythonpath.sh
chmod +x /etc/profile.d/pythonpath.sh
echo "--------------------------------------------------------"
echo "To connect to your database:"
echo "1. Make sure you have set the GCP_SERVICE_ACCOUNT_KEY Codespace secret with your service account JSON key."
echo "2. The container will automatically authenticate to GCP and fetch secrets."
echo "3. Start the Cloud SQL Auth Proxy when needed:"
echo "   supervisord -c /workspaces/tsi-data-uploader/.devcontainer/supervisord.conf"
echo "   or"
echo "   .devcontainer/start-cloud-sql-proxy.sh"
echo "For more information, visit: https://cloud.google.com/sql/docs/mysql/connect-auth-proxy"
echo "--------------------------------------------------------"
