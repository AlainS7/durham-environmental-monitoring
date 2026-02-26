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
    SHAREPOINT_PAT: Personal Access Token for SharePoint/Graph API
    GCP_PROJECT_ID: Google Cloud project ID (default: durham-weather-466502)
    GCS_BUCKET: GCS bucket name (default: sensor-data-to-bigquery)
    SHAREPOINT_SITE_ID: SharePoint site ID (extracted from site URL)
    SHAREPOINT_DRIVE_ID: Drive ID for the target document library
    SHAREPOINT_FOLDER_PATH: Base folder path in SharePoint (default: /Data - Environmental/Google Cloud Sensor Data)
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

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
            access_token: Microsoft Graph API access token (PAT)
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

    def _ensure_folder_exists(self, folder_path: str) -> dict:
        """
        Ensure a folder exists in SharePoint, creating it if necessary.

        Returns the folder's metadata dict.
        """
        # Try to get the folder first
        url = f"{self.BASE_URL}/sites/{self.site_id}/drives/{self.drive_id}/root:/{folder_path}"
        response = self.session.get(url)

        if response.status_code == 200:
            return response.json()

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
            check_response = self.session.get(check_url)

            if check_response.status_code == 200:
                continue

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

            create_response = self.session.post(create_url, json=payload)
            if create_response.status_code not in (200, 201):
                log.error(f"Failed to create folder {part}: {create_response.text}")
                raise Exception(
                    f"Failed to create folder: {create_response.status_code}"
                )

        # Get the final folder metadata
        final_url = f"{self.BASE_URL}/sites/{self.site_id}/drives/{self.drive_id}/root:/{folder_path}"
        final_response = self.session.get(final_url)

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

            # Upload file (using simple upload for files < 4MB, which all our files should be)
            upload_url = (
                f"{self.BASE_URL}/sites/{self.site_id}/drives/{self.drive_id}"
                f"/root:/{folder_path}/{filename}:/content"
            )

            # Remove Content-Type for file upload
            headers = {
                "Authorization": f"Bearer {self.access_token}",
            }

            response = requests.put(upload_url, headers=headers, data=file_content)

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

    for source in sources:
        try:
            blob_names = gcs.list_parquet_files(source, date_str)

            if not blob_names:
                log.warning(f"No parquet files found for {source} on {date_str}")
                continue

            for blob_name in blob_names:
                total_count += 1
                filename = Path(blob_name).name

                log.info(f"Downloading {source}/{date_str}/{filename}...")
                file_content = gcs.download_file(blob_name)

                if sharepoint.upload_file(
                    file_content, filename, source, date_str, dry_run
                ):
                    success_count += 1

        except Exception as e:
            log.error(f"Error syncing {source} for {date_str}: {e}")

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
    sharepoint_pat = os.getenv("SHAREPOINT_PAT")
    if not sharepoint_pat:
        log.error("SHAREPOINT_PAT environment variable not set")
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
        sharepoint_pat,
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
