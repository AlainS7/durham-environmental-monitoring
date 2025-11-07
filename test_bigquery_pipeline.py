#!/usr/bin/env python3
"""
Test script to verify BigQuery pipeline works with NEW data types.
Tests data collection and BigQuery frame building (dry-run).
"""

import sys
from pathlib import Path
from datetime import date, timedelta

sys.path.insert(0, str(Path(__file__).parent / "oura-rings"))

from oura_client import OuraClient
from oura_bigquery_loader import build_daily_frames


def load_token(resident_num=1):
    """Load PAT token from env file."""
    pats_dir = Path(__file__).parent / "oura-rings" / "pats"
    pat_file = pats_dir / f"pat_r{resident_num}.env"

    if not pat_file.exists():
        return None

    with open(pat_file, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("PERSONAL_ACCESS_TOKEN="):
                return line.split("=", 1)[1]
    return None


def test_new_data_types():
    """Test collection and BigQuery frame building for NEW data types."""

    token = load_token(1)
    if not token:
        print("❌ No token found")
        return False

    # Date range for testing (last 7 days)
    end_date = date.today()
    start_date = end_date - timedelta(days=7)

    print("=" * 80)
    print("TESTING NEW DATA TYPES WITH BIGQUERY PIPELINE")
    print("=" * 80)
    print(f"Date range: {start_date} to {end_date}")
    print("Resident: 1")
    print()

    # Collect data
    print("📡 Collecting Oura data...")
    print("-" * 80)

    data = {}

    with OuraClient(personal_access_token=token) as client:
        # Original data types
        print("  ✓ Fetching daily sleep...")
        data["sleep"] = client.get_daily_sleep(
            start_date=str(start_date), end_date=str(end_date)
        )

        print("  ✓ Fetching daily activity...")
        data["activity"] = client.get_daily_activity(
            start_date=str(start_date), end_date=str(end_date)
        )

        print("  ✓ Fetching daily readiness...")
        data["readiness"] = client.get_daily_readiness(
            start_date=str(start_date), end_date=str(end_date)
        )

        # NEW data types
        print("  ✓ Fetching daily SpO2...")
        data["daily_spo2"] = client.get_daily_spo2(
            start_date=str(start_date), end_date=str(end_date)
        )

        print("  ✓ Fetching daily stress...")
        data["daily_stress"] = client.get_daily_stress(
            start_date=str(start_date), end_date=str(end_date)
        )

        print("  ✓ Fetching cardiovascular age...")
        data["daily_cardiovascular_age"] = client.get_daily_cardiovascular_age(
            start_date=str(start_date), end_date=str(end_date)
        )

        # Newly added collections (event-level + heart rate samples)
        print("  ✓ Fetching sleep periods...")
        data["sleep_periods"] = client.get_sleep_periods(
            start_date=str(start_date), end_date=str(end_date)
        )

        print("  ✓ Fetching sessions...")
        data["sessions"] = client.get_sessions(
            start_date=str(start_date), end_date=str(end_date)
        )

        print("  ✓ Fetching workouts...")
        data["workouts"] = client.get_workouts(
            start_date=str(start_date), end_date=str(end_date)
        )

        print("  ✓ Fetching heart rate samples...")
        data["heart_rate"] = client.get_heart_rate(
            start_date=str(start_date), end_date=str(end_date)
        )

    print()
    print("📊 Data Collection Summary:")
    print("-" * 80)
    for data_type, records in data.items():
        count = len(records) if records else 0
        status = "✅" if count > 0 else "⚠️ "
        print(f"  {status} {data_type:<30} {count:>3} records")

    print()
    print("🔄 Building BigQuery DataFrames...")
    print("-" * 80)

    try:
        frames = build_daily_frames(data, resident_no=1)

        print("✅ Successfully built DataFrames!")
        print()
        print("📋 BigQuery Tables Preview:")
        print("-" * 80)

        for table_name, df in frames.items():
            print(f"\n📊 Table: oura_{table_name}")
            print(f"   Rows: {len(df)}")
            print(f"   Columns: {', '.join(df.columns[:10])}")
            if len(df.columns) > 10:
                print(f"            ... and {len(df.columns) - 10} more")

            if not df.empty:
                print("\n   Sample (first row):")
                for col in df.columns[:8]:
                    val = df[col].iloc[0]
                    print(f"     {col}: {val}")

        print()
        print("=" * 80)
        print("✅ SUCCESS! BigQuery pipeline supports NEW data types!")
        print("=" * 80)
        print()
        print("📦 Tables that would be created in BigQuery:")
        for table_name in sorted(frames.keys()):
            print(f"  - oura_{table_name}")
        print()
        print("🎯 Next Steps:")
        print("  1. Enable BigQuery export: OPTIONS['export_to_bigquery'] = True")
        print("  2. Test with dry-run: OPTIONS['bq_dry_run'] = True")
        print("  3. Verify schemas in BigQuery")
        print("  4. Enable real uploads: OPTIONS['bq_dry_run'] = False")
        print()

        return True

    except Exception as e:
        print("❌ ERROR: Failed to build BigQuery frames")
        print(f"   {type(e).__name__}: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_new_data_types()
    sys.exit(0 if success else 1)
