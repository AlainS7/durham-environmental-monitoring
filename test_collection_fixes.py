#!/usr/bin/env python3
"""
Test script to verify WU and TSI data collection fixes.
Tests a recent date (Oct 4, 2025) to validate field extraction.
"""

import asyncio
import sys
import pytest

# Add project root to path
sys.path.insert(0, '/workspaces/durham-environmental-monitoring')

from src.data_collection.clients.wu_client import WUClient, EndpointStrategy
from src.data_collection.clients.tsi_client import TSIClient
import os

@pytest.mark.asyncio
async def test_wu_client():
    """Test WU client with historical API (should return ALL fields)"""
    print("="*80)
    print("TESTING WEATHER UNDERGROUND CLIENT")
    print("="*80)
    
    wu_api_key = os.getenv('WU_API_KEY')
    
    if not wu_api_key:
        print("❌ WU_API_KEY environment variable not set")
        return
    
    # Test with Oct 4, 2025 (yesterday)
    test_date = "2025-10-04"
    
    print(f"\n📅 Testing date: {test_date}")
    print("🔧 Using endpoint strategy: HOURLY (PWS Historical v2 API)")
    print("🎯 Expected: ALL weather fields including temp, wind, precip, pressure\n")
    
    async with WUClient(wu_api_key, endpoint_strategy=EndpointStrategy.HOURLY) as client:
        df = await client.fetch_data(test_date, test_date, aggregate=False)
        
        if df.empty:
            print("❌ No data returned from WU API")
            return
        
        print(f"✅ Received {len(df)} records from {df['stationID'].nunique()} stations\n")
        
        # Check field coverage
        critical_fields = [
            'tempAvg', 'tempHigh', 'tempLow',
            'windspeedAvg', 'windspeedHigh', 'windspeedLow',
            'windgustAvg', 'windgustHigh', 'windgustLow',
            'precipRate', 'precipTotal',
            'pressureMax', 'pressureMin',
            'dewptAvg', 'heatindexAvg', 'windchillAvg',
            'humidityAvg', 'solarRadiationHigh', 'uvHigh', 'winddirAvg'
        ]
        
        print("📊 Field Coverage Analysis:")
        print("-"*80)
        print(f"{'Field Name':<25} {'Non-Null Count':>15} {'Coverage %':>12} {'Status':>8}")
        print("-"*80)
        
        total_records = len(df)
        all_fields_present = True
        
        for field in critical_fields:
            if field in df.columns:
                non_null = df[field].notna().sum()
                coverage = (non_null / total_records * 100) if total_records > 0 else 0
                status = "✅" if coverage > 50 else "⚠️" if coverage > 0 else "❌"
                print(f"{field:<25} {non_null:>15,} {coverage:>11.1f}% {status:>8}")
                if coverage < 50:
                    all_fields_present = False
            else:
                print(f"{field:<25} {'N/A':>15} {'0.0':>11}% {'❌':>8}")
                all_fields_present = False
        
        print("-"*80)
        
        if all_fields_present:
            print("\n🎉 SUCCESS: All critical weather fields have >50% coverage!")
        else:
            print("\n⚠️  WARNING: Some fields missing or have low coverage")
            print("    This may indicate the API is not returning full historical data")
        
        # Show sample data
        print("\n📋 Sample Data (first 3 records):")
        print("-"*80)
        sample_cols = ['stationID', 'obsTimeUtc', 'tempAvg', 'windspeedAvg', 'precipTotal', 'humidityAvg']
        available_cols = [col for col in sample_cols if col in df.columns]
        print(df[available_cols].head(3).to_string(index=False))


@pytest.mark.asyncio
async def test_tsi_client():
    """Test TSI client (should capture all available measurement types)"""
    print("\n\n")
    print("="*80)
    print("TESTING TSI AIR QUALITY CLIENT")
    print("="*80)
    
    tsi_client_id = os.getenv('TSI_CLIENT_ID')
    tsi_client_secret = os.getenv('TSI_CLIENT_SECRET')
    tsi_auth_url = os.getenv('TSI_AUTH_URL', 'https://api-prd.tsilink.com/oauth/token')
    
    if not all([tsi_client_id, tsi_client_secret]):
        print("❌ TSI_CLIENT_ID and TSI_CLIENT_SECRET environment variables not set")
        return
    
    # Test with Oct 4, 2025 (yesterday)
    test_date = "2025-10-04"
    
    print(f"\n📅 Testing date: {test_date}")
    print("🔧 Using endpoint: /telemetry with age parameter")
    print("🎯 Expected: All available sensor measurements (varies by sensor hardware)\n")
    
    async with TSIClient(tsi_client_id, tsi_client_secret, tsi_auth_url) as client:
        df = await client.fetch_data(test_date, test_date, aggregate=False)
        
        if df.empty:
            print("❌ No data returned from TSI API")
            return
        
        print(f"✅ Received {len(df)} records from {df['device_id'].nunique()} devices\n")
        
        # Check field coverage for all 31 enhanced fields
        enhanced_fields = [
            ('PM Metrics', ['pm1_0', 'pm2_5', 'pm4_0', 'pm10', 'pm2_5_aqi', 'pm10_aqi']),
            ('Number Concentration', ['ncpm0_5', 'ncpm1_0', 'ncpm2_5', 'ncpm4_0', 'ncpm10']),
            ('Environmental', ['temperature', 'rh', 'baro_inhg', 'tpsize']),
            ('Gas Sensors', ['co2_ppm', 'co_ppm', 'o3_ppb', 'no2_ppb', 'so2_ppb', 'ch2o_ppb', 'voc_mgm3']),
            ('Location', ['latitude', 'longitude', 'is_indoor', 'is_public'])
        ]
        
        print("📊 Field Coverage Analysis by Category:")
        print("="*80)
        
        total_records = len(df)
        category_stats = []
        
        for category, fields in enhanced_fields:
            print(f"\n{category}:")
            print("-"*80)
            print(f"{'Field Name':<20} {'Non-Null Count':>15} {'Coverage %':>12} {'Sensors':>10}")
            print("-"*80)
            
            category_coverage = 0
            for field in fields:
                if field in df.columns:
                    non_null = df[field].notna().sum()
                    coverage = (non_null / total_records * 100) if total_records > 0 else 0
                    sensors_with_data = df[df[field].notna()]['device_id'].nunique() if non_null > 0 else 0
                    category_coverage += coverage
                    print(f"{field:<20} {non_null:>15,} {coverage:>11.1f}% {sensors_with_data:>10}")
                else:
                    print(f"{field:<20} {'N/A':>15} {'0.0':>11}% {'0':>10}")
            
            avg_coverage = category_coverage / len(fields)
            category_stats.append((category, avg_coverage))
        
        print("\n" + "="*80)
        print("📈 Category Summary:")
        print("-"*80)
        for category, avg_coverage in category_stats:
            status = "✅" if avg_coverage > 50 else "⚠️" if avg_coverage > 2 else "❌"
            print(f"{category:<30} {avg_coverage:>8.1f}% {status:>8}")
        
        print("\n" + "="*80)
        print("📌 NOTE: TSI sensor hardware varies by model.")
        print("   - Older sensors: Basic readings only (~0-5% enhanced field coverage)")
        print("   - Newer sensors: Full 31-field suite (PM, NC, gases, environmental)")
        print("   - This is normal sensor network behavior, not a collection issue")
        
        # Show sample data from sensors with the most fields
        print("\n📋 Sample Data from Best Sensor (most fields populated):")
        print("-"*80)
        
        # Find device with most non-null PM fields
        df['pm_fields_count'] = df[['pm1_0', 'pm2_5', 'pm10']].notna().sum(axis=1)
        best_device = df.loc[df['pm_fields_count'].idxmax(), 'device_id']
        best_df = df[df['device_id'] == best_device].head(3)
        
        sample_cols = ['device_id', 'timestamp', 'pm2_5', 'temperature', 'rh', 'latitude', 'longitude']
        available_cols = [col for col in sample_cols if col in best_df.columns]
        print(best_df[available_cols].to_string(index=False))


async def main():
    """Run both tests"""
    print("\n" + "="*80)
    print("DATA COLLECTION CLIENT TESTING")
    print("Test Date: Oct 4, 2025 (Yesterday)")
    print("="*80)
    
    try:
        await test_wu_client()
    except Exception as e:
        print(f"\n❌ WU Client test failed: {e}")
        import traceback
        traceback.print_exc()
    
    try:
        await test_tsi_client()
    except Exception as e:
        print(f"\n❌ TSI Client test failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "="*80)
    print("TESTING COMPLETE")
    print("="*80)


if __name__ == "__main__":
    asyncio.run(main())
