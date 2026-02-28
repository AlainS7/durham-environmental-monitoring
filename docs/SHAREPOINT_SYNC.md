# SharePoint Sync Documentation

This document describes the automated system for syncing parquet data files from Google Cloud Storage to Microsoft Teams SharePoint.

## Overview

The SharePoint sync system automatically downloads daily parquet files (TSI and Weather Underground data) from the GCS bucket `sensor-data-to-bigquery` and uploads them to the Duke SharePoint site for team access, local analysis, and backup.

**Key Features:**

- ✅ Automated daily sync at 08:45 UTC (15 minutes after quality checks)
- ✅ Manual backfill support for historical data
- ✅ Dry-run mode for testing
- ✅ Maintains organized folder structure by source and date
- ✅ ~3-4 MB per day of new data
- ✅ Supports multiple data sources (TSI, WU)

**SharePoint Destination:**

```
Data - Environmental/Google Cloud Sensor Data/
├── TSI/
│   ├── 2025-07-07/
│   │   └── TSI-2025-07-07.parquet
│   ├── 2025-07-08/
│   │   └── TSI-2025-07-08.parquet
│   └── ...
└── WU/
    ├── 2025-07-07/
    │   └── WU-2025-07-07.parquet
    ├── 2025-07-08/
    │   └── WU-2025-07-08.parquet
    └── ...
```

## Prerequisites

1. **SharePoint Site Access**: Team members need access to:
   - Site: `prodduke.sharepoint.com/sites/DistributedUrbanHeatAirqualityMapping`
   - Folder: `Data - Environmental/Google Cloud Sensor Data`

2. **Microsoft Graph API Credentials**: You'll need:
   - SharePoint Personal Access Token (PAT) or App Registration
   - SharePoint Site ID
   - Drive ID

## Setup Instructions

### Step 1: Get SharePoint Site ID and Drive ID

You'll need to use Microsoft Graph Explorer to find these IDs:

1. **Go to Graph Explorer**: https://developer.microsoft.com/en-us/graph/graph-explorer

2. **Sign in** with your Duke credentials

3. **Get Site ID**:

   ```
   GET https://graph.microsoft.com/v1.0/sites/prodduke.sharepoint.com:/sites/DistributedUrbanHeatAirqualityMapping
   ```

   Look for the `id` field in the response (format: `prodduke.sharepoint.com,<guid>,<guid>`)

4. **Get Drive ID**:

   ```
   GET https://graph.microsoft.com/v1.0/sites/{site-id}/drives
   ```

   Look for the drive with name "Documents" or "Shared Documents" and note its `id`

### Step 2: Create Personal Access Token (PAT)

**Option A: Using Azure AD App Registration (Recommended for Production)**

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Click **New registration**
   - Name: `Durham Weather Data Sync`
   - Supported account types: `Accounts in this organizational directory only`
   - Redirect URI: Leave blank
4. Click **Register**
5. Note the **Application (client) ID**
6. Go to **Certificates & secrets** → **New client secret**
   - Description: `GitHub Actions SharePoint Sync`
   - Expires: Choose appropriate duration (recommend 12 months)
   - Click **Add**
7. **Copy the secret value immediately** (you won't be able to see it again)
8. Go to **API permissions** → **Add a permission**
   - Choose **Microsoft Graph** → **Application permissions**
   - Add: `Sites.ReadWrite.All` or `Files.ReadWrite.All`
   - Click **Grant admin consent**

**Option B: Using Personal Access Token (Simpler, but less secure)**

For academic/development use, you can use a delegated access token:

1. Go to [Graph Explorer](https://developer.microsoft.com/en-us/graph/graph-explorer)
2. Sign in with your Duke account
3. Click **Access Token** tab
4. Copy the access token (valid for ~1 hour, needs refresh)

⚠️ **Note**: PATs expire quickly. For automated workflows, use Option A (App Registration).

### Step 3: Add Secrets to GitHub Repository

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** and add the following:

| Secret Name           | Description                               | Example Value                                     |
| --------------------- | ----------------------------------------- | ------------------------------------------------- |
| `SHAREPOINT_PAT`      | Access token or client secret from Step 2 | `eyJ0eXAiOi...` (App Registration) or token value |
| `SHAREPOINT_SITE_ID`  | Site ID from Step 1                       | `prodduke.sharepoint.com,abc123...,def456...`     |
| `SHAREPOINT_DRIVE_ID` | Drive ID from Step 1                      | `b!Abc123...`                                     |

**Existing Secrets** (should already be configured):

- `GCP_SA_KEY_JSON` - GCP service account credentials
- `GCP_WORKLOAD_IDENTITY_PROVIDER` - For GCP authentication
- `GCP_VERIFIER_SA` - Service account email

### Step 4: Verify Configuration

Test the setup locally before running GitHub Actions:

```bash
# Set environment variables
export SHAREPOINT_PAT="your-token-here"
export SHAREPOINT_SITE_ID="your-site-id-here"
export SHAREPOINT_DRIVE_ID="your-drive-id-here"
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/gcp-credentials.json"

# Test with dry run for a single recent date
python scripts/sync_parquet_to_sharepoint.py \
  --date 2026-02-11 \
  --dry-run

# If dry run looks good, try actual sync
python scripts/sync_parquet_to_sharepoint.py \
  --date 2026-02-11
```

Expected output:

```
2026-02-12 10:30:00 [INFO] Initializing GCS downloader (bucket: sensor-data-to-bigquery)...
2026-02-12 10:30:00 [INFO] Initializing SharePoint uploader...
2026-02-12 10:30:00 [INFO] Syncing 1 date(s) for sources: TSI, WU
2026-02-12 10:30:01 [INFO] [1/1] Syncing 2026-02-11...
2026-02-12 10:30:01 [INFO] Downloading TSI/2026-02-11/TSI-2026-02-11.parquet...
2026-02-12 10:30:03 [INFO] ✓ Uploaded TSI-2026-02-11.parquet (3.42 MB) to Data - Environmental/Google Cloud Sensor Data/TSI/2026-02-11
...
2026-02-12 10:30:08 [INFO] Sync complete: 2/2 files synced successfully
```

## Usage

### Daily Automatic Sync

The daily sync runs **automatically at 08:45 UTC** via GitHub Actions (workflow: `sync-to-sharepoint.yml`).

**Timeline:**

- 06:45 UTC - Data collection (Cloud Run job)
- 07:25 UTC - SQL transformations
- 08:30 UTC - Data quality checks
- **08:45 UTC - SharePoint sync** ← Automated

You can view the sync status:

1. Go to **Actions** tab in GitHub
2. Look for **Daily SharePoint Sync** workflow
3. Check the latest run for status and logs

### Manual Sync for Specific Date

Sync a specific date manually:

1. Go to **Actions** → **Daily SharePoint Sync**
2. Click **Run workflow**
3. Fill in parameters:
   - Date: `2026-02-11` (YYYY-MM-DD)
   - Sources: `TSI WU` (default)
   - Dry run: Check if you want to preview first
4. Click **Run workflow**

### Historical Backfill

To sync historical data (e.g., all data since 2025-07-07):

1. Go to **Actions** → **Backfill SharePoint (Historical Data)**
2. Click **Run workflow**
3. Fill in parameters:
   - Start date: `2025-07-07`
   - End date: `2026-02-11`
   - Sources: `TSI WU`
   - Dry run: **Recommended first run**
4. Click **Run workflow**

**Performance Note**: Backfilling ~220 days (~373 MB) takes approximately 5-10 minutes.

### Local Command-Line Usage

```bash
# Sync single day
make sync-sharepoint-today

# Sync specific date
python scripts/sync_parquet_to_sharepoint.py --date 2026-02-11

# Backfill date range
make sync-sharepoint-backfill START=2025-07-07 END=2026-02-11

# Or directly:
python scripts/sync_parquet_to_sharepoint.py \
  --start-date 2025-07-07 \
  --end-date 2026-02-11 \
  --sources TSI WU
```

## Accessing Synced Files

### Via Teams Desktop/Web

1. Open Microsoft Teams
2. Navigate to your team: **Distributed Urban Heat & Air Quality Mapping**
3. Go to **Files** tab
4. Browse to: `Data - Environmental/Google Cloud Sensor Data/`
5. Download files as needed

### Via OneDrive Sync

1. In Teams Files tab, click **Sync**
2. Files will sync to: `~/OneDrive - Duke University/Distributed Urban Heat.../Shared Documents/Data - Environmental/`
3. Access files locally without repeated downloads

### Via Python (for Analysis)

Once synced, team members can access via OneDrive sync:

```python
import pandas as pd
from pathlib import Path

# Assuming OneDrive sync is enabled
base_path = Path.home() / "OneDrive - Duke University" / \
    "Distributed Urban Heat & Air Quality Mapping" / \
    "Shared Documents" / "Data - Environmental" / \
    "Google Cloud Sensor Data"

# Load TSI data for a specific date
tsi_file = base_path / "TSI" / "2026-02-11" / "TSI-2026-02-11.parquet"
df = pd.read_parquet(tsi_file)

print(f"Loaded {len(df)} rows from {tsi_file.name}")
print(df.head())
```

## Monitoring and Troubleshooting

### Check Sync Status

**Via GitHub Actions:**

1. Go to **Actions** tab
2. Check **Daily SharePoint Sync** runs
3. Green checkmark = success, Red X = failure
4. Click on a run to see detailed logs

**Via SharePoint:**

1. Browse to the SharePoint folder
2. Check file count and dates
3. Most recent should be yesterday's date

### Common Issues

#### Issue: "SHAREPOINT_PAT environment variable not set"

**Solution:**

- Ensure `SHAREPOINT_PAT` is added to GitHub repository secrets
- For local runs, set the environment variable: `export SHAREPOINT_PAT="..."`

#### Issue: "Failed to create folder: 403 Forbidden"

**Solution:**

- PAT/token lacks permissions
- Ensure API permissions include `Sites.ReadWrite.All` or `Files.ReadWrite.All`
- For App Registration, ensure admin consent is granted

#### Issue: "Failed to upload file: 401 Unauthorized"

**Solution:**

- Token expired (PATs expire after ~1 hour)
- For App Registration, generate a new client secret
- Update `SHAREPOINT_PAT` secret in GitHub

#### Issue: "No parquet files found for {source} on {date}"

**Solution:**

- Data may not exist for that date in GCS
- Check if data collection ran successfully for that date
- Verify GCS bucket path: `gs://sensor-data-to-bigquery/raw/source={SOURCE}/agg=raw/dt={DATE}/`

#### Issue: Files upload slowly or timeout

**Solution:**

- Large backfills (>100 days) may take time
- Break into smaller date ranges (e.g., monthly batches)
- Check network connectivity in GitHub Actions runner

### Debug Mode

Enable detailed logging:

```bash
# Set Python logging to DEBUG
export PYTHONUNBUFFERED=1

python scripts/sync_parquet_to_sharepoint.py \
  --date 2026-02-11 \
  --dry-run 2>&1 | tee sync-debug.log
```

### Re-uploading Files

If files need to be re-uploaded (e.g., corruption or schema fix):

1. Simply re-run the sync for that date
2. SharePoint will overwrite existing files
3. No need to manually delete first

```bash
# Re-upload a specific date
python scripts/sync_parquet_to_sharepoint.py --date 2026-02-11
```

## File Size and Storage

**Current Usage:**

- Historical data (2025-07-07 to present): ~373 MB
- Daily increment: ~3-4 MB/day
- Projected annual: ~1.1-1.5 GB/year

**Team Storage:**

- Available: ~3 TB
- SharePoint quota should be more than sufficient

**Compression:**

- Files use Snappy compression (Parquet default)
- Provides good balance of size and read performance
- No additional compression needed

## Security Notes

1. **Token Storage**: All tokens are stored as encrypted GitHub secrets
2. **Access Control**: Only repository collaborators can trigger workflows
3. **Token Rotation**: Rotate tokens periodically (recommend every 6-12 months)
4. **Audit Trail**: All uploads are logged in GitHub Actions runs
5. **Least Privilege**: Tokens only have file write permissions, not full SharePoint admin

## Support

For issues or questions:

1. Check [Troubleshooting](#monitoring-and-troubleshooting) section above
2. Review GitHub Actions logs for detailed error messages
3. Contact repository maintainers: [@AlainS7](https://github.com/AlainS7)
4. Open an issue in the repository with logs attached

## Related Documentation

- [System Architecture](SYSTEM_ARCHITECTURE.md)
- [Automated Pipeline Overview](AUTOMATED_PIPELINE_OVERVIEW.md)
- [Data Quality Monitoring](TSI-Data-Quality-Monitoring.md)
- [Local Development Guide](LOCAL_DEVELOPMENT.md)
