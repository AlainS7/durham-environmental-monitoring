#!/usr/bin/env python3
"""
Oura Ring & Environmental Monitoring Correlation Analysis

This script analyzes relationships between Oura Ring biometric data from the Oura API
and environmental monitoring data from multiple air quality networks and weather sources.

Features:
- Fetch Oura Ring data directly from Oura API v2
- Colocation analysis: Air Assure vs Blue Sky vs Ambient PM2.5
- Temperature vs Heart Rate Variability correlations
- PM2.5 vs Oura metrics correlations
- Statistical significance testing with Pearson & Spearman correlations
- Interactive visualizations with Plotly
"""

import os
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from google.cloud import bigquery
from scipy.stats import pearsonr, spearmanr
import pyarrow.parquet as pq

# Configure
warnings.filterwarnings("ignore")
pd.set_option("display.max_columns", 100)
sns.set_style("whitegrid")
plt.rcParams["figure.figsize"] = (14, 8)

# Setup paths
REPO_PATH = Path(__file__).parent.parent
DATA_DIR = REPO_PATH / "data" / "analysis_outputs"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Add oura-rings to path for imports
sys.path.insert(0, str(REPO_PATH / "oura-rings"))

print("=" * 80)
print("🔬 OURA RING & ENVIRONMENTAL MONITORING CORRELATION ANALYSIS")
print("=" * 80)

# ============================================================================
# 1. LOAD OURA DATA FROM API
# ============================================================================
print("\n📊 SECTION 1: Loading Oura Data...")
print("-" * 80)

oura_data = None

# Try to fetch from Oura API first
try:
    from oura_client import OuraClient
    from oura_transforms import combine_daily_dataframes

    # Load token from environment
    oura_token = os.getenv("OURA_PAT") or os.getenv("PERSONAL_ACCESS_TOKEN")

    # Try loading from token file if not in env
    token_file = None
    if not oura_token:
        # Check Secure Files location (parent of repo)
        secure_files_path = REPO_PATH.parent.parent / "Secure Files" / "pat_r3.env"
        if secure_files_path.exists():
            token_file = secure_files_path

        # Also check oura-rings/pats directory
        if not token_file:
            pats_path = REPO_PATH / "oura-rings" / "pats"
            if pats_path.exists():
                pat_files = list(pats_path.glob("pat_*.env"))
                if pat_files:
                    token_file = pat_files[0]

        if token_file:
            print(f"📁 Loading token from: {token_file}")
            load_dotenv(token_file)
            oura_token = os.getenv("PERSONAL_ACCESS_TOKEN")

    if oura_token:
        print("🔗 Connecting to Oura API...")
        with OuraClient(oura_token) as client:
            # Define date range (last 180 days)
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=180)

            print(f"   📅 Fetching data from {start_date} to {end_date}")

            # Fetch daily data
            sleep_data = client.get_daily_sleep(str(start_date), str(end_date))
            activity_data = client.get_daily_activity(str(start_date), str(end_date))
            readiness_data = client.get_daily_readiness(str(start_date), str(end_date))

            print(f"   ✓ Sleep records: {len(sleep_data)}")
            print(f"   ✓ Activity records: {len(activity_data)}")
            print(f"   ✓ Readiness records: {len(readiness_data)}")

            # Combine into daily dataframe
            oura_data = combine_daily_dataframes(
                sleep_data, activity_data, readiness_data
            )

            if not oura_data.empty:
                oura_data["day"] = pd.to_datetime(oura_data["day"])
                print("\n✅ Successfully fetched Oura data from API")
                print(f"   Records: {len(oura_data)} days")
                print(
                    f"   Date range: {oura_data['day'].min().date()} to {oura_data['day'].max().date()}"
                )
            else:
                print("⚠️  No data returned from Oura API")
    else:
        print("⚠️  No Oura API token found")
        print("   Set OURA_PAT or PERSONAL_ACCESS_TOKEN environment variable")
        print("   Or create pat_r<N>.env with your token (see oura-rings/SECRETS_SETUP.md)")

except ImportError as e:
    print(f"⚠️  Could not import Oura modules: {e}")
except Exception as e:
    print(f"⚠️  Error fetching from Oura API: {e}")

# Fallback to local parquet files if API fetch failed
if oura_data is None or oura_data.empty:
    print("\n   Trying local parquet files...")
    oura_path = REPO_PATH / "oura-rings"
    try:
        parquet_files = list(oura_path.glob("**/*.parquet"))
        if parquet_files:
            oura_data = pd.concat(
                [pq.read_table(f).to_pandas() for f in parquet_files], ignore_index=True
            )
            print(f"✅ Loaded Oura data from {len(parquet_files)} parquet files")
        else:
            raise FileNotFoundError("No parquet files found")
    except Exception as e:
        print(f"⚠️  Could not load local Oura data: {e}")
        print("   Creating sample Oura data for demonstration...")
        date_range = pd.date_range(start="2025-06-01", end="2025-12-31", freq="D")
        oura_data = pd.DataFrame(
            {
                "day": date_range,
                "sleep_score": np.random.uniform(60, 95, len(date_range)),
                "total_sleep": np.random.uniform(6, 9, len(date_range)) * 3600,
                "resting_heart_rate": np.random.uniform(55, 75, len(date_range)),
                "heart_rate_variability": np.random.uniform(30, 100, len(date_range)),
                "activity_score": np.random.uniform(40, 100, len(date_range)),
                "readiness_score": np.random.uniform(30, 100, len(date_range)),
                "recovery_index": np.random.uniform(0, 100, len(date_range)),
            }
        )
        print(f"✅ Created sample Oura dataset with {len(oura_data)} days")

if oura_data is not None and not oura_data.empty:
    if "day" in oura_data.columns:
        oura_data["day"] = pd.to_datetime(oura_data["day"])
    print(f"📊 Oura data shape: {oura_data.shape}")
    print(f"   Columns: {list(oura_data.columns[:5])}...")
else:
    print("❌ No Oura data available")
    sys.exit(1)

# ============================================================================
# 2. FETCH DATA FROM BIGQUERY
# ============================================================================
print("\n📊 SECTION 2: Fetching Environmental Data...")
print("-" * 80)

pm25_data = pd.DataFrame()
wu_data = pd.DataFrame()

try:
    print("🔗 Connecting to BigQuery...")
    client = bigquery.Client(project="durham-weather-466502")
    print("   ✅ BigQuery client initialized")

    # Define date range from Oura data
    if oura_data is not None and "day" in oura_data.columns:
        start_date = oura_data["day"].min().date()
        end_date = oura_data["day"].max().date()
    else:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=180)

    print(f"\n   Fetching PM2.5 data ({start_date} to {end_date})...")

    # Fixed query using correct table and metric name: pm2_5_mv_corrected
    # Table: all_sensors_daily_enriched
    # Column mapping: day_ts→timestamp, native_sensor_id→sensor_id, sensor_source→sensor_name, avg_value→value
    query_pm25 = f"""
    SELECT 
        day_ts as timestamp,
        native_sensor_id as sensor_id,
        sensor_source as sensor_name,
        metric_name,
        avg_value as value,
        latitude as location_lat,
        longitude as location_lon
    FROM `durham-weather-466502.sensors.all_sensors_daily_enriched`
    WHERE DATE(day_ts) BETWEEN CAST('{start_date}' AS DATE) AND CAST('{end_date}' AS DATE)
    AND metric_name = 'pm2_5_mv_corrected'
    AND avg_value IS NOT NULL
    LIMIT 15000
    """

    try:
        pm25_data = client.query(query_pm25).to_dataframe()
        pm25_data["timestamp"] = pd.to_datetime(pm25_data["timestamp"])
        if len(pm25_data) > 0:
            print(
                f"   ✅ Loaded {len(pm25_data):,} PM2.5 records from {pm25_data['sensor_name'].nunique()} sensors"
            )
        else:
            # Try alternative metric names
            print("   ⚠️  No pm2_5_mv_corrected records found, trying pm2_5_aqi...")
            query_pm25 = f"""
            SELECT 
                day_ts as timestamp,
                native_sensor_id as sensor_id,
                sensor_source as sensor_name,
                metric_name,
                avg_value as value,
                latitude as location_lat,
                longitude as location_lon
            FROM `durham-weather-466502.sensors.all_sensors_daily_enriched`
            WHERE DATE(day_ts) BETWEEN CAST('{start_date}' AS DATE) AND CAST('{end_date}' AS DATE)
            AND metric_name IN ('pm2_5_mv_corrected', 'pm2_5_aqi')
            AND avg_value IS NOT NULL
            LIMIT 15000
            """
            pm25_data = client.query(query_pm25).to_dataframe()
            pm25_data["timestamp"] = pd.to_datetime(pm25_data["timestamp"])
            print(
                f"   ✅ Loaded {len(pm25_data):,} PM2.5 records from {pm25_data['sensor_name'].nunique()} sensors"
            )
    except Exception as e:
        print(f"   ⚠️  PM2.5 query failed: {e}")
        pm25_data = pd.DataFrame()

    # Query Wunderground data
    print(
        f"\n   Fetching Wunderground temperature data ({start_date} to {end_date})..."
    )
    # Fixed query using correct column names from actual schema:
    # - ts (not timestamp)
    # - temperature (not tempC)
    # - native_sensor_id for station ID
    query_wu = f"""
    SELECT 
        ts as timestamp,
        native_sensor_id as station_id,
        temperature as temperature_celsius,
        humidity,
        wind_speed_avg as wind_speed_kph
    FROM `durham-weather-466502.sensors.wu_raw_materialized`
    WHERE DATE(ts) BETWEEN CAST('{start_date}' AS DATE) AND CAST('{end_date}' AS DATE)
    LIMIT 10000
    """

    try:
        wu_data = client.query(query_wu).to_dataframe()
        wu_data["timestamp"] = pd.to_datetime(wu_data["timestamp"])
        print(
            f"   ✅ Loaded {len(wu_data):,} Wunderground records from {wu_data['station_id'].nunique()} stations"
        )
    except Exception as e:
        print(f"   ⚠️  Wunderground query failed: {e}")
        wu_data = pd.DataFrame()

except Exception as e:
    print(f"⚠️  BigQuery connection failed: {e}")
    print("   Will use generated sample data for demonstration")

    # Generate sample environmental data
    date_range = pd.date_range(start="2025-06-01", end="2025-12-31", freq="D")
    pm25_data = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp(d) + pd.Timedelta(hours=h)
                for d in date_range
                for h in range(24)
            ],
            "device_id": ["SENSOR_01", "SENSOR_02", "SENSOR_03"]
            * (len(date_range) * 8),
            "sensor_name": ["AirAssure_Downtown", "Bluesky_Central", "Ambient_Indoor"]
            * (len(date_range) * 8),
            "metric_name": "pm2_5",
            "value": np.random.uniform(5, 50, len(date_range) * 24),
            "location_lat": [36.0] * (len(date_range) * 24),
            "location_lon": [-78.8] * (len(date_range) * 24),
        }
    )

    wu_data = pd.DataFrame(
        {
            "timestamp": [
                pd.Timestamp(d) + pd.Timedelta(hours=h)
                for d in date_range
                for h in range(24)
            ],
            "station_id": ["WU_STATION_01"] * len(date_range) * 24,
            "temperature_celsius": 15
            + 10 * np.sin(np.arange(len(date_range) * 24) * 2 * np.pi / (24 * 365))
            + np.random.normal(0, 2, len(date_range) * 24),
            "humidity": np.random.uniform(30, 90, len(date_range) * 24),
            "wind_speed_kph": np.random.uniform(0, 25, len(date_range) * 24),
        }
    )

    print(f"✅ Created sample PM2.5 data: {len(pm25_data):,} records")
    print(f"✅ Created sample Wunderground data: {len(wu_data):,} records")

# ============================================================================
# 3. COLOCATION ANALYSIS: Air Assure vs Blue Sky
# ============================================================================
print("\n" + "=" * 80)
print("📍 SECTION 3: Colocation Analysis - Air Assure vs Blue Sky")
print("=" * 80)

if not pm25_data.empty:
    sensors = pm25_data["sensor_name"].unique()
    print(f"\n📡 Available sensors: {len(sensors)}")
    print(f"   {', '.join(sensors[:5])}{'...' if len(sensors) > 5 else ''}")

    # Create proxies if specific sensors not found
    air_assure = pm25_data[
        pm25_data["sensor_name"].str.contains("air|assure", case=False, na=False)
    ]
    if air_assure.empty and len(sensors) > 0:
        air_assure = pm25_data[pm25_data["sensor_name"] == sensors[0]]

    bluesky = pm25_data[
        pm25_data["sensor_name"].str.contains("blue|sky", case=False, na=False)
    ]
    if bluesky.empty and len(sensors) > 1:
        bluesky = pm25_data[pm25_data["sensor_name"] == sensors[1]]

    if not air_assure.empty and not bluesky.empty:
        # Aggregate daily
        air_daily = (
            air_assure.groupby(air_assure["timestamp"].dt.date)["value"]
            .mean()
            .reset_index()
        )
        air_daily.columns = ["date", "air_assure_pm25"]
        air_daily["date"] = pd.to_datetime(air_daily["date"])

        blue_daily = (
            bluesky.groupby(bluesky["timestamp"].dt.date)["value"].mean().reset_index()
        )
        blue_daily.columns = ["date", "bluesky_pm25"]
        blue_daily["date"] = pd.to_datetime(blue_daily["date"])

        coloc_ab = air_daily.merge(blue_daily, on="date", how="inner")

        if len(coloc_ab) > 1:
            print(f"\n✅ Colocation data: {len(coloc_ab)} overlapping days")

            # Statistics
            r, p = pearsonr(coloc_ab["air_assure_pm25"], coloc_ab["bluesky_pm25"])
            print(f"\n📈 Pearson Correlation: r={r:.4f}, p-value={p:.4e}")
            print(f"   Result: {'SIGNIFICANT ✓' if p < 0.05 else 'NOT SIGNIFICANT ✗'}")

            # Visualization
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=coloc_ab["air_assure_pm25"],
                    y=coloc_ab["bluesky_pm25"],
                    mode="markers",
                    marker=dict(size=8, color="rgba(0, 100, 200, 0.6)"),
                    name="Measurements",
                    text=coloc_ab["date"].dt.strftime("%Y-%m-%d"),
                    hovertemplate="Air Assure: %{x:.1f}<br>Blue Sky: %{y:.1f}<br>%{text}<extra></extra>",
                )
            )

            # Perfect agreement line
            lim = [
                min(coloc_ab["air_assure_pm25"].min(), coloc_ab["bluesky_pm25"].min()),
                max(coloc_ab["air_assure_pm25"].max(), coloc_ab["bluesky_pm25"].max()),
            ]
            fig.add_trace(
                go.Scatter(
                    x=lim,
                    y=lim,
                    mode="lines",
                    line=dict(dash="dash", color="gray"),
                    name="Perfect Agreement",
                )
            )

            fig.update_layout(
                title=f"Air Assure vs Blue Sky PM2.5 (r={r:.3f}, p={p:.3e})",
                xaxis_title="Air Assure PM2.5 (µg/m³)",
                yaxis_title="Blue Sky PM2.5 (µg/m³)",
                height=600,
            )
            output_file = DATA_DIR / "colocation_air_assure_vs_bluesky.html"
            fig.write_html(str(output_file))
            print("\n📊 Visualization saved: colocation_air_assure_vs_bluesky.html")

# ============================================================================
# 4. COLOCATION ANALYSIS: Blue Sky vs Ambient
# ============================================================================
print("\n" + "=" * 80)
print("📍 SECTION 4: Colocation Analysis - Blue Sky vs Ambient")
print("=" * 80)

if not pm25_data.empty and len(sensors) > 2:
    ambient = pm25_data[
        pm25_data["sensor_name"].str.contains(
            "ambient|outdoor|env", case=False, na=False
        )
    ]
    if ambient.empty:
        ambient = pm25_data[pm25_data["sensor_name"] == sensors[2]]

    if not bluesky.empty and not ambient.empty:
        blue_daily = (
            bluesky.groupby(bluesky["timestamp"].dt.date)["value"].mean().reset_index()
        )
        blue_daily.columns = ["date", "bluesky_pm25"]
        blue_daily["date"] = pd.to_datetime(blue_daily["date"])

        amb_daily = (
            ambient.groupby(ambient["timestamp"].dt.date)["value"].mean().reset_index()
        )
        amb_daily.columns = ["date", "ambient_pm25"]
        amb_daily["date"] = pd.to_datetime(amb_daily["date"])

        coloc_ba = blue_daily.merge(amb_daily, on="date", how="inner")

        if len(coloc_ba) > 1:
            print(f"\n✅ Colocation data: {len(coloc_ba)} overlapping days")

            # Statistics
            r, p = pearsonr(coloc_ba["bluesky_pm25"], coloc_ba["ambient_pm25"])
            mean_diff = (coloc_ba["bluesky_pm25"] - coloc_ba["ambient_pm25"]).mean()

            print(f"\n📈 Pearson Correlation: r={r:.4f}, p-value={p:.4e}")
            print(f"   Mean Difference (Blue Sky - Ambient): {mean_diff:.2f} µg/m³")

            # Visualization: Scatter plot
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=coloc_ba["bluesky_pm25"],
                    y=coloc_ba["ambient_pm25"],
                    mode="markers",
                    marker=dict(size=8, color="rgba(200, 100, 0, 0.6)"),
                    name="Measurements",
                    text=coloc_ba["date"].dt.strftime("%Y-%m-%d"),
                    hovertemplate="Blue Sky: %{x:.1f}<br>Ambient: %{y:.1f}<br>%{text}<extra></extra>",
                )
            )

            lim = [
                min(coloc_ba["bluesky_pm25"].min(), coloc_ba["ambient_pm25"].min()),
                max(coloc_ba["bluesky_pm25"].max(), coloc_ba["ambient_pm25"].max()),
            ]
            fig.add_trace(
                go.Scatter(
                    x=lim,
                    y=lim,
                    mode="lines",
                    line=dict(dash="dash", color="gray"),
                    name="Perfect Agreement",
                )
            )

            fig.update_layout(
                title=f"Blue Sky vs Ambient PM2.5 (r={r:.3f}, p={p:.3e})",
                xaxis_title="Blue Sky PM2.5 (µg/m³)",
                yaxis_title="Ambient PM2.5 (µg/m³)",
                height=600,
            )
            output_file = DATA_DIR / "colocation_bluesky_vs_ambient.html"
            fig.write_html(str(output_file))
            print("\n📊 Visualization saved: colocation_bluesky_vs_ambient.html")

            # Time series difference
            coloc_ba["difference"] = coloc_ba["bluesky_pm25"] - coloc_ba["ambient_pm25"]
            fig2 = go.Figure()
            fig2.add_trace(
                go.Scatter(
                    x=coloc_ba["date"],
                    y=coloc_ba["difference"],
                    fill="tozeroy",
                    name="Difference",
                    line=dict(color="orange"),
                )
            )
            fig2.add_hline(y=0, line_dash="dash", line_color="red")
            fig2.update_layout(
                title="PM2.5 Difference Over Time: Blue Sky - Ambient",
                xaxis_title="Date",
                yaxis_title="Difference (µg/m³)",
                height=500,
            )
            output_file2 = DATA_DIR / "colocation_difference_timeseries.html"
            fig2.write_html(str(output_file2))
            print("📊 Time series saved: colocation_difference_timeseries.html")

# ============================================================================
# 5. TEMPERATURE vs HEART RATE VARIABILITY
# ============================================================================
print("\n" + "=" * 80)
print("💓 SECTION 5: Temperature vs Heart Rate Variability Correlation")
print("=" * 80)

if (
    oura_data is not None
    and "heart_rate_variability" in oura_data.columns
    and not wu_data.empty
):
    # Prepare Oura HRV data
    oura_hrv = oura_data[["day", "heart_rate_variability"]].dropna()

    # Prepare WU temperature
    wu_agg = wu_data.copy()
    wu_agg["date"] = wu_agg["timestamp"].dt.date
    wu_daily_temp = (
        wu_agg.groupby("date")
        .agg(
            {
                "temperature_celsius": "mean",
                "humidity": "mean",
                "wind_speed_kph": "mean",
            }
        )
        .reset_index()
    )
    wu_daily_temp.columns = ["day", "temperature", "humidity", "wind_speed"]
    wu_daily_temp["day"] = pd.to_datetime(wu_daily_temp["day"])

    # Merge
    temp_hrv = oura_hrv.merge(wu_daily_temp, on="day", how="inner").dropna(
        subset=["heart_rate_variability", "temperature"]
    )

    if len(temp_hrv) > 2:
        print(f"\n✅ Merged data: {len(temp_hrv)} days with complete records")

        # Correlation tests
        pearson_r, pearson_p = pearsonr(
            temp_hrv["temperature"], temp_hrv["heart_rate_variability"]
        )
        spearman_r, spearman_p = spearmanr(
            temp_hrv["temperature"], temp_hrv["heart_rate_variability"]
        )

        print("\n📊 STATISTICAL TESTS:")
        print(f"   Pearson  Correlation: r = {pearson_r:7.4f} (p = {pearson_p:.4e})")
        print(f"   Spearman Correlation: ρ = {spearman_r:7.4f} (p = {spearman_p:.4e})")
        print(
            f"   Significance: {'✓ SIGNIFICANT' if pearson_p < 0.05 else '✗ NOT SIGNIFICANT'} (α=0.05)"
        )

        # Scatter plot with regression
        fig = px.scatter(
            temp_hrv,
            x="temperature",
            y="heart_rate_variability",
            trendline="ols",
            title=f"Wunderground Temperature vs Heart Rate Variability<br><sub>r={pearson_r:.3f}, p={pearson_p:.3e}</sub>",
            labels={
                "temperature": "Temperature (°C)",
                "heart_rate_variability": "HRV (ms)",
            },
            height=600,
        )
        fig.update_traces(marker=dict(size=8, opacity=0.7))
        output_file = DATA_DIR / "temperature_vs_hrv_scatter.html"
        fig.write_html(str(output_file))
        print("\n📊 Scatter plot saved: temperature_vs_hrv_scatter.html")

        # Time series overlay
        fig_ts = make_subplots(specs=[[{"secondary_y": True}]])
        fig_ts.add_trace(
            go.Scatter(
                x=temp_hrv["day"],
                y=temp_hrv["temperature"],
                name="Temperature",
                line=dict(color="orangered"),
            ),
            secondary_y=False,
        )
        fig_ts.add_trace(
            go.Scatter(
                x=temp_hrv["day"],
                y=temp_hrv["heart_rate_variability"],
                name="HRV",
                line=dict(color="steelblue"),
            ),
            secondary_y=True,
        )
        fig_ts.update_xaxes(title_text="Date")
        fig_ts.update_yaxes(title_text="Temperature (°C)", secondary_y=False)
        fig_ts.update_yaxes(title_text="HRV (ms)", secondary_y=True)
        fig_ts.update_layout(
            title="Temperature vs HRV Time Series", height=500, hovermode="x unified"
        )
        output_file_ts = DATA_DIR / "temperature_vs_hrv_timeseries.html"
        fig_ts.write_html(str(output_file_ts))
        print("📊 Time series saved: temperature_vs_hrv_timeseries.html")

# ============================================================================
# 6. PM2.5 & TEMPERATURE vs OURA METRICS
# ============================================================================
print("\n" + "=" * 80)
print("🌍 SECTION 6: Environmental Factors vs Oura Metrics")
print("=" * 80)

if oura_data is not None and (not pm25_data.empty or not wu_data.empty):
    # Prepare PM2.5
    pm25_daily = (
        pm25_data.groupby(pm25_data["timestamp"].dt.date)["value"].mean().reset_index()
    )
    pm25_daily.columns = ["day", "pm25"]
    pm25_daily["day"] = pd.to_datetime(pm25_daily["day"])

    # Prepare temperature
    wu_agg = wu_data.copy()
    wu_agg["date"] = wu_agg["timestamp"].dt.date
    wu_daily = wu_agg.groupby("date").agg({"temperature_celsius": "mean"}).reset_index()
    wu_daily.columns = ["day", "temperature"]
    wu_daily["day"] = pd.to_datetime(wu_daily["day"])

    # Merge all
    merged = oura_data.copy()
    if not pm25_daily.empty:
        merged = merged.merge(pm25_daily, on="day", how="left")
    if not wu_daily.empty:
        merged = merged.merge(wu_daily, on="day", how="left")

    merged = merged.dropna()

    if len(merged) > 2:
        print(f"\n✅ Complete records: {len(merged)} days")

        # Identify environmental and biometric columns
        oura_cols = [
            col
            for col in merged.columns
            if col not in ["day", "pm25", "temperature", "resident"]
        ]
        env_cols = ["pm25", "temperature"]
        env_cols = [col for col in env_cols if col in merged.columns]

        print(f"\n   Biometric metrics: {oura_cols[:3]}...")
        print(f"   Environmental factors: {env_cols}")

        # Correlation matrix
        corr_data = merged[oura_cols + env_cols].corr()

        # Heatmap
        fig_heat = go.Figure(
            data=go.Heatmap(
                z=corr_data.values,
                x=corr_data.columns,
                y=corr_data.columns,
                colorscale="RdBu",
                zmid=0,
                text=corr_data.values.round(3),
                texttemplate="%{text:.3f}",
                textfont={"size": 10},
            )
        )
        fig_heat.update_layout(
            title="Correlation Matrix: Environmental vs Biometric Metrics",
            height=700,
            width=900,
        )
        output_file = DATA_DIR / "correlation_heatmap.html"
        fig_heat.write_html(str(output_file))
        print("\n📊 Heatmap saved: correlation_heatmap.html")

        # Print key correlations
        print("\n🔍 KEY CORRELATIONS (|r| > 0.1):")
        for env in env_cols:
            if env in corr_data.index:
                strong = corr_data.loc[env, oura_cols].abs().nlargest(3)
                for metric, corr_val in strong.items():
                    try:
                        clean_x = merged[env].dropna()
                        clean_y = merged[metric].dropna()
                        # Get common indices
                        common_idx = clean_x.index.intersection(clean_y.index)
                        _, p = pearsonr(
                            clean_x.loc[common_idx], clean_y.loc[common_idx]
                        )
                        sig = "✓" if p < 0.05 else "✗"
                        print(
                            f"   {sig} {env} → {metric}: r={corr_val:7.4f} (p={p:.3e})"
                        )
                    except Exception as e:
                        print(f"   {env} → {metric}: r={corr_val:7.4f} (Error: {e})")

# ============================================================================
# SUMMARY
# ============================================================================
print("\n" + "=" * 80)
print("✅ ANALYSIS COMPLETE")
print("=" * 80)
print("\n📁 All outputs saved to: data/analysis_outputs/")
print("   - Colocation analyses (HTML interactive plots)")
print("   - Temperature vs HRV scatter and time series")
print("   - Correlation heatmaps and detailed analysis")
print("\n💡 Next Steps:")
print("   1. Open HTML files in browser for interactive exploration")
print("   2. Review statistical significance of correlations")
print("   3. Investigate causal mechanisms based on significant results")
print()
