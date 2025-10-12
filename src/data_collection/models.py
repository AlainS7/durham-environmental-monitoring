
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# -----------------------------------------------------------------------------
# Pydantic Models for API Response Validation
# -----------------------------------------------------------------------------
#
# These models define the expected structure of responses from the Weather Underground (WU)
# and TSI APIs. They are intended to be used for parsing and validating incoming JSON data
# in the API clients (e.g., WUClient, TSIClient) to ensure robustness against unexpected
# API changes or malformed data.
#
# Recommended usage in a client:
#
# import pydantic
# ...
# try:
#     json_data = response.json()
#     validated_data = WUResponse.model_validate(json_data)
#     # work with validated_data.observations
# except pydantic.ValidationError as e:
#     log.error(f"API response validation failed: {e}")
#     return None
#
# This approach helps catch schema mismatches early and improves data quality.
# -----------------------------------------------------------------------------


# --- WU Models ---

# only for imperial WU data (currently only using WU)
# class WUImperial(BaseModel):
#     tempHigh: Optional[float] = None
#     tempLow: Optional[float] = None
#     tempAvg: Optional[float] = None
#     windspeedHigh: Optional[float] = None
#     windspeedLow: Optional[float] = None
#     windspeedAvg: Optional[float] = None
#     windgustHigh: Optional[float] = None
#     windgustLow: Optional[float] = None
#     windgustAvg: Optional[float] = None
#     dewptHigh: Optional[float] = None
#     dewptLow: Optional[float] = None
#     dewptAvg: Optional[float] = None
#     windchillHigh: Optional[float] = None
#     windchillLow: Optional[float] = None
#     windchillAvg: Optional[float] = None
#     heatindexHigh: Optional[float] = None
#     heatindexLow: Optional[float] = None
#     heatindexAvg: Optional[float] = None
#     pressureMax: Optional[float] = None
#     pressureMin: Optional[float] = None
#     pressureTrend: Optional[float] = None
#     precipRate: Optional[float] = None
#     precipTotal: Optional[float] = None

class WUObservation(BaseModel):
    stationID: str
    tz: Optional[str] = None
    obsTimeUtc: datetime
    obsTimeLocal: Optional[str] = None
    epoch: Optional[int] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    solarRadiationHigh: Optional[float] = None
    uvHigh: Optional[float] = None
    winddirAvg: Optional[float] = None
    humidityHigh: Optional[float] = None
    humidityLow: Optional[float] = None
    humidityAvg: Optional[float] = None
    qcStatus: Optional[int] = None
    dewptAvg: Optional[float] = None
    dewptHigh: Optional[float] = None
    dewptLow: Optional[float] = None
    heatindexAvg: Optional[float] = None
    heatindexHigh: Optional[float] = None
    heatindexLow: Optional[float] = None
    precipRate: Optional[float] = None
    precipTotal: Optional[float] = None
    pressureMax: Optional[float] = None
    pressureMin: Optional[float] = None
    pressureTrend: Optional[float] = None
    tempAvg: Optional[float] = None
    tempHigh: Optional[float] = None
    tempLow: Optional[float] = None
    windchillAvg: Optional[float] = None
    windchillHigh: Optional[float] = None
    windchillLow: Optional[float] = None
    windgustAvg: Optional[float] = None
    windgustHigh: Optional[float] = None
    windgustLow: Optional[float] = None
    windspeedAvg: Optional[float] = None
    windspeedHigh: Optional[float] = None
    windspeedLow: Optional[float] = None
    # imperial: Optional[WUImperial] = None
    # Metric object contains nested temperature/wind/precip data
    # Pydantic will accept extra fields if we use model_config allow_extra
    model_config = {'extra': 'allow'}  # Allow 'metric' and other extra fields from API

class WUResponse(BaseModel):
    observations: List[WUObservation]


# --- TSI Models ---

# Flat-format TSI record for direct validation of flat-format endpoint
class TSIFlatRecord(BaseModel):
    cloud_account_id: Optional[str] = None
    cloud_device_id: Optional[str] = None
    # The API sometimes uses 'timestamp' as the field name; accept either by using an alias.
    cloud_timestamp: Optional[datetime] = Field(default=None, alias='timestamp')
    is_indoor: Optional[bool] = None
    is_public: Optional[bool] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    mcpm10: Optional[float] = None
    mcpm10_aqi: Optional[float] = None
    mcpm1x0: Optional[float] = None
    mcpm2x5: Optional[float] = None
    mcpm2x5_aqi: Optional[float] = None
    mcpm4x0: Optional[float] = None
    model: Optional[str] = None
    ncpm0x5: Optional[float] = None
    ncpm10: Optional[float] = None
    ncpm1x0: Optional[float] = None
    ncpm2x5: Optional[float] = None
    ncpm4x0: Optional[float] = None
    rh: Optional[float] = None
    serial: Optional[str] = None
    temperature: Optional[float] = None
    tpsize: Optional[float] = None
    co2_ppm: Optional[float] = None
    co_ppm: Optional[float] = None
    baro_inhg: Optional[float] = None
    o3_ppb: Optional[float] = None
    no2_ppb: Optional[float] = None
    so2_ppb: Optional[float] = None
    ch2o_ppb: Optional[float] = None
    voc_mgm3: Optional[float] = None
