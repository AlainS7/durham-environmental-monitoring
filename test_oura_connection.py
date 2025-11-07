#!/usr/bin/env python3
"""
Quick test script to verify Oura Ring API connection.
Tests connectivity using the first available PAT token.
"""

import sys
from pathlib import Path
from datetime import date, timedelta

# Add oura-rings to path
sys.path.insert(0, str(Path(__file__).parent / "oura-rings"))

from oura_client import OuraClient


def load_token_from_env_file(env_file_path: Path) -> str | None:
    """Extract PERSONAL_ACCESS_TOKEN from .env file."""
    try:
        with open(env_file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("PERSONAL_ACCESS_TOKEN="):
                    return line.split("=", 1)[1]
    except FileNotFoundError:
        return None
    return None


def test_oura_connection(resident_num: int = 1):
    """Test Oura API connection with a specific resident's token."""

    # Try to load PAT token
    pats_dir = Path(__file__).parent / "oura-rings" / "pats"
    pat_file = pats_dir / f"pat_r{resident_num}.env"

    print(f"🔍 Looking for PAT file: {pat_file}")

    if not pat_file.exists():
        print(f"❌ PAT file not found: {pat_file}")
        return False

    token = load_token_from_env_file(pat_file)

    if not token:
        print(f"❌ Failed to extract token from {pat_file}")
        return False

    print(f"✓ Token loaded successfully (length: {len(token)} chars)")
    print()

    # Test API connection
    print(f"🔗 Testing Oura API connection for Resident {resident_num}...")
    print("-" * 60)

    try:
        with OuraClient(personal_access_token=token) as client:
            # Get last 7 days of sleep data as a simple test
            end_date = date.today()
            start_date = end_date - timedelta(days=7)

            print(f"📅 Fetching sleep data from {start_date} to {end_date}")

            sleep_data = client.get_daily_sleep(
                start_date=str(start_date), end_date=str(end_date)
            )

            print(f"✅ SUCCESS! Retrieved {len(sleep_data)} days of sleep data")
            print()

            if sleep_data:
                print("📊 Sample data (first entry):")
                print("-" * 60)
                sample = sleep_data[0]
                print(f"  Date: {sample.get('day', 'N/A')}")
                print(f"  Sleep Score: {sample.get('score', 'N/A')}")
                print(
                    f"  Total Sleep Duration: {sample.get('contributors', {}).get('total_sleep_duration', 'N/A')} seconds"
                )
                print(
                    f"  Deep Sleep: {sample.get('contributors', {}).get('deep_sleep', 'N/A')} seconds"
                )
                print(
                    f"  REM Sleep: {sample.get('contributors', {}).get('rem_sleep', 'N/A')} seconds"
                )
            else:
                print("⚠️  No sleep data found for this date range")

            print()
            print("=" * 60)
            print("🎉 Oura API connection test PASSED!")
            print("=" * 60)
            return True

    except Exception as e:
        print(f"❌ ERROR: Failed to connect to Oura API")
        print(f"   Error type: {type(e).__name__}")
        print(f"   Error message: {str(e)}")
        print()
        print("=" * 60)
        print("❌ Oura API connection test FAILED")
        print("=" * 60)
        return False


def main():
    """Run the Oura connection test."""
    print()
    print("=" * 60)
    print("OURA RING API CONNECTION TEST")
    print("=" * 60)
    print()

    # Try to test with resident 1, or fall back to first available
    pats_dir = Path(__file__).parent / "oura-rings" / "pats"

    # Find first available PAT file
    available_residents = []
    for pat_file in sorted(pats_dir.glob("pat_r*.env")):
        try:
            resident_num = int(pat_file.stem.replace("pat_r", ""))
            available_residents.append(resident_num)
        except ValueError:
            continue

    if not available_residents:
        print("❌ No PAT files found in oura-rings/pats/")
        print(f"   Searched in: {pats_dir}")
        return 1

    print(f"📋 Found {len(available_residents)} PAT files: {available_residents}")
    print()

    # Test with first available resident
    test_resident = available_residents[0]
    success = test_oura_connection(test_resident)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
