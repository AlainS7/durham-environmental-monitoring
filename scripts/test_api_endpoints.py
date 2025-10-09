

#!/usr/bin/env python3
"""
Test different WU and TSI API endpoints to find which ones return actual sensor data.
"""
import asyncio
import os
import sys
import pandas as pd
import httpx
import pytest
from dotenv import load_dotenv
from src.utils.config_loader import get_wu_stations, get_tsi_devices

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.mark.asyncio
async def test_wu_endpoints():
    """Test all 3 WU historical endpoints to see which has data."""
    print("="*80)
    print("TESTING WEATHER UNDERGROUND ENDPOINTS")
    print("="*80)
    
    api_key = os.getenv('WU_API_KEY')
    if not api_key:
        # Try app_config
        from src.config.app_config import app_config
        api_key = app_config.wu_api_config.get('api_key')
    
    if not api_key:
        print("ERROR: WU_API_KEY not available")
        return
    
    stations = get_wu_stations()
    if not stations:
        print("ERROR: No WU stations configured")
        return
    
    test_station = stations[0]['stationId']
    print(f"\nTesting with station: {test_station}")
    print("Date: 2025-10-02")
    
    base_url = "https://api.weather.com/v2/pws"
    
    # Test 1: Daily Summary - 7 Day
    print("\n" + "-"*80)
    print("TEST 1: PWS Daily Summary - 7 Day History")
    print("Endpoint: /dailysummary/7day")
    print("-"*80)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        params = {
            'stationId': test_station,
            'format': 'json',
            'units': 'm',
            'apiKey': api_key,
            'numericPrecision': 'decimal'
        }
        try:
            resp = await client.get(f"{base_url}/dailysummary/7day", params=params)
            resp.raise_for_status()
            data = resp.json()
            
            if data and 'observations' in data:
                df = pd.DataFrame(data['observations'])
                print(f"✅ Success! Returned {len(df)} days")
                print(f"\nColumns: {list(df.columns)}")
                
                # Check for temperature data
                temp_cols = [col for col in df.columns if 'temp' in col.lower()]
                print(f"\nTemperature columns: {temp_cols}")
                if temp_cols:
                    for col in temp_cols[:3]:  # First 3 temp columns
                        non_null = df[col].notna().sum()
                        print(f"  {col}: {non_null}/{len(df)} non-null")
                
                # Show sample
                print("\nSample row:")
                if len(df) > 0:
                    sample = df.iloc[0]
                    for key in ['obsTimeLocal', 'tempHigh', 'tempLow', 'tempAvg', 'windspdAvg', 'precipTotal']:
                        if key in sample:
                            print(f"  {key}: {sample[key]}")
            else:
                print("❌ No observations returned")
                print(f"Response: {data}")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # Test 2: Recent History - 1 Day - Rapid
    print("\n" + "-"*80)
    print("TEST 2: PWS Recent History - 1 Day - Rapid History")
    print("Endpoint: /observations/all/1day")
    print("-"*80)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(f"{base_url}/observations/all/1day", params=params)
            resp.raise_for_status()
            data = resp.json()
            
            if data and 'observations' in data:
                df = pd.DataFrame(data['observations'])
                print(f"✅ Success! Returned {len(df)} observations")
                
                # Check for temperature data
                temp_cols = [col for col in df.columns if 'temp' in col.lower()]
                if temp_cols:
                    for col in temp_cols[:3]:
                        non_null = df[col].notna().sum()
                        pct = (non_null / len(df)) * 100 if len(df) > 0 else 0
                        print(f"  {col}: {non_null}/{len(df)} ({pct:.1f}%) non-null")
            else:
                print("❌ No observations returned")
        except Exception as e:
            print(f"❌ Error: {e}")
    
    # Test 3: Recent History - 7 Day - Hourly
    print("\n" + "-"*80)
    print("TEST 3: PWS Recent History - 7 Day - Hourly History")
    print("Endpoint: /observations/hourly/7day")
    print("-"*80)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(f"{base_url}/observations/hourly/7day", params=params)
            resp.raise_for_status()
            data = resp.json()
            
            if data and 'observations' in data:
                df = pd.DataFrame(data['observations'])
                print(f"✅ Success! Returned {len(df)} hourly observations")
                
                # Check for temperature data
                temp_cols = [col for col in df.columns if 'temp' in col.lower()]
                if temp_cols:
                    for col in temp_cols[:3]:
                        non_null = df[col].notna().sum()
                        pct = (non_null / len(df)) * 100 if len(df) > 0 else 0
                        status = "✅" if pct > 0 else "❌"
                        print(f"  {status} {col}: {non_null}/{len(df)} ({pct:.1f}%) non-null")
                
                # Show sample
                print("\nSample row:")
                if len(df) > 0:
                    sample = df.iloc[0]
                    for key in ['obsTimeLocal', 'tempAvg', 'windspdAvg', 'precipRate', 'humidityAvg']:
                        if key in sample:
                            val = sample[key]
                            print(f"  {key}: {val if not pd.isna(val) else 'NULL'}")
            else:
                print("❌ No observations returned")
        except Exception as e:
            print(f"❌ Error: {e}")


@pytest.mark.asyncio
async def test_tsi_endpoint():
    """Test TSI flat-format endpoint."""
    print("\n\n" + "="*80)
    print("TESTING TSI FLAT-FORMAT ENDPOINT")
    print("="*80)
    
    from src.config.app_config import app_config
    tsi_config = app_config.tsi_api_config
    
    client_id = tsi_config.get('client_id')
    client_secret = tsi_config.get('client_secret')
    auth_url = tsi_config.get('auth_url')
    base_url = "https://api-prd.tsilink.com/api/v3/external"
    
    if not all([client_id, client_secret, auth_url]):
        print("ERROR: TSI credentials not available")
        return
    
    devices = get_tsi_devices()
    if not devices:
        print("ERROR: No TSI devices configured")
        return
    
    test_device = devices[0]
    print(f"\nTesting with device: {test_device}")
    print("Date: 2025-10-02")
    
    # Authenticate
    print("\nStep 1: Authenticating...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        params = {'grant_type': 'client_credentials'}
        data = {'client_id': client_id, 'client_secret': client_secret}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        try:
            if auth_url is None:
                print("ERROR: TSI_AUTH_URL not set")
                return
            auth_resp = await client.post(auth_url, params=params, data=data, headers=headers)
            auth_resp.raise_for_status()
            auth_json = auth_resp.json()
            token = auth_json['access_token']
            print("✅ Authentication successful")
        except Exception as e:
            print(f"❌ Authentication failed: {e}")
            return
        
        # Test flat-format endpoint
        print("\nStep 2: Fetching telemetry data...")
        print("Endpoint: /telemetry/flat-format")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        
        start_iso = "2025-10-02T00:00:00Z"
        end_iso = "2025-10-03T00:00:00Z"
        
        params = {
            'device_id': test_device,
            'start_date': start_iso,
            'end_date': end_iso
        }
        
        try:
            resp = await client.get(f"{base_url}/telemetry/flat-format", params=params, headers=headers)
            resp.raise_for_status()
            records = resp.json()
            
            if records and len(records) > 0:
                df = pd.DataFrame(records)
                print(f"✅ Success! Returned {len(df)} records")
                print(f"\nColumns ({len(df.columns)} total): {list(df.columns)}")
                
                # Check for sensor data
                sensor_cols = ['mcpm2x5', 'mcpm10', 'temperature', 'rh', 'co2_ppm', 'o3_ppb']
                print("\nSensor data availability:")
                for col in sensor_cols:
                    if col in df.columns:
                        non_null = df[col].notna().sum()
                        pct = (non_null / len(df)) * 100 if len(df) > 0 else 0
                        status = "✅" if pct > 0 else "❌"
                        print(f"  {status} {col}: {non_null}/{len(df)} ({pct:.1f}%) non-null")
                    else:
                        print(f"  ⚠️  {col}: Column not in response")
                
                # Show sample
                print("\nSample row:")
                if len(df) > 0:
                    sample = df.iloc[0]
                    for key in ['timestamp', 'mcpm2x5', 'temperature', 'rh', 'co2_ppm']:
                        if key in sample:
                            val = sample[key]
                            print(f"  {key}: {val if not pd.isna(val) else 'NULL'}")
            else:
                print("❌ No records returned")
                print(f"Response: {records}")
        except Exception as e:
            print(f"❌ Error: {e}")


async def main():
    await test_wu_endpoints()
    await test_tsi_endpoint()
    
    print("\n\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    print("\nBased on the test results above:")
    print("1. For WU: Use the endpoint with the highest % of non-null temperature data")
    print("2. For TSI: If flat-format returns data, update the client to use it")
    print("\nNext steps will be provided based on these results.")


if __name__ == '__main__':
    asyncio.run(main())
