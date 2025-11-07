#!/usr/bin/env python3
"""
Comprehensive test to discover all available Oura Ring data endpoints.
Tests each endpoint to see what data is actually available.
"""

import sys
from pathlib import Path
from datetime import date, timedelta
import json

sys.path.insert(0, str(Path(__file__).parent / "oura-rings"))

from oura_client import OuraClient


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


def test_all_endpoints():
    """Test all known and potential Oura API endpoints."""

    token = load_token(1)
    if not token:
        print("❌ No token found")
        return

    # Date range for testing (last 7 days)
    end_date = date.today()
    start_date = end_date - timedelta(days=7)

    # Known endpoints from current implementation
    known_endpoints = [
        ("Daily Sleep", "v2/usercollection/daily_sleep"),
        ("Sleep Periods", "v2/usercollection/sleep"),
        ("Daily Activity", "v2/usercollection/daily_activity"),
        ("Daily Readiness", "v2/usercollection/daily_readiness"),
        ("Heart Rate", "v2/usercollection/heartrate"),
        ("Sessions", "v2/usercollection/session"),
        ("Workouts", "v2/usercollection/workout"),
    ]

    # Additional endpoints to test based on API docs
    additional_endpoints = [
        ("Personal Info", "v2/usercollection/personal_info"),
        ("Daily SpO2", "v2/usercollection/daily_spo2"),
        ("SpO2", "v2/usercollection/spo2"),
        ("Daily Stress", "v2/usercollection/daily_stress"),
        ("Stress", "v2/usercollection/stress"),
        ("Tags", "v2/usercollection/tag"),
        ("Daily Tag", "v2/usercollection/daily_tag"),
        ("Rest Mode Period", "v2/usercollection/rest_mode_period"),
        ("Ring Configuration", "v2/usercollection/ring_configuration"),
        ("Daily Resilience", "v2/usercollection/daily_resilience"),
        ("Sleep Time", "v2/usercollection/sleep_time"),
        ("Daily Cardiovascular Age", "v2/usercollection/daily_cardiovascular_age"),
        ("VO2 Max", "v2/usercollection/vO2_max"),
    ]

    results = {"working": [], "no_data": [], "error": []}

    print("=" * 80)
    print("TESTING ALL OURA API ENDPOINTS")
    print("=" * 80)
    print(f"Date range: {start_date} to {end_date}")
    print()

    with OuraClient(personal_access_token=token) as client:
        all_endpoints = known_endpoints + additional_endpoints

        for name, endpoint in all_endpoints:
            print(f"Testing: {name:<30} ", end="", flush=True)

            try:
                response = client._make_paginated_request(
                    "GET",
                    endpoint,
                    params={"start_date": str(start_date), "end_date": str(end_date)},
                )

                if response and len(response) > 0:
                    print(f"✅ SUCCESS - {len(response)} records")
                    results["working"].append(
                        {
                            "name": name,
                            "endpoint": endpoint,
                            "records": len(response),
                            "sample": response[0] if response else None,
                        }
                    )
                else:
                    print(f"⚠️  No data (endpoint exists)")
                    results["no_data"].append({"name": name, "endpoint": endpoint})

            except Exception as e:
                error_msg = str(e)
                if "404" in error_msg:
                    print(f"❌ Not found (404)")
                elif "403" in error_msg:
                    print(f"❌ Forbidden (403 - may need subscription)")
                elif "401" in error_msg:
                    print(f"❌ Unauthorized (401)")
                else:
                    print(f"❌ Error: {error_msg[:50]}")

                results["error"].append(
                    {"name": name, "endpoint": endpoint, "error": error_msg}
                )

    # Print summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()

    print(f"✅ WORKING ENDPOINTS ({len(results['working'])}):")
    print("-" * 80)
    for item in results["working"]:
        print(f"  • {item['name']:<30} - {item['records']} records")
        if item["sample"]:
            # Show available fields
            keys = list(item["sample"].keys())
            print(f"    Fields: {', '.join(keys[:10])}")
            if len(keys) > 10:
                print(f"            ... and {len(keys) - 10} more")

    print()
    print(f"⚠️  ENDPOINTS WITH NO DATA ({len(results['no_data'])}):")
    print("-" * 80)
    for item in results["no_data"]:
        print(f"  • {item['name']:<30} - {item['endpoint']}")

    print()
    print(f"❌ FAILED/UNAVAILABLE ENDPOINTS ({len(results['error'])}):")
    print("-" * 80)
    for item in results["error"]:
        print(f"  • {item['name']:<30}")
        if "404" in item["error"]:
            print(f"    → Endpoint doesn't exist")
        elif "403" in item["error"]:
            print(f"    → May require Oura membership or different scope")
        else:
            print(f"    → {item['error'][:60]}")

    print()
    print("=" * 80)

    # Save detailed results
    output_file = Path(__file__).parent / "oura_endpoint_test_results.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"📄 Detailed results saved to: {output_file}")
    print()


if __name__ == "__main__":
    test_all_endpoints()
