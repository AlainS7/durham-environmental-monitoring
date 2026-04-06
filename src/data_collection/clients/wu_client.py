

import asyncio
import pandas as pd
import logging
from tqdm import tqdm
from typing import Optional
import pydantic
from enum import Enum

from .base_client import BaseClient
from src.utils.config_loader import get_wu_stations
from src.data_collection.models import WUResponse

class EndpointStrategy(Enum):
    ALL = "all"
    MULTIDAY = "multiday"
    HOURLY = "hourly"
    HYBRID = "hybrid"

log = logging.getLogger(__name__)

class WUClient(BaseClient):
    @staticmethod
    def _normalize_endpoint_strategy(
        endpoint_strategy: EndpointStrategy | str,
    ) -> EndpointStrategy:
        if isinstance(endpoint_strategy, EndpointStrategy):
            return endpoint_strategy
        try:
            return EndpointStrategy(str(endpoint_strategy).strip().lower())
        except ValueError:
            log.warning(
                "Invalid WU endpoint strategy '%s'; defaulting to HYBRID",
                endpoint_strategy,
            )
            return EndpointStrategy.HYBRID

    def _build_requests(self, start_date: str, end_date: str) -> list:
        """
        Builds a list of (station_id, date_str, end_date) tuples for the selected endpoint strategy.
        - HOURLY: one request per station per day (for /history/hourly endpoint)
        - MULTIDAY: one request per station per day (for /history/all endpoint)
        - HYBRID: two requests per station per day (HOURLY + MULTIDAY), merged later
        - ALL: one request per station for the full date range (for /observations/all endpoint)
        """
        requests = []
        date_range = pd.date_range(start=start_date, end=end_date)
        if self.endpoint_strategy in (
            EndpointStrategy.HOURLY,
            EndpointStrategy.MULTIDAY,
        ):
            # HOURLY and MULTIDAY: build (station, date) requests for each day in range
            for s in self.stations:
                if 'stationId' not in s:
                    continue
                station_id = s['stationId']
                for d in date_range:
                    date_str = d.strftime("%Y-%m-%d")
                    requests.append((station_id, date_str, None, self.endpoint_strategy))
        elif self.endpoint_strategy == EndpointStrategy.HYBRID:
            # HYBRID mode: collect rich hourly fields + higher-frequency intraday rows
            # and reconcile them by (stationID, obsTimeUtc) after fetch.
            for s in self.stations:
                if 'stationId' not in s:
                    continue
                station_id = s['stationId']
                for d in date_range:
                    date_str = d.strftime("%Y-%m-%d")
                    requests.append((station_id, date_str, None, EndpointStrategy.HOURLY))
                    requests.append((station_id, date_str, None, EndpointStrategy.MULTIDAY))
        elif self.endpoint_strategy == EndpointStrategy.ALL:
            # ALL: build (station, start_date, end_date) requests for each station
            for s in self.stations:
                if 'stationId' not in s:
                    continue
                station_id = s['stationId']
                requests.append((station_id, start_date, end_date, EndpointStrategy.ALL))
        else:
            # Fallback: treat as per-day requests
            for s in self.stations:
                if 'stationId' not in s:
                    continue
                station_id = s['stationId']
                for d in date_range:
                    date_str = d.strftime("%Y-%m-%d")
                    requests.append((station_id, date_str, None, EndpointStrategy.HOURLY))
        return requests

    async def _execute_fetches(self, requests: list) -> list:
        """
        Executes async fetches for the given requests and collects results.
        - For ALL: calls _fetch_one(station_id, start_date, end_date, strategy=ALL)
        - For HOURLY/MULTIDAY/HYBRID: calls _fetch_one(station_id, date_str, strategy=...)
        """
        all_results = []
        tasks = []
        for req in requests:
            station_id, start_date, end_date, strategy = req
            tasks.append(self._fetch_one(station_id, start_date, end_date, strategy))
        for future in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Fetching WU Data"):
            result = await future
            if result is not None and not result.empty:
                all_results.append(result)
        return all_results
    """Client for fetching data from the Weather Underground API."""

    # FEAT: Replace boolean parameters with an enum-based endpoint strategy
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.weather.com/v2/pws",
        endpoint_strategy: EndpointStrategy | str = EndpointStrategy.HYBRID,
    ):
        """
        endpoint_strategy: Specifies the endpoint strategy to use. Options are:
            - EndpointStrategy.ALL: Use 'observations/all' (multi-day, no date param).
            - EndpointStrategy.MULTIDAY: Use 'history/all' (per-day, denser intraday observations).
            - EndpointStrategy.HOURLY: Use 'history/hourly' endpoint (per-day, per-station, FULL HISTORICAL DATA with all fields).
            - EndpointStrategy.HYBRID: Fetch both HOURLY + MULTIDAY and reconcile by timestamp.
        
        NOTE:
            - HOURLY provides full weather fields but at coarser cadence.
            - MULTIDAY/ALL can provide denser intraday rows but fewer fields.
            - HYBRID keeps richer hourly records and supplements with denser intraday points.
        """
        super().__init__(base_url, api_key)
        self.stations = get_wu_stations()
        self.endpoint_strategy = self._normalize_endpoint_strategy(endpoint_strategy)

    async def _fetch_one(
        self,
        station_id: str,
        start_date: str,
        end_date: str = "",
        strategy: EndpointStrategy | None = None,
    ) -> Optional[pd.DataFrame]:
        """
        Fetches all rapid observations for a single station and date range, returns as DataFrame.
        If using /all endpoint, fetches all data for the range in one call; else, expects start_date == end_date and fetches for that day.
        If using /history/hourly endpoint, fetches hourly summary for a single day and station.
        Uses Pydantic WUResponse for validation.
        """
        mode = strategy or self.endpoint_strategy
        data = None
        filter_end_date_for_helper = "" # Initialize for clarity
        if mode == EndpointStrategy.HOURLY:
            # Use /history/hourly endpoint (per-day, per-station) - Returns ALL fields including temp, wind, precip
            # This is the PWS Historical v2 API that returns complete weather data
            endpoint = "history/hourly"
            date_param = start_date.replace("-", "") # The date param for this endpoint is YYYYMMDD
            params = {
                "stationId": station_id,
                "date": date_param,
                "format": "json",
                "apiKey": self.api_key,
                "units": "e",  # Use English units (imperial) to match expected response format
                "numericPrecision": "decimal"
            }
            data = await self._request("GET", endpoint, params=params)
            filter_end_date_for_helper = start_date # For history/hourly, filter for just the start_date
        elif mode == EndpointStrategy.ALL:
            endpoint = "observations/all"
            filter_end_date_for_helper = end_date if end_date else start_date # Use the actual end_date for filtering
            params = {
                "stationId": station_id,
                "format": "json",
                "apiKey": self.api_key,
                "units": "m",
                "startDate": start_date,  # YYYY-MM-DD
                "endDate": filter_end_date_for_helper  # YYYY-MM-DD
            }
            data = await self._request("GET", endpoint, params=params)
        else:
            # MULTIDAY path: use date-addressable dense history endpoint.
            endpoint = "history/all"
            date_param = start_date.replace("-", "")  # YYYYMMDD
            filter_end_date_for_helper = start_date
            params = {
                "stationId": station_id,
                "date": date_param,
                "format": "json",
                "apiKey": self.api_key,
                "units": "m"
            }
            data = await self._request("GET", endpoint, params=params)

        # Validate and parse using Pydantic WUResponse
        try:
            validated = WUResponse.model_validate(data)
        except pydantic.ValidationError as e:
            log.error(f"WU API response validation failed for station {station_id}: {e}")
            return None

        # Convert validated observations to dicts for DataFrame
        obs_dicts = [obs.model_dump() for obs in validated.observations]
        
        # Flatten the 'metric' and 'imperial' nested objects into top-level fields
        # WU API returns temp/wind/precip data inside these nested objects
        # Historical API (history/hourly) returns data in 'imperial' or 'metric' object based on units parameter
        for o in obs_dicts:
            # Flatten 'imperial' object (contains temperature, wind speed, precipitation in imperial units)
            if 'imperial' in o and isinstance(o['imperial'], dict):
                for key, value in o['imperial'].items():
                    # Overwrite top-level field with imperial value
                    # This handles case where Pydantic sets top-level fields to None but imperial has actual values
                    o[key] = value
                o.pop('imperial', None)  # Remove the nested object after flattening
            
            # Flatten 'metric' object (contains temperature, wind speed, precipitation in metric units)
            # Only used if units=m was specified in request
            if 'metric' in o and isinstance(o['metric'], dict):
                for key, value in o['metric'].items():
                    # Overwrite top-level field with metric value (metric values take precedence)
                    # This handles case where Pydantic sets top-level fields to None but metric has actual values
                    o[key] = value
                o.pop('metric', None)  # Remove the nested object after flattening

        if obs_dicts:
            df = pd.DataFrame(obs_dicts)
            log.debug(f"Raw DataFrame shape for station {station_id}: {df.shape}")
            df['stationID'] = station_id
            # Filter to just the requested date range
            if 'obsTimeUtc' in df.columns:
                df['obsTimeUtc'] = pd.to_datetime(df['obsTimeUtc'])
                date_start_utc = pd.to_datetime(start_date).tz_localize('UTC')
                # The filter_end_date is inclusive, so we add one day for the exclusive upper bound
                date_end_utc = pd.to_datetime(filter_end_date_for_helper).tz_localize('UTC') + pd.Timedelta(days=1)
                mask = (df['obsTimeUtc'] >= date_start_utc) & (df['obsTimeUtc'] < date_end_utc)
                df = df.loc[mask]
                log.debug(f"Filtered DataFrame shape for station {station_id} from {start_date} to {filter_end_date_for_helper}: {df.shape}")
            return df
        return None

    # _process_and_filter_observations is no longer needed; validation and flattening are handled in _fetch_one

    async def fetch_data(self, start_date: str, end_date: str, aggregate: bool = False, agg_interval: str = 'h') -> pd.DataFrame:
        """
        Fetches WU observations for a date range. When aggregate is False, returns raw observations
        with an 'obsTimeUtc' column. When True, returns resampled summaries per stationID.
        """
        if not self.api_key or not self.stations:
            log.error("Weather Underground API key or station list is not configured properly.")
            return pd.DataFrame()

        log.info(f"Building list of requests for endpoint strategy: {self.endpoint_strategy.name}")
        requests = self._build_requests(start_date, end_date)
        all_results = await self._execute_fetches(requests)
        log.info(f"Fetched data for {len(all_results)} requests.")

        if not all_results:
            log.warning("No data fetched from WU API.")
            return pd.DataFrame()

        log.info("Concatenating all results into a single DataFrame...")
        raw_df = pd.concat(all_results, ignore_index=True)
        if raw_df.empty or 'obsTimeUtc' not in raw_df.columns:
            log.warning("No valid data after concatenation.")
            return pd.DataFrame()

        log.info("Converting obsTimeUtc to datetime...")
        raw_df['obsTimeUtc'] = pd.to_datetime(raw_df['obsTimeUtc'])
        if {'stationID', 'obsTimeUtc'}.issubset(raw_df.columns):
            # Collapse overlap between HOURLY and MULTIDAY requests on same timestamp.
            # For duplicate rows, keep the first non-null value per column.
            order_cols = ['stationID', 'obsTimeUtc']
            raw_df = raw_df.sort_values(order_cols)
            raw_df = (
                raw_df.groupby(order_cols, as_index=False, sort=False)
                .agg(lambda s: s.dropna().iloc[0] if not s.dropna().empty else s.iloc[0])
                .reset_index(drop=True)
            )

        if not aggregate:
            log.info("Aggregation disabled; returning raw observations DataFrame.")
            return raw_df

        # Aggregation path
        raw_df = raw_df.set_index('obsTimeUtc')
        numeric_cols = raw_df.select_dtypes(include='number').columns.tolist()
        exclude_cols = ['epoch', 'lat', 'lon', 'qcStatus']
        agg_cols = [col for col in numeric_cols if col not in exclude_cols]
        agg_dict = {col: 'mean' for col in agg_cols}
        final_df = raw_df.groupby('stationID').resample(agg_interval).agg(agg_dict)  # type: ignore
        final_df = final_df.reset_index()
        log.info(f"Successfully resampled WU data to {len(final_df)} records at interval '{agg_interval}'.")
        return final_df
