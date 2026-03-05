# SharePoint Sync Runbook

This runbook documents the production SharePoint sync path implemented by `scripts/sync_parquet_to_sharepoint.py` and the related GitHub Actions workflows.

## Quick answer: Do I need a PAT?

**No for production automation.**
Use Microsoft Entra app registration credentials (`SHAREPOINT_TENANT_ID`, `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_CLIENT_SECRET`) for unattended runs.

Use `SHAREPOINT_ACCESS_TOKEN` (or legacy `SHAREPOINT_PAT`) only as a fallback for local/manual runs.

## Authentication modes supported by `sync_parquet_to_sharepoint.py`

| Mode | Environment variables | Recommended use | Notes |
|---|---|---|---|
| Entra app registration (client credentials) | `SHAREPOINT_TENANT_ID`, `SHAREPOINT_CLIENT_ID`, `SHAREPOINT_CLIENT_SECRET` | **Production automation** | Script requests a Graph token at runtime. |
| Direct bearer token fallback | `SHAREPOINT_ACCESS_TOKEN` or `SHAREPOINT_PAT` | Local/manual troubleshooting | Token lifetime is short; avoid for unattended schedules. |

Auth resolution order in script:
1. `SHAREPOINT_ACCESS_TOKEN`
2. `SHAREPOINT_PAT` (legacy alias)
3. Client-credentials token request using tenant/client/secret

If a direct token is set, it takes precedence over app-registration credentials.

## Professional sync scope (include/exclude)

Canonical policy is maintained in `config/sharepoint_sync_scope.json`.

### Included scope

- **Raw parquet (active in daily sync):**
  - `raw/source={SOURCE}/agg=raw/dt={YYYY-MM-DD}/*.parquet` for `TSI` and `WU`
- **Manifest + health artifacts (active in daily sync):**
  - `_artifacts/manifests/{YYYY-MM-DD}/sync_manifest_{YYYY-MM-DD}.json`
  - `_artifacts/health/{YYYY-MM-DD}/sync_health_{YYYY-MM-DD}.json`
- **Curated research pack (active in daily sync):**
  - `reports/curated/daily/**/*.{parquet,csv}`
  - `reports/curated/hourly/**/*.{parquet,csv}`
  - `config/sensor_name_map.csv`, `config/generated/**/*.json`
  - Daily workflow currently exports and uploads:
    - `daily_source_summary.csv`
    - `hourly_pm25_temp_humidity_summary.csv`
    - `metadata.json`

### Excluded scope

- `staging/**`
- `**/internal/**`
- `raw/**/full_table_dumps/**`
- `**/*_full_table*.parquet`

## GitHub Actions secrets matrix

Add these in **Settings → Secrets and variables → Actions**.

### Repository variables

| Name | Required | Purpose |
|---|---|---|
| `GCP_PROJECT_ID` | Yes | GCP project used by workflows |
| `GCS_BUCKET` | Yes | Source bucket (default `sensor-data-to-bigquery`) |

### Repository secrets

| Area | Name | Required | When |
|---|---|---|---|
| SharePoint | `SHAREPOINT_SITE_ID` | Yes | Always |
| SharePoint | `SHAREPOINT_DRIVE_ID` | Yes | Always |
| SharePoint (recommended) | `SHAREPOINT_TENANT_ID` | Yes | App-registration mode |
| SharePoint (recommended) | `SHAREPOINT_CLIENT_ID` | Yes | App-registration mode |
| SharePoint (recommended) | `SHAREPOINT_CLIENT_SECRET` | Yes | App-registration mode |
| SharePoint (fallback) | `SHAREPOINT_ACCESS_TOKEN` | Optional | Direct token mode |
| SharePoint (legacy fallback) | `SHAREPOINT_PAT` | Optional | Direct token mode |
| GCP | `GCP_WORKLOAD_IDENTITY_PROVIDER` | Yes | Always |
| GCP | `GCP_VERIFIER_SA` | Yes | Always |
| Alerts | `TEAMS_WEBHOOK_URL` | Optional* | Used by alert-enabled workflows (daily sync); not used by backfill by default |

\* Workflows continue without Teams notification when `TEAMS_WEBHOOK_URL` is unset; `backfill-sharepoint.yml` is intentionally not Teams-notified by default.

## Setup checklist (reliable workflow + Teams notifications)

1. **Create/confirm Entra app registration (recommended):**
   - Grant Microsoft Graph application permission (`Sites.ReadWrite.All` or `Files.ReadWrite.All`).
   - Grant admin consent.
   - Record tenant ID, client ID, and client secret value.
2. **Resolve SharePoint IDs once:**
   - Site ID: `GET /v1.0/sites/prodduke.sharepoint.com:/sites/DistributedUrbanHeatAirqualityMapping`
   - Drive ID: `GET /v1.0/sites/{site-id}/drives`
3. **Configure GitHub variables/secrets from the matrix above.**
4. **Avoid mixed auth confusion:**
   - If using app-registration mode, leave `SHAREPOINT_ACCESS_TOKEN`/`SHAREPOINT_PAT` empty.
5. **Set Teams webhook secret:**
   - Create Incoming Webhook in the target Teams channel.
   - Save URL as `TEAMS_WEBHOOK_URL` repository secret.
6. **Run a manual dry run:**
   - Trigger `Daily SharePoint Sync` with `dry_run=true`.
   - Confirm preflight passes and target date resolves correctly.
7. **Run a real sync validation date:**
   - Trigger one known-good date and confirm files in SharePoint.
8. **Verify notification path:**
   - Confirm workflow failures produce Teams cards (failure steps are guarded by `TEAMS_WEBHOOK_URL != ''`).

## Local/manual execution

```bash
# Recommended local auth: app registration
export SHAREPOINT_TENANT_ID="<tenant-id>"
export SHAREPOINT_CLIENT_ID="<client-id>"
export SHAREPOINT_CLIENT_SECRET="<client-secret>"

# Required SharePoint target IDs
export SHAREPOINT_SITE_ID="<site-id>"
export SHAREPOINT_DRIVE_ID="<drive-id>"

# Optional fallback token mode
# export SHAREPOINT_ACCESS_TOKEN="<graph-bearer-token>"
# export SHAREPOINT_PAT="<legacy-token-alias>"

uv run python scripts/sync_parquet_to_sharepoint.py --date 2026-02-11 --dry-run
uv run python scripts/sync_parquet_to_sharepoint.py --date 2026-02-11
```

## Operations summary

- **Daily automation:** `.github/workflows/sync-to-sharepoint.yml` (08:45 UTC)
- **Historical backfill:** `.github/workflows/backfill-sharepoint.yml`
- **Failure notifications:** `scripts/notify_teams.py` invoked on failure for alert-enabled sync workflows (not historical backfill by default)
- **Curated export tooling:** `scripts/export_curated_research_pack.py` + `scripts/upload_research_pack_to_sharepoint.py`

## Quick troubleshooting

- **Auth not configured:** confirm either app-registration triple or direct token fallback is present.
- **403 Forbidden:** app/token lacks Graph permissions or admin consent.
- **401 Unauthorized:** token invalid/expired (common in direct token mode).
- **No parquet files found:** verify source/date exists in `gs://sensor-data-to-bigquery/raw/source={SOURCE}/agg=raw/dt={DATE}/`.

## Related docs

- `docs/Monitoring-Alerts.md`
- `docs/DAILY_AUTOMATION.md`
- `docs/ARCHITECTURE_OVERVIEW.md`
