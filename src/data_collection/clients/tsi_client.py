
import asyncio
import logging
import unicodedata
import pandas as pd
from datetime import datetime
from typing import Any, Dict, Optional

from .base_client import BaseClient
from src.utils.config_loader import get_tsi_devices

log = logging.getLogger(__name__)


def _normalize_measurement_label(name: str) -> str:
    """TSI API may use Unicode subscripts or full words; normalize for comparisons."""
    if not isinstance(name, str):
        return ""
    n = unicodedata.normalize("NFKC", name).strip().upper()
    n = n.replace("₂", "2").replace("\u2082", "2")
    return " ".join(n.split())

def _measurement_value(measurement: dict) -> Any:
    """Prefer nested data.value; some payloads put value at top level."""
    data = measurement.get("data")
    if isinstance(data, dict) and data.get("value") is not None:
        return data.get("value")
    return measurement.get("value")


class TSIClient(BaseClient):
    """Client for fetching data from the TSI API."""

    def __init__(self, client_id: str, client_secret: str, auth_url: str, base_url: str = "https://api-prd.tsilink.com/api/v3/external"):
        super().__init__(base_url, semaphore_limit=3)
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_url = auth_url
        self.device_ids = get_tsi_devices()
        self.headers: Optional[Dict[str, str]] = None

    async def _authenticate(self) -> bool:
        """Authenticates with the TSI API to get an access token using the managed httpx.AsyncClient."""
        params = {'grant_type': 'client_credentials'}
        data = {'client_id': self.client_id, 'client_secret': self.client_secret}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if not self.client:
            log.error("TSIClient httpx.AsyncClient not initialized. Use TSIClient within an 'async with' block.")
            return False
        try:
            log.info("Trying TSI authentication with params and form-encoded body using managed client...")
            auth_resp = await self.client.post(self.auth_url, params=params, data=data, headers=headers)
            auth_resp.raise_for_status()
            auth_json = auth_resp.json()
            self.headers = {"Authorization": f"Bearer {auth_json['access_token']}", "Accept": "application/json"}
            log.info("TSI authentication succeeded with params and form-encoded body.")
            return True
        except Exception as e:
            log.error(f"TSI authentication failed: {e}", exc_info=True)
            return False

    async def _fetch_one_day(self, device_id: str, date_iso: str) -> Optional[pd.DataFrame]:
        """Fetches data for a single device and day using the telemetry endpoint with start_date and end_date parameters."""
        if not self.headers:
            log.error("TSI client is not authenticated.")
            return None

        # Use start_date and end_date parameters in RFC3339 format (required for historical data with measurements)
        # This is the key difference - age parameter returns empty sensor arrays, but start_date/end_date returns full measurements
        from datetime import timedelta
        
        start_iso = f"{date_iso}T00:00:00Z"
        target_date = datetime.strptime(date_iso, "%Y-%m-%d")
        end_date = target_date + timedelta(days=1)
        end_iso = end_date.strftime("%Y-%m-%dT00:00:00Z")
        
        # Use start_date and end_date instead of age to get actual measurement data
        params = {'device_id': device_id, 'start_date': start_iso, 'end_date': end_iso}

        # Use the telemetry endpoint with start_date/end_date to get nested sensor measurements
        records = await self._request("GET", "telemetry", params=params, headers=self.headers)
        log.info(f"TSI RAW API RESPONSE for device {device_id} date {date_iso} (start={start_iso}, end={end_iso}): received {len(records) if records else 0} records")
        
        if not records:
            log.info(f"TSI API returned no records for device {device_id} date {date_iso}.")
            return None
        
        # Parse nested sensor measurements from telemetry response
        data = []
        for row in records:
            timestamp = row.get('cloud_timestamp')
            if not timestamp:
                continue
            
            # Extract metadata from record
            metadata = row.get('metadata', {})
            location = metadata.get('location', {})
            latitude = location.get('latitude')
            longitude = location.get('longitude')
            is_indoor = metadata.get('is_indoor')
            is_public = metadata.get('is_public')
            model = row.get('model')
            cloud_account_id = row.get('cloud_account_id')
            
            # Initialize all sensor values with typed defaults (0.0 for float, '' for string, False for bool)
            # This ensures consistent parquet schemas even when measurements are empty
            # Using 0.0 instead of None prevents null-type columns in parquet
            pm_1_0 = 0.0
            pm_2_5 = 0.0
            pm_4_0 = 0.0
            pm_10 = 0.0
            pm2_5_aqi = 0.0
            pm10_aqi = 0.0
            ncpm0_5 = 0.0
            ncpm1_0 = 0.0
            ncpm2_5 = 0.0
            ncpm4_0 = 0.0
            ncpm10 = 0.0
            temp = 0.0
            rh = 0.0
            tpsize = 0.0
            co2_ppm = 0.0
            co_ppm = 0.0
            baro_inhg = 0.0
            o3_ppb = 0.0
            no2_ppb = 0.0
            so2_ppb = 0.0
            ch2o_ppb = 0.0
            voc_mgm3 = 0.0
            serial = ''  # Initialize serial with empty string
            
            # Extract measurements from nested sensors array
            sensors = row.get('sensors', [])
            for sensor in sensors:
                sensor_serial = sensor.get('serial')
                if sensor_serial:
                    serial = sensor_serial  # Override with actual serial if found
                measurements = sensor.get('measurements', [])
                for measurement in measurements:
                    name = measurement.get('name', '')
                    value = _measurement_value(measurement)
                    
                    # Only update field if value is not None (preserve 0.0 default for missing measurements)
                    if value is None:
                        continue
                    
                    # Map measurement names to fields
                    if name == 'PM 1.0':
                        pm_1_0 = float(value)
                    elif name == 'PM 2.5':
                        pm_2_5 = float(value)
                    elif name == 'PM 4.0':
                        pm_4_0 = float(value)
                    elif name == 'PM 10':
                        pm_10 = float(value)
                    elif name == 'PM 2.5 AQI':
                        pm2_5_aqi = float(value)
                    elif name == 'PM 10 AQI':
                        pm10_aqi = float(value)
                    elif name == 'NC 0.5':
                        ncpm0_5 = float(value)
                    elif name == 'NC 1.0':
                        ncpm1_0 = float(value)
                    elif name == 'NC 2.5':
                        ncpm2_5 = float(value)
                    elif name == 'NC 4.0':
                        ncpm4_0 = float(value)
                    elif name == 'NC 10':
                        ncpm10 = float(value)
                    elif name == 'Temperature':
                        temp = float(value)
                    elif name == 'Relative Humidity':
                        rh = float(value)
                    elif name == 'Typical Particle Size':
                        tpsize = float(value)
                    elif name == 'CO2':
                        co2_ppm = float(value)
                    elif name == 'CO':
                        co_ppm = float(value)
                    elif name == 'Barometric Pressure':
                        baro_inhg = float(value)
                    elif name == 'O3':
                        o3_ppb = float(value)
                    elif name == 'NO2':
                        no2_ppb = float(value)
                    elif name == 'SO2':
                        so2_ppb = float(value)
                    elif name == 'CH2O':
                        ch2o_ppb = float(value)
                    elif name == 'VOC':
                        voc_mgm3 = float(value)
            
            data.append({
                'timestamp': timestamp,
                'cloud_account_id': cloud_account_id,
                'device_id': device_id,
                'model': model,
                'serial': serial,
                'latitude': latitude,
                'longitude': longitude,
                'is_indoor': is_indoor,
                'is_public': is_public,
                'pm1_0': pm_1_0,
                'pm2_5': pm_2_5,
                'pm4_0': pm_4_0,
                'pm10': pm_10,
                'pm2_5_aqi': pm2_5_aqi,
                'pm10_aqi': pm10_aqi,
                'ncpm0_5': ncpm0_5,
                'ncpm1_0': ncpm1_0,
                'ncpm2_5': ncpm2_5,
                'ncpm4_0': ncpm4_0,
                'ncpm10': ncpm10,
                'temperature': temp,
                'rh': rh,
                'tpsize': tpsize,
                'co2_ppm': co2_ppm,
                'co_ppm': co_ppm,
                'baro_inhg': baro_inhg,
                'o3_ppb': o3_ppb,
                'no2_ppb': no2_ppb,
                'so2_ppb': so2_ppb,
                'ch2o_ppb': ch2o_ppb,
                'voc_mgm3': voc_mgm3
            })
        
        if not data:
            log.info(f"No valid sensor measurements found for device {device_id} date {date_iso}.")
            return None
        
        df = pd.DataFrame(data)
        log.info(f"TSI DataFrame for device {device_id} date {date_iso}: shape={df.shape}")
        log.debug(f"TSI columns: {list(df.columns)}\nSample:\n{df.head().to_string(index=False)}")
        
        # Explicitly set dtypes to ensure consistent parquet schema
        # This is critical for BigQuery external tables to work correctly
        dtype_map = {
            'cloud_account_id': 'object',
            'device_id': 'object',
            'model': 'object',
            'serial': 'object',
            'latitude': 'float64',
            'longitude': 'float64',
            'is_indoor': 'bool',
            'is_public': 'bool',
            'pm1_0': 'float64',
            'pm2_5': 'float64',
            'pm4_0': 'float64',
            'pm10': 'float64',
            'pm2_5_aqi': 'float64',
            'pm10_aqi': 'float64',
            'ncpm0_5': 'float64',
            'ncpm1_0': 'float64',
            'ncpm2_5': 'float64',
            'ncpm4_0': 'float64',
            'ncpm10': 'float64',
            'temperature': 'float64',
            'rh': 'float64',
            'tpsize': 'float64',
            'co2_ppm': 'float64',
            'co_ppm': 'float64',
            'baro_inhg': 'float64',
            'o3_ppb': 'float64',
            'no2_ppb': 'float64',
            'so2_ppb': 'float64',
            'ch2o_ppb': 'float64',
            'voc_mgm3': 'float64'
        }
        
        # Apply dtype conversions
        for col, dtype in dtype_map.items():
            if col in df.columns:
                try:
                    df[col] = df[col].astype(dtype)
                except Exception as e:
                    log.warning(f"Could not convert column {col} to {dtype}: {e}")
        
        log.debug(f"TSI DataFrame dtypes after conversion:\n{df.dtypes}")
        
        # Convert timestamp using pandas' flexible ISO8601 parser
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='ISO8601', utc=True)
        
        # Filter to only include records from the target date
        df = df[df['timestamp'].dt.date == target_date.date()]
        
        if df.empty:
            log.info(f"No data for target date {date_iso} after filtering (start_date/end_date returned data from other dates).")
            return None
        
        log.info(f"After filtering to {date_iso}: {len(df)} records remain")
        return df

    async def fetch_data(self, start_date: str, end_date: str, aggregate: bool = False, agg_interval: str = 'h') -> pd.DataFrame:
        """
        Fetches TSI data for a given date range, optionally aggregates into summaries.
        When aggregate is False, returns raw flat-format observations with a 'timestamp' column.
        """
        if not await self._authenticate():
            log.error("TSI authentication failed. No data will be fetched.")
            return pd.DataFrame()

        log.info("Building list of requests for all devices and dates...")
        date_range = pd.date_range(start=start_date, end=end_date)
        requests = [(dev_id, d.strftime("%Y-%m-%d")) for dev_id in self.device_ids for d in date_range]
        tasks = [self._fetch_one_day(dev_id, date_str) for dev_id, date_str in requests]

        log.info(f"Starting async fetch for {len(tasks)} device-date combinations...")
        all_results: list[pd.DataFrame] = []
        from tqdm import tqdm
        for future in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Fetching TSI Data"):
            result = await future
            if result is not None:
                all_results.append(result)

        log.info(f"Fetched data for {len(all_results)} device-date combinations.")

        if not all_results:
            log.warning("No data fetched from TSI API.")
            return pd.DataFrame()

        log.info("Concatenating all results into a single DataFrame...")
        raw_df = pd.concat(all_results, ignore_index=True)
        if raw_df.empty or 'timestamp' not in raw_df.columns:
            log.warning("No valid data after concatenation.")
            return pd.DataFrame()

        log.info("Converting timestamp to datetime...")
        raw_df['timestamp'] = pd.to_datetime(raw_df['timestamp'])
        # Drop rows with missing timestamps to avoid NaTType errors during resampling
        raw_df = raw_df.dropna(subset=['timestamp'])
        if raw_df.empty:
            log.warning("No valid data after dropping rows with missing timestamps.")
            return pd.DataFrame()

        if not aggregate:
            log.info("Aggregation disabled; returning raw TSI DataFrame.")
            return raw_df

        # Aggregation path
        raw_df = raw_df.set_index('timestamp')
        numeric_cols = raw_df.select_dtypes(include='number').columns.tolist()
        agg_dict = {col: 'mean' for col in numeric_cols}
        final_df = raw_df.groupby('device_id').resample(agg_interval).agg(agg_dict)  # type: ignore
        final_df = final_df.reset_index()
        log.info(f"Successfully resampled TSI data to {len(final_df)} records at interval '{agg_interval}'.")
        return final_df
