#!/bin/bash
# This script is executed after the container is created.

echo "Starting post-create setup..."

# Install Google Cloud CLI
echo "Installing Google Cloud CLI..."
sudo apt-get update && sudo apt-get install -y lsb-release apt-transport-https ca-certificates gnupg

sudo mkdir -p /usr/share/keyrings
curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg
echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | sudo tee /etc/apt/sources.list.d/google-cloud-sdk.list
sudo apt-get update && sudo apt-get install -y google-cloud-cli

# Create and activate a virtual environment
echo "Creating Python virtual environment in .venv..."
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

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


echo "Post-create setup complete."

# Ensure PYTHONPATH is set for all shells in Codespace
echo 'export PYTHONPATH=$PWD' >> ~/.bashrc
echo 'export PYTHONPATH=$PWD' >> ~/.zshrc
echo 'export PYTHONPATH=$PWD' >> /etc/profile.d/pythonpath.sh
chmod +x /etc/profile.d/pythonpath.sh
