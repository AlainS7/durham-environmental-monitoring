
#!/usr/bin/env python3
"""
Diagnose WU and TSI API column availability by fetching fresh data and showing actual column names.
"""
import asyncio
import os
import sys
import pandas as pd
from dotenv import load_dotenv
from src.data_collection.clients.wu_client import WUClient, EndpointStrategy
from src.data_collection.clients.tsi_client import TSIClient
from typing import cast

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def diagnose_wu():
    print("="*80)
    print("DIAGNOSING WEATHER UNDERGROUND API")
    print("="*80)
    
    api_key = os.getenv('WU_API_KEY')
    if not api_key:
        print("ERROR: WU_API_KEY not set")
        return
    
    # Try hourly endpoint
    print("\n--- Testing HOURLY endpoint strategy ---")
    client = WUClient(api_key=api_key, endpoint_strategy=EndpointStrategy.HOURLY)
    async with client:
        df = await client.fetch_data('2025-10-04', '2025-10-04', aggregate=False)
        
        if df.empty:
            print("ERROR: No data returned from WU API")
            return
        
        print(f"\nTotal rows returned: {len(df)}")
        print(f"Date range: {df['obsTimeUtc'].min()} to {df['obsTimeUtc'].max()}")
        print(f"\nColumns returned by API ({len(df.columns)} total):")
        for col in sorted(df.columns):
            non_null = df[col].notna().sum()
            pct = (non_null / len(df)) * 100
            status = "✅" if pct > 0 else "❌"
            print(f"  {status} {col:30s} - {non_null:5d}/{len(df):5d} ({pct:5.1f}%) non-null")
        
        # Show a sample row
        print("\n--- Sample Row (first station, first timestamp) ---")
        sample = df.iloc[0]
        for col in sorted(df.columns):
            value = sample[col]
            if pd.isna(value):
                value = "NULL"
            print(f"  {col:30s} = {value}")


async def diagnose_tsi():
    print("\n\n" + "="*80)
    print("DIAGNOSING TSI LINK API")
    print("="*80)
    
    client_id = os.getenv('TSI_CLIENT_ID')
    client_secret = os.getenv('TSI_CLIENT_SECRET')
    auth_url = os.getenv('TSI_AUTH_URL')
    if not all([client_id, client_secret, auth_url]):
        print("ERROR: TSI credentials not set (TSI_CLIENT_ID, TSI_CLIENT_SECRET, TSI_AUTH_URL)")
        return
    if not all(isinstance(x, str) for x in [client_id, client_secret, auth_url]):
        print("ERROR: TSI credentials must be strings")
        return
    print("\n--- Testing TSI flat-format endpoint ---")
    client = TSIClient(
        client_id=cast(str, client_id),
        client_secret=cast(str, client_secret),
        auth_url=cast(str, auth_url)
    )
    async with client:
        df = await client.fetch_data('2025-10-04', '2025-10-04', aggregate=False)
        
        if df.empty:
            print("ERROR: No data returned from TSI API")
            return
        
        print(f"\nTotal rows returned: {len(df)}")
        print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        print(f"\nColumns returned by API ({len(df.columns)} total):")
        for col in sorted(df.columns):
            non_null = df[col].notna().sum()
            pct = (non_null / len(df)) * 100
            status = "✅" if pct > 0 else "❌"
            print(f"  {status} {col:30s} - {non_null:5d}/{len(df):5d} ({pct:5.1f}%) non-null")
        
        # Show a sample row
        print("\n--- Sample Row (first device, first timestamp) ---")
        sample = df.iloc[0]
        for col in sorted(df.columns):
            value = sample[col]
            if pd.isna(value):
                value = "NULL"
            print(f"  {col:30s} = {value}")


async def main():
    await diagnose_wu()
    await diagnose_tsi()


if __name__ == '__main__':
    asyncio.run(main())
