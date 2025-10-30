# Secrets Setup Guide for Oura Pipeline

This guide covers setting up secrets for the Oura Ring data pipeline to work with GitHub Actions and Google Cloud.

## Overview

The Oura pipeline needs:
1. **Oura Personal Access Tokens (PATs)** - One per resident/participant
2. **Google Cloud credentials** - For BigQuery uploads
3. **BigQuery configuration** - Project and dataset info

---

## 1️⃣ Oura Personal Access Tokens

### What You Need

- One Oura Personal Access Token (PAT) for **each resident** you're collecting data from
- These are OAuth tokens that give access to a specific Oura Ring user's data

### How to Get Oura PATs

1. **For each participant:**
   - They need to log into their Oura account at https://cloud.ouraring.com
   - Go to **Personal Access Tokens** (or direct: https://cloud.ouraring.com/personal-access-tokens)
   - Click "Create a new personal access token"
   - Give it a name (e.g., "Durham Environmental Study")
   - Copy the token immediately (you can't see it again!)

2. **Token format:** `YOUR_OURA_PAT_HERE` (long alphanumeric string)

---

## 2️⃣ Local Development Setup

### Option A: Local Files (Recommended for Development)

Create token files **outside your repo** (already configured in `oura_import_options.py`):

```bash
# Create directory structure (adjust path as needed)
mkdir -p "../../../../Secure Files"

# Create a token file for each resident
# Example for resident 3:
echo "PERSONAL_ACCESS_TOKEN=your_actual_oura_pat_here" > "../../../../Secure Files/pat_r3.env"

# Repeat for each resident (r1, r2, r3, etc.)
```

**File structure:**
```
Secure Files/
├── pat_r1.env    # PERSONAL_ACCESS_TOKEN=token_for_resident_1
├── pat_r2.env    # PERSONAL_ACCESS_TOKEN=token_for_resident_2
├── pat_r3.env    # PERSONAL_ACCESS_TOKEN=token_for_resident_3
└── ...
```

### Option B: Environment Variables (Alternative)

Set environment variables for local testing:

```bash
export OURA_PAT_R1="token_for_resident_1"
export OURA_PAT_R2="token_for_resident_2"
# etc.
```

Then modify `oura_collector.py` to read from these env vars instead of files.

---

## 3️⃣ Google Secret Manager Setup

For production Cloud Run/Cloud Scheduler deployments, store secrets in Google Secret Manager.

### Create Secrets in GCP

```bash
# Set your project
export PROJECT_ID="durham-weather-466502"  # or your project

# Store each resident's Oura token
echo -n "actual_token_for_resident_1" | \
  gcloud secrets create oura-pat-r1 \
    --data-file=- \
    --project=$PROJECT_ID

echo -n "actual_token_for_resident_2" | \
  gcloud secrets create oura-pat-r2 \
    --data-file=- \
    --project=$PROJECT_ID

# Repeat for each resident (oura-pat-r3, oura-pat-r4, etc.)
```

### Grant Access to Service Account

```bash
# Get your Cloud Run service account
SA_EMAIL="your-service-account@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant access to all Oura secrets
for i in {1..14}; do
  gcloud secrets add-iam-policy-binding oura-pat-r${i} \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor" \
    --project=$PROJECT_ID
done
```

### Update Cloud Run Job to Use Secrets

When deploying your Oura collection job:

```bash
gcloud run jobs update oura-data-collector \
  --region=us-central1 \
  --project=$PROJECT_ID \
  --set-secrets="OURA_PAT_R1=oura-pat-r1:latest,OURA_PAT_R2=oura-pat-r2:latest,OURA_PAT_R3=oura-pat-r3:latest" \
  # ... add all residents
```

Or in `cloudbuild.yaml`:

```yaml
- name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
  entrypoint: 'gcloud'
  args:
    - 'run'
    - 'jobs'
    - 'create'
    - 'oura-data-collector'
    - '--image=${_IMAGE}'
    - '--region=us-central1'
    - '--set-secrets=OURA_PAT_R1=oura-pat-r1:latest,OURA_PAT_R2=oura-pat-r2:latest,OURA_PAT_R3=oura-pat-r3:latest'
    - '--set-env-vars=BQ_PROJECT=${PROJECT_ID},BQ_DATASET=oura,BQ_LOCATION=US'
```

---

## 4️⃣ GitHub Actions / Secrets

For GitHub Actions to run your pipeline (e.g., scheduled runs), add secrets to your repository.

### Add Secrets to GitHub Repository

1. Go to: `https://github.com/AlainS7/durham-environmental-monitoring/settings/secrets/actions`
2. Click **"New repository secret"**
3. Add these secrets:

#### Required Secrets:

| Secret Name | Value | Description |
|------------|-------|-------------|
| `GCP_PROJECT_ID` | `durham-weather-466502` | Your GCP project ID |
| `GCP_SA_KEY` | `{...json key...}` | Service account JSON key for GCP auth |
| `BQ_DATASET` | `oura` | BigQuery dataset name |
| `OURA_PAT_R1` | `actual_token_1` | Oura PAT for resident 1 |
| `OURA_PAT_R2` | `actual_token_2` | Oura PAT for resident 2 |
| `OURA_PAT_R3` | `actual_token_3` | Oura PAT for resident 3 |
| ... | ... | One per resident |

#### Get GCP Service Account Key:

```bash
# Create a service account for GitHub Actions
gcloud iam service-accounts create github-actions-oura \
  --display-name="GitHub Actions - Oura Pipeline" \
  --project=$PROJECT_ID

SA_EMAIL="github-actions-oura@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant permissions
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/bigquery.jobUser"

# Create and download key (DO NOT COMMIT THIS!)
gcloud iam service-accounts keys create github-sa-key.json \
  --iam-account=$SA_EMAIL \
  --project=$PROJECT_ID

# Copy the contents of github-sa-key.json and paste into GitHub secret GCP_SA_KEY
# Then delete the local file:
rm github-sa-key.json
```

### Example GitHub Actions Workflow

Create `.github/workflows/oura-daily-collect.yml`:

```yaml
name: Oura Daily Data Collection

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  workflow_dispatch:  # Manual trigger

env:
  BQ_PROJECT: ${{ secrets.GCP_PROJECT_ID }}
  BQ_DATASET: ${{ secrets.BQ_DATASET }}
  BQ_LOCATION: US

jobs:
  collect-oura-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      
      - name: Authenticate to Google Cloud
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
      
      - name: Create token files
        run: |
          mkdir -p /tmp/secure_files
          echo "PERSONAL_ACCESS_TOKEN=${{ secrets.OURA_PAT_R1 }}" > /tmp/secure_files/pat_r1.env
          echo "PERSONAL_ACCESS_TOKEN=${{ secrets.OURA_PAT_R2 }}" > /tmp/secure_files/pat_r2.env
          echo "PERSONAL_ACCESS_TOKEN=${{ secrets.OURA_PAT_R3 }}" > /tmp/secure_files/pat_r3.env
          # Add more as needed
      
      - name: Run Oura collection with BigQuery export
        run: |
          # Update config to use temp directory
          python -c "
          import sys
          sys.path.insert(0, 'oura-rings')
          from oura_import_options import PATHS, OPTIONS
          PATHS['env_files_dir'] = '/tmp/secure_files'
          OPTIONS['export_to_bigquery'] = True
          OPTIONS['bq_dry_run'] = False
          "
          
          python -m oura_rings.cli \
            --residents 1 2 3 \
            --export-bq \
            --no-dry-run
      
      - name: Cleanup token files
        if: always()
        run: rm -rf /tmp/secure_files
```

---

## 5️⃣ BigQuery Setup

### Environment Variables Needed

Set these in your environment (GitHub secrets or local):

| Variable | Example | Required? | Description |
|----------|---------|-----------|-------------|
| `BQ_PROJECT` | `durham-weather-466502` | Yes (for upload) | GCP project ID |
| `BQ_DATASET` | `oura` | No (default: "oura") | BigQuery dataset name |
| `BQ_LOCATION` | `US` | No (default: "US") | BigQuery region |

### Create BigQuery Dataset

```bash
bq mk --dataset \
  --location=US \
  --description="Oura Ring health metrics" \
  ${PROJECT_ID}:oura
```

### Expected Tables (Auto-created)

The pipeline will automatically create these tables:
- `oura_daily_sleep` - Sleep metrics per resident per day
- `oura_daily_activity` - Activity metrics per resident per day
- `oura_daily_readiness` - Readiness metrics per resident per day

---

## 6️⃣ Testing Your Setup

### Test Locally (Dry Run)

```bash
# Set config to use your local token files
cd oura-rings

# Edit oura_import_options.py:
# RESIDENTS_TO_PROCESS = [1]  # Test with one resident
# OPTIONS['export_to_bigquery'] = True
# OPTIONS['bq_dry_run'] = True  # Dry run first!

# Run
python -m oura_rings.cli --residents 1 --export-bq --dry-run
```

Expected output:
```
✅ Successfully processed resident 1
BigQuery export (dry_run=True): {'oura_daily_sleep': 30, 'oura_daily_activity': 30, ...}
```

### Test Real BigQuery Upload

```bash
# Ensure you have GCP credentials
gcloud auth application-default login

# Set env vars
export BQ_PROJECT="durham-weather-466502"
export BQ_DATASET="oura"

# Run with real upload
python -m oura_rings.cli --residents 1 --export-bq --no-dry-run
```

### Verify in BigQuery

```sql
-- Check data was uploaded
SELECT 
  resident,
  COUNT(*) as days,
  MIN(day) as first_day,
  MAX(day) as last_day
FROM `durham-weather-466502.oura.oura_daily_sleep`
GROUP BY resident
ORDER BY resident;
```

---

## 🔒 Security Checklist

Before going to production:

- [ ] ✅ Pre-commit hook installed (`.git/hooks/pre-commit`)
- [ ] ✅ All Oura PATs stored in Secret Manager (not in code)
- [ ] ✅ GCP service account has minimal permissions (BigQuery only)
- [ ] ✅ GitHub secrets configured (not in `.env` files in repo)
- [ ] ✅ `.gitignore` excludes `pat_r*.env`, `*.env` (except `.env.sample`)
- [ ] ✅ Token files stored outside repository
- [ ] ✅ No actual tokens in `oura_import_options.py` (empty list)
- [ ] ✅ Tested dry-run mode works
- [ ] ✅ Tested real BigQuery upload with one resident

---

## 📋 Quick Reference

### Secrets Summary

```
# Local Development:
../../../../Secure Files/pat_r1.env    → PERSONAL_ACCESS_TOKEN=xxx
../../../../Secure Files/pat_r2.env    → PERSONAL_ACCESS_TOKEN=xxx

# Google Secret Manager:
oura-pat-r1    → actual_token_1
oura-pat-r2    → actual_token_2
oura-pat-r3    → actual_token_3

# GitHub Secrets:
OURA_PAT_R1    → actual_token_1
OURA_PAT_R2    → actual_token_2
GCP_SA_KEY     → {...service account JSON...}
GCP_PROJECT_ID → durham-weather-466502
BQ_DATASET     → oura
```

### Commands Quick Copy

```bash
# Create local token file
echo "PERSONAL_ACCESS_TOKEN=YOUR_TOKEN" > "../../../../Secure Files/pat_r1.env"

# Create GCP secret
echo -n "YOUR_TOKEN" | gcloud secrets create oura-pat-r1 --data-file=- --project=$PROJECT_ID

# Test locally
python -m oura_rings.cli --residents 1 --export-bq --dry-run

# Deploy to Cloud Run
gcloud run jobs update oura-collector --set-secrets="OURA_PAT_R1=oura-pat-r1:latest"
```

---

## 🆘 Troubleshooting

### "No access token available"
- Check token file exists: `ls "../../../../Secure Files/pat_r1.env"`
- Check file contents: `cat "../../../../Secure Files/pat_r1.env"`
- Verify format: `PERSONAL_ACCESS_TOKEN=xxxxx` (no quotes, no spaces)

### "Permission denied" in BigQuery
- Verify service account has `roles/bigquery.dataEditor` and `roles/bigquery.jobUser`
- Check dataset exists: `bq ls --project_id=$PROJECT_ID`
- Verify credentials: `gcloud auth application-default print-access-token`

### "Secret not found" in Cloud Run
- Check secret exists: `gcloud secrets list --project=$PROJECT_ID | grep oura`
- Verify IAM binding: `gcloud secrets get-iam-policy oura-pat-r1 --project=$PROJECT_ID`
- Check Cloud Run job config: `gcloud run jobs describe oura-collector --format=yaml | grep secrets`

---

## Need Help?

- Oura API docs: https://cloud.ouraring.com/v2/docs
- GCP Secret Manager: https://cloud.google.com/secret-manager/docs
- BigQuery: https://cloud.google.com/bigquery/docs
