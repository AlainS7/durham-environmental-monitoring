#!/usr/bin/env python3
"""
Sync parquet files from GCS to Microsoft Teams SharePoint.

This script downloads parquet files from the sensor-data-to-bigquery GCS bucket
and uploads them to a Duke SharePoint site accessible via Microsoft Graph API.

Usage:
    # Sync a single day
    python scripts/sync_parquet_to_sharepoint.py --date 2025-12-15

    # Backfill a date range
    python scripts/sync_parquet_to_sharepoint.py --start-date 2025-07-07 --end-date 2025-12-15

    # Dry run to see what would be synced
    python scripts/sync_parquet_to_sharepoint.py --date 2025-12-15 --dry-run

Environment Variables:
    SHAREPOINT_ACCESS_TOKEN: Direct Microsoft Graph bearer token (preferred)
    SHAREPOINT_PAT: Backward-compatible alias for SHAREPOINT_ACCESS_TOKEN
    SHAREPOINT_TENANT_ID: Microsoft Entra tenant ID (for client credentials flow)
    SHAREPOINT_CLIENT_ID: Microsoft Entra app/client ID (for client credentials flow)
    SHAREPOINT_CLIENT_SECRET: Microsoft Entra app client secret (for client credentials flow)
    GCP_PROJECT_ID: Google Cloud project ID (default: durham-weather-466502)
    GCS_BUCKET: GCS bucket name (default: sensor-data-to-bigquery)
    SHAREPOINT_SITE_ID: SharePoint site ID (extracted from site URL)
    SHAREPOINT_DRIVE_ID: Drive ID for the target document library
    SHAREPOINT_FOLDER_PATH: Base folder path in SharePoint (default: /Data - Environmental/Google Cloud Sensor Data)
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional

import requests
from google.cloud import storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


class SharePointUploader:
    """Upload files to SharePoint using Microsoft Graph API."""

    BASE_URL = "https://graph.microsoft.com/v1.0"
    REQUEST_TIMEOUT_SECONDS = 30
    MAX_RETRIES = 5
    SIMPLE_UPLOAD_MAX_BYTES = 4 * 1024 * 1024
    CHUNK_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024

    def __init__(
        self,
        access_token: str,
        site_id: str,
        drive_id: str,
        base_folder: str = "/Data - Environmental/Google Cloud Sensor Data",
    ):
        """
        Initialize SharePoint uploader.

        Args:
            access_token: Microsoft Graph API access token
            site_id: SharePoint site ID
            drive_id: Document library drive ID
            base_folder: Base folder path in SharePoint
        """
        self.access_token = access_token
        self.site_id = site_id
        self.drive_id = drive_id
        self.base_folder = base_folder.strip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }
        )

    def _get_folder_path(self, source: str, date_str: str) -> str:
        """Build SharePoint folder path for a given source and date."""
        return f"{self.base_folder}/{source}/{date_str}"

    @staticmethod
    def _is_transient_status(status_code: int) -> bool:
        """Return True for retryable HTTP status codes."""
        return status_code == 429 or 500 <= status_code < 600

    def _get_retry_delay(self, attempt: int, response: Optional[requests.Response]) -> float:
        """Calculate retry delay with Retry-After support and exponential backoff."""
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return max(float(retry_after), 0.0)
                except ValueError:
                    pass
        return min(2 ** (attempt - 1), 30)

    def _request_with_retry(
        self,
        method: str,
        url: str,
        *,
        use_session: bool = True,
        **kwargs,
    ) -> requests.Response:
        """Make an HTTP request with retries for transient Graph/API failures."""
        requester = self.session.request if use_session else requests.request

        for attempt in range(1, self.MAX_RETRIES + 1):
            response = None
            try:
                response = requester(
                    method,
                    url,
                    timeout=self.REQUEST_TIMEOUT_SECONDS,
                    **kwargs,
                )
            except requests.RequestException as exc:
                if attempt == self.MAX_RETRIES:
                    raise
                delay = self._get_retry_delay(attempt, response)
                log.warning(
                    "Transient request error for %s %s (attempt %s/%s): %s; retrying in %.1fs",
                    method,
                    url,
                    attempt,
                    self.MAX_RETRIES,
                    exc,
                    delay,
                )
                time.sleep(delay)
                continue

            if self._is_transient_status(response.status_code):
                if attempt == self.MAX_RETRIES:
                    return response
                delay = self._get_retry_delay(attempt, response)
                log.warning(
                    "Transient response for %s %s (HTTP %s, attempt %s/%s); retrying in %.1fs",
                    method,
                    url,
                    response.status_code,
                    attempt,
                    self.MAX_RETRIES,
                    delay,
                )
                time.sleep(delay)
                continue

            return response

        raise RuntimeError(f"Failed request to {url} after retries")

    def _upload_file_chunked(
        self, file_content: bytes, folder_path: str, filename: str, file_size_mb: float
    ) -> bool:
        """Upload large files using Microsoft Graph upload session."""
        create_session_url = (
            f"{self.BASE_URL}/sites/{self.site_id}/drives/{self.drive_id}"
            f"/root:/{folder_path}/{filename}:/createUploadSession"
        )
        payload = {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
        session_response = self._request_with_retry(
            "POST",
            create_session_url,
            json=payload,
        )

        if session_response.status_code not in (200, 201):
            log.error(
                f"✗ Failed to create upload session for {filename}: "
                f"{session_response.status_code} - {session_response.text}"
            )
            return False

        try:
            upload_url = session_response.json()["uploadUrl"]
        except (ValueError, KeyError):
            log.error(f"✗ Upload session response missing uploadUrl for {filename}")
            return False

        file_size = len(file_content)
        for start in range(0, file_size, self.CHUNK_UPLOAD_SIZE_BYTES):
            end = min(start + self.CHUNK_UPLOAD_SIZE_BYTES, file_size) - 1
            chunk = file_content[start : end + 1]
            headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{file_size}",
            }
            chunk_response = self._request_with_retry(
                "PUT",
                upload_url,
                use_session=False,
                headers=headers,
                data=chunk,
            )

            if chunk_response.status_code in (200, 201):
                log.info(
                    f"✓ Uploaded {filename} ({file_size_mb:.2f} MB) to {folder_path} using upload session"
                )
                return True

            if chunk_response.status_code == 202:
                continue

            log.error(
                f"✗ Failed chunk upload for {filename}: "
                f"{chunk_response.status_code} - {chunk_response.text}"
            )
            return False

        log.error(f"✗ Upload session did not complete for {filename}")
        return False

    def _ensure_folder_exists(self, folder_path: str) -> dict:
        """
        Ensure a folder exists in SharePoint, creating it if necessary.

        Returns the folder's metadata dict.
        """
        # Try to get the folder first
        url = f"{self.BASE_URL}/sites/{self.site_id}/drives/{self.drive_id}/root:/{folder_path}"
        response = self._request_with_retry("GET", url)

        if response.status_code == 200:
            return response.json()
        if response.status_code != 404:
            raise Exception(f"Failed to check folder: {response.status_code}")

        # Folder doesn't exist, create it
        # We need to create parent folders recursively
        parts = folder_path.split("/")
        current_path = ""

        for part in parts:
            if not part:
                continue

            parent_path = current_path if current_path else ""
            current_path = f"{current_path}/{part}" if current_path else part

            # Check if this level exists
            check_url = f"{self.BASE_URL}/sites/{self.site_id}/drives/{self.drive_id}/root:/{current_path}"
            check_response = self._request_with_retry("GET", check_url)

            if check_response.status_code == 200:
                continue
            if check_response.status_code != 404:
                raise Exception(f"Failed to check folder level: {check_response.status_code}")

            # Create this folder level
            if parent_path:
                create_url = f"{self.BASE_URL}/sites/{self.site_id}/drives/{self.drive_id}/root:/{parent_path}:/children"
            else:
                create_url = f"{self.BASE_URL}/sites/{self.site_id}/drives/{self.drive_id}/root/children"

            payload = {
                "name": part,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "replace",
            }

            create_response = self._request_with_retry(
                "POST",
                create_url,
                json=payload,
            )
            if create_response.status_code not in (200, 201):
                log.error(f"Failed to create folder {part}: {create_response.text}")
                raise Exception(
                    f"Failed to create folder: {create_response.status_code}"
                )

        # Get the final folder metadata
        final_url = f"{self.BASE_URL}/sites/{self.site_id}/drives/{self.drive_id}/root:/{folder_path}"
        final_response = self._request_with_retry("GET", final_url)

        if final_response.status_code != 200:
            raise Exception(
                f"Failed to get folder after creation: {final_response.status_code}"
            )

        return final_response.json()

    def upload_file(
        self,
        file_content: bytes,
        filename: str,
        source: str,
        date_str: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Upload a file to SharePoint.

        Args:
            file_content: File content as bytes
            filename: Name of the file (e.g., TSI-2025-12-15.parquet)
            source: Data source (TSI or WU)
            date_str: Date string (YYYY-MM-DD)
            dry_run: If True, don't actually upload

        Returns:
            True if upload successful, False otherwise
        """
        folder_path = self._get_folder_path(source, date_str)
        file_size_mb = len(file_content) / (1024 * 1024)

        if dry_run:
            log.info(
                f"[DRY RUN] Would upload {filename} ({file_size_mb:.2f} MB) to {folder_path}"
            )
            return True

        try:
            # Ensure folder exists
            self._ensure_folder_exists(folder_path)

            if len(file_content) > self.SIMPLE_UPLOAD_MAX_BYTES:
                return self._upload_file_chunked(
                    file_content, folder_path, filename, file_size_mb
                )

            # Upload file using simple upload
            upload_url = (
                f"{self.BASE_URL}/sites/{self.site_id}/drives/{self.drive_id}"
                f"/root:/{folder_path}/{filename}:/content"
            )

            # Remove Content-Type for file upload
            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            response = self._request_with_retry(
                "PUT",
                upload_url,
                use_session=False,
                headers=headers,
                data=file_content,
            )

            if response.status_code in (200, 201):
                log.info(
                    f"✓ Uploaded {filename} ({file_size_mb:.2f} MB) to {folder_path}"
                )
                return True
            else:
                log.error(
                    f"✗ Failed to upload {filename}: {response.status_code} - {response.text}"
                )
                return False

        except Exception as e:
            log.error(f"✗ Exception uploading {filename}: {e}")
            return False


class GCSDownloader:
    """Download parquet files from Google Cloud Storage."""

    def __init__(self, bucket_name: str, prefix: str = "raw"):
        """
        Initialize GCS downloader.

        Args:
            bucket_name: GCS bucket name
            prefix: Prefix path in bucket (default: raw)
        """
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)
        self.prefix = prefix.strip("/")

    def list_parquet_files(self, source: str, date_str: str) -> List[str]:
        """
        List parquet files for a given source and date.

        Args:
            source: Data source (TSI or WU)
            date_str: Date string (YYYY-MM-DD)

        Returns:
            List of blob names
        """
        # Path format: raw/source=TSI/agg=raw/dt=2025-12-15/TSI-2025-12-15.parquet
        prefix = f"{self.prefix}/source={source}/agg=raw/dt={date_str}/"
        blobs = self.bucket.list_blobs(prefix=prefix)
        return [blob.name for blob in blobs if blob.name.endswith(".parquet")]

    def download_file(self, blob_name: str) -> bytes:
        """
        Download a file from GCS.

        Args:
            blob_name: Full blob path in bucket

        Returns:
            File content as bytes
        """
        blob = self.bucket.blob(blob_name)
        return blob.download_as_bytes()


def parse_date(date_str: str) -> datetime:
    """Parse a date string in YYYY-MM-DD format."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date format: {date_str}. Expected YYYY-MM-DD")


def get_date_range(start_date: str, end_date: str) -> List[str]:
    """
    Generate a list of date strings between start and end dates (inclusive).

    Args:
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)

    Returns:
        List of date strings
    """
    start = parse_date(start_date)
    end = parse_date(end_date)

    if start > end:
        raise ValueError(f"Start date {start_date} is after end date {end_date}")

    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    return dates


def get_sharepoint_access_token(
    auth_session: Optional[requests.Session] = None,
) -> str:
    """Resolve a Graph access token from direct token env vars or client credentials."""
    direct_token = (
        os.getenv("SHAREPOINT_ACCESS_TOKEN") or os.getenv("SHAREPOINT_PAT") or ""
    ).strip()
    if direct_token:
        return direct_token

    tenant_id = (os.getenv("SHAREPOINT_TENANT_ID") or "").strip()
    client_id = (os.getenv("SHAREPOINT_CLIENT_ID") or "").strip()
    client_secret = (os.getenv("SHAREPOINT_CLIENT_SECRET") or "").strip()

    missing_client_vars = [
        name
        for name, value in (
            ("SHAREPOINT_TENANT_ID", tenant_id),
            ("SHAREPOINT_CLIENT_ID", client_id),
            ("SHAREPOINT_CLIENT_SECRET", client_secret),
        )
        if not value
    ]
    if missing_client_vars:
        raise RuntimeError(
            "SharePoint auth is not configured. Direct token mode is missing "
            "SHAREPOINT_ACCESS_TOKEN and SHAREPOINT_PAT (set either one). "
            "Client credentials mode is missing: "
            f"{', '.join(missing_client_vars)}."
        )

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_payload = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    }
    session = auth_session or requests.Session()

    try:
        token_response = session.post(token_url, data=token_payload, timeout=30)
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Failed to request Graph token from Microsoft Entra endpoint ({token_url}): {exc}"
        ) from exc

    if token_response.status_code != 200:
        error_detail = token_response.text
        try:
            error_json = token_response.json()
            error = error_json.get("error")
            error_description = error_json.get("error_description")
            if error or error_description:
                error_detail = f"{error}: {error_description}"
        except ValueError:
            pass

        raise RuntimeError(
            "Failed to obtain Microsoft Graph token via client credentials "
            f"(HTTP {token_response.status_code}): {error_detail}"
        )

    try:
        token_data = token_response.json()
    except ValueError as exc:
        raise RuntimeError(
            "Microsoft Entra token endpoint returned non-JSON response."
        ) from exc

    access_token = token_data.get("access_token")
    if not access_token:
        raise RuntimeError(
            "Microsoft Entra token response did not include access_token."
        )

    return access_token


def write_json_artifact(artifact_path: Path, payload: dict[str, Any]) -> bytes:
    """Write a JSON artifact to disk and return its byte content."""
    artifact_bytes = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    artifact_path.write_bytes(artifact_bytes)
    log.info(f"Wrote artifact: {artifact_path}")
    return artifact_bytes


def sync_date(
    gcs: GCSDownloader,
    sharepoint: SharePointUploader,
    date_str: str,
    sources: List[str],
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Sync parquet files for a specific date.

    Args:
        gcs: GCS downloader instance
        sharepoint: SharePoint uploader instance
        date_str: Date string (YYYY-MM-DD)
        sources: List of data sources to sync (e.g., ['TSI', 'WU'])
        dry_run: If True, don't actually upload

    Returns:
        Tuple of (success_count, total_count)
    """
    success_count = 0
    total_count = 0
    manifest_entries: list[dict[str, Any]] = []
    missing_source_files: list[str] = []

    for source in sources:
        try:
            blob_names = gcs.list_parquet_files(source, date_str)

            if not blob_names:
                log.warning(f"No parquet files found for {source} on {date_str}")
                missing_source_files.append(source)
                continue

            for blob_name in blob_names:
                total_count += 1
                filename = Path(blob_name).name
                file_metadata: dict[str, Any] = {
                    "source": source,
                    "date": date_str,
                    "gcs_blob_path": f"gs://{gcs.bucket.name}/{blob_name}",
                    "filename": filename,
                    "size_bytes": None,
                    "upload_status": "pending",
                    "error": None,
                }

                log.info(f"Downloading {source}/{date_str}/{filename}...")
                try:
                    file_content = gcs.download_file(blob_name)
                    file_metadata["size_bytes"] = len(file_content)
                except Exception as e:
                    file_metadata["upload_status"] = "download_failed"
                    file_metadata["error"] = str(e)
                    manifest_entries.append(file_metadata)
                    log.error(f"Error downloading {blob_name}: {e}")
                    continue

                if sharepoint.upload_file(file_content, filename, source, date_str, dry_run):
                    success_count += 1
                    file_metadata["upload_status"] = "dry_run" if dry_run else "uploaded"
                else:
                    file_metadata["upload_status"] = "upload_failed"
                    file_metadata["error"] = "Upload failed"

                manifest_entries.append(file_metadata)

        except Exception as e:
            log.error(f"Error syncing {source} for {date_str}: {e}")
            missing_source_files.append(source)

    generated_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    manifest_payload = {
        "date": date_str,
        "generated_at_utc": generated_at,
        "files": manifest_entries,
    }
    health_payload = {
        "date": date_str,
        "generated_at_utc": generated_at,
        "totals": {
            "files": total_count,
            "successful_uploads": success_count,
            "failed_uploads": total_count - success_count,
        },
        "missing_source_files": sorted(set(missing_source_files)),
    }

    manifest_path = Path.cwd() / f"sync_manifest_{date_str}.json"
    health_path = Path.cwd() / f"sync_health_{date_str}.json"
    manifest_bytes = write_json_artifact(manifest_path, manifest_payload)
    health_bytes = write_json_artifact(health_path, health_payload)

    artifact_uploads = (
        (manifest_bytes, manifest_path.name, "_artifacts/manifests"),
        (health_bytes, health_path.name, "_artifacts/health"),
    )
    for artifact_bytes, artifact_name, artifact_folder in artifact_uploads:
        if not sharepoint.upload_file(
            artifact_bytes, artifact_name, artifact_folder, date_str, dry_run
        ):
            log.error(
                f"✗ Failed to upload artifact {artifact_name} to {artifact_folder}/{date_str}"
            )

    return success_count, total_count


def extract_sharepoint_ids(sharepoint_url: str) -> tuple[str, str]:
    """
    Extract site ID and drive ID from SharePoint URL.

    This is a placeholder - in practice, you'll need to use the Graph API
    to resolve the site URL to site ID and drive ID.

    For now, these should be provided as environment variables.
    """
    # This would require additional Graph API calls to resolve
    # For simplicity, we'll require these as env vars
    raise NotImplementedError(
        "Please set SHAREPOINT_SITE_ID and SHAREPOINT_DRIVE_ID environment variables.\n"
        "To find these, use Graph Explorer: https://developer.microsoft.com/en-us/graph/graph-explorer\n"
        "Query: GET https://graph.microsoft.com/v1.0/sites/{hostname}:/sites/{site-path}\n"
        "Then: GET https://graph.microsoft.com/v1.0/sites/{site-id}/drives"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Sync parquet files from GCS to SharePoint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Date arguments
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument(
        "--date",
        help="Single date to sync (YYYY-MM-DD)",
    )
    date_group.add_argument(
        "--start-date",
        help="Start date for range sync (YYYY-MM-DD, requires --end-date)",
    )

    parser.add_argument(
        "--end-date",
        help="End date for range sync (YYYY-MM-DD, requires --start-date)",
    )

    parser.add_argument(
        "--sources",
        nargs="+",
        default=["TSI", "WU"],
        help="Data sources to sync (default: TSI WU)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be synced without uploading",
    )

    parser.add_argument(
        "--gcs-bucket",
        default=os.getenv("GCS_BUCKET", "sensor-data-to-bigquery"),
        help="GCS bucket name (default: sensor-data-to-bigquery)",
    )

    parser.add_argument(
        "--gcs-prefix",
        default="raw",
        help="GCS prefix path (default: raw)",
    )

    args = parser.parse_args()

    # Validate date range arguments
    if args.start_date and not args.end_date:
        parser.error("--start-date requires --end-date")
    if args.end_date and not args.start_date:
        parser.error("--end-date requires --start-date")

    # Get dates to sync
    if args.date:
        dates = [args.date]
    else:
        dates = get_date_range(args.start_date, args.end_date)

    # Get SharePoint credentials
    try:
        sharepoint_access_token = get_sharepoint_access_token()
    except RuntimeError as exc:
        log.error(str(exc))
        sys.exit(1)

    sharepoint_site_id = os.getenv("SHAREPOINT_SITE_ID")
    sharepoint_drive_id = os.getenv("SHAREPOINT_DRIVE_ID")

    if not sharepoint_site_id or not sharepoint_drive_id:
        log.error(
            "SHAREPOINT_SITE_ID and SHAREPOINT_DRIVE_ID environment variables must be set.\n"
            "Use Graph Explorer to find these: https://developer.microsoft.com/en-us/graph/graph-explorer\n"
            "1. GET https://graph.microsoft.com/v1.0/sites/prodduke.sharepoint.com:/sites/DistributedUrbanHeatAirqualityMapping\n"
            "2. GET https://graph.microsoft.com/v1.0/sites/{site-id}/drives"
        )
        sys.exit(1)

    sharepoint_folder = os.getenv(
        "SHAREPOINT_FOLDER_PATH", "/Data - Environmental/Google Cloud Sensor Data"
    )

    # Initialize clients
    log.info(f"Initializing GCS downloader (bucket: {args.gcs_bucket})...")
    gcs = GCSDownloader(args.gcs_bucket, args.gcs_prefix)

    log.info(f"Initializing SharePoint uploader (folder: {sharepoint_folder})...")
    sharepoint = SharePointUploader(
        sharepoint_access_token,
        sharepoint_site_id,
        sharepoint_drive_id,
        sharepoint_folder,
    )

    # Sync files
    if args.dry_run:
        log.info("=== DRY RUN MODE ===")

    log.info(f"Syncing {len(dates)} date(s) for sources: {', '.join(args.sources)}")

    total_success = 0
    total_files = 0

    for i, date_str in enumerate(dates, 1):
        log.info(f"[{i}/{len(dates)}] Syncing {date_str}...")
        success, total = sync_date(
            gcs, sharepoint, date_str, args.sources, args.dry_run
        )
        total_success += success
        total_files += total

        if total > 0:
            log.info(f"  → {success}/{total} files synced successfully")

    # Summary
    log.info("=" * 60)
    log.info(f"Sync complete: {total_success}/{total_files} files synced successfully")

    if total_success < total_files:
        log.warning(
            f"Some files failed to sync ({total_files - total_success} failures)"
        )
        sys.exit(1)

    log.info("All files synced successfully! ✓")


if __name__ == "__main__":
    main()
