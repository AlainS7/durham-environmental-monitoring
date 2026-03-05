#!/usr/bin/env python3
"""Upload curated research-pack artifacts to SharePoint/Teams."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sync_parquet_to_sharepoint import SharePointUploader, get_sharepoint_access_token


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upload curated research-pack files to SharePoint.")
    parser.add_argument("--input-dir", required=True, help="Base directory containing <date>/ research files.")
    parser.add_argument("--date", required=True, help="Date partition in YYYY-MM-DD format.")
    parser.add_argument(
        "--scope-folder",
        default="_research_pack",
        help="SharePoint scope folder under base path (default: _research_pack).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview uploads without writing files.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date_dir = Path(args.input_dir).expanduser().resolve() / args.date
    if not date_dir.exists() or not date_dir.is_dir():
        print(f"Research-pack directory not found: {date_dir}", file=sys.stderr)
        return 2

    files = sorted([p for p in date_dir.iterdir() if p.is_file()])
    if not files:
        print(f"No research-pack files found in: {date_dir}", file=sys.stderr)
        return 2

    site_id = os.getenv("SHAREPOINT_SITE_ID")
    drive_id = os.getenv("SHAREPOINT_DRIVE_ID")
    if not site_id or not drive_id:
        print("SHAREPOINT_SITE_ID and SHAREPOINT_DRIVE_ID must be set.", file=sys.stderr)
        return 2

    base_folder = os.getenv(
        "SHAREPOINT_FOLDER_PATH",
        "/Data - Environmental/Google Cloud Sensor Data",
    )
    try:
        access_token = get_sharepoint_access_token()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    uploader = SharePointUploader(access_token, site_id, drive_id, base_folder=base_folder)

    success = 0
    for file_path in files:
        content = file_path.read_bytes()
        if uploader.upload_file(content, file_path.name, args.scope_folder, args.date, args.dry_run):
            success += 1

    if success != len(files):
        print(f"Uploaded {success}/{len(files)} research-pack files.", file=sys.stderr)
        return 1

    print(f"Uploaded {success}/{len(files)} research-pack files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
