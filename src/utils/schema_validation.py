"""Schema validation utilities for ensuring consistent data quality across data sources."""

import pandas as pd
import logging
from typing import Dict, List

log = logging.getLogger(__name__)


def validate_schema_consistency(
    df: pd.DataFrame,
    expected_dtypes: Dict[str, str],
    source_name: str = "Unknown"
) -> bool:
    """
    Validate that a DataFrame has the expected schema (columns and types).
    
    Args:
        df: DataFrame to validate
        expected_dtypes: Dictionary mapping column names to expected dtype strings
        source_name: Name of the data source (for logging)
    
    Returns:
        True if schema is valid, False otherwise
    """
    if df.empty:
        log.warning(f"[{source_name}] Cannot validate schema: DataFrame is empty")
        return False
    
    errors = []
    
    # Check for missing columns
    expected_cols = set(expected_dtypes.keys())
    actual_cols = set(df.columns)
    missing_cols = expected_cols - actual_cols
    extra_cols = actual_cols - expected_cols
    
    if missing_cols:
        errors.append(f"Missing columns: {missing_cols}")
    
    if extra_cols:
        log.warning(f"[{source_name}] Extra columns found (not an error): {extra_cols}")
    
    # Check column types
    type_mismatches = []
    for col, expected_dtype in expected_dtypes.items():
        if col not in df.columns:
            continue  # Already reported as missing
        
        actual_dtype = str(df[col].dtype)
        
        # Normalize type names for comparison
        normalized_expected = _normalize_dtype(expected_dtype)
        normalized_actual = _normalize_dtype(actual_dtype)
        
        if normalized_actual != normalized_expected:
            type_mismatches.append(
                f"{col}: expected {expected_dtype}, got {actual_dtype}"
            )
    
    if type_mismatches:
        errors.append(f"Type mismatches: {type_mismatches}")
    
    if errors:
        log.error(f"[{source_name}] Schema validation failed:\n" + "\n".join(errors))
        return False
    
    log.info(f"[{source_name}] Schema validation passed ✓")
    return True


def _normalize_dtype(dtype_str: str) -> str:
    """Normalize dtype string for comparison."""
    dtype_str = str(dtype_str).lower()
    
    # Map equivalent types
    type_map = {
        'int64': 'int64',
        'int32': 'int64',  # Allow int32 as int64
        'float64': 'float64',
        'float32': 'float64',  # Allow float32 as float64
        'object': 'object',
        'string': 'object',  # string and object are equivalent
        'bool': 'bool',
        'boolean': 'bool',
        'datetime64[ns]': 'datetime64',
        'datetime64[ns, utc]': 'datetime64',
    }
    
    for pattern, normalized in type_map.items():
        if pattern in dtype_str:
            return normalized
    
    return dtype_str


def check_null_coverage(
    df: pd.DataFrame,
    critical_columns: List[str],
    min_coverage: float = 0.90,
    source_name: str = "Unknown"
) -> bool:
    """
    Check that critical columns have sufficient non-null coverage.
    
    Args:
        df: DataFrame to check
        critical_columns: List of column names that must have good coverage
        min_coverage: Minimum required non-null ratio (0.0 to 1.0)
        source_name: Name of the data source (for logging)
    
    Returns:
        True if coverage is acceptable, False otherwise
    """
    if df.empty:
        log.warning(f"[{source_name}] Cannot check coverage: DataFrame is empty")
        return False
    
    issues = []
    
    for col in critical_columns:
        if col not in df.columns:
            issues.append(f"{col}: column missing")
            continue
        
        non_null_count = df[col].notna().sum()
        total_count = len(df)
        coverage = non_null_count / total_count if total_count > 0 else 0.0
        
        if coverage < min_coverage:
            issues.append(
                f"{col}: {coverage:.1%} coverage (need {min_coverage:.0%})"
            )
        else:
            log.debug(f"[{source_name}] {col}: {coverage:.1%} coverage ✓")
    
    if issues:
        log.error(
            f"[{source_name}] Coverage check failed:\n" + "\n".join(issues)
        )
        return False
    
    log.info(f"[{source_name}] Coverage check passed ✓")
    return True


def get_schema_info(df: pd.DataFrame) -> Dict[str, str]:
    """
    Get schema information from a DataFrame.
    
    Returns:
        Dictionary mapping column names to dtype strings
    """
    schema = {}
    for col, dtype in df.dtypes.items():
        schema[str(col)] = str(dtype)
    return schema


def log_schema_comparison(
    df1: pd.DataFrame,
    df2: pd.DataFrame,
    name1: str = "DataFrame 1",
    name2: str = "DataFrame 2"
) -> None:
    """
    Log a comparison of schemas between two DataFrames.
    Useful for debugging schema consistency issues.
    """
    schema1 = get_schema_info(df1)
    schema2 = get_schema_info(df2)
    
    all_cols = set(schema1.keys()) | set(schema2.keys())
    
    log.info(f"\n{'='*60}")
    log.info(f"Schema Comparison: {name1} vs {name2}")
    log.info(f"{'='*60}")
    log.info(f"{'Column':<25} | {name1:<15} | {name2:<15}")
    log.info(f"{'-'*60}")
    
    for col in sorted(all_cols):
        dtype1 = schema1.get(col, "MISSING")
        dtype2 = schema2.get(col, "MISSING")
        
        match_marker = "✓" if dtype1 == dtype2 else "✗"
        log.info(f"{col:<25} | {dtype1:<15} | {dtype2:<15} {match_marker}")
    
    log.info(f"{'='*60}\n")


# Pre-defined schemas for validation

TSI_EXPECTED_SCHEMA = {
    'timestamp': 'datetime64',
    'cloud_account_id': 'object',
    'native_sensor_id': 'object',  # Changed from device_id
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
    'humidity': 'float64',  # Changed from rh
    'tpsize': 'float64',
    'co2_ppm': 'float64',
    'co_ppm': 'float64',
    'baro_inhg': 'float64',
    'o3_ppb': 'float64',
    'no2_ppb': 'float64',
    'so2_ppb': 'float64',
    'ch2o_ppb': 'float64',
    'voc_mgm3': 'float64',
    # Additional columns from raw data
    'ts': 'datetime64',
    'latitude_f': 'float64',
    'longitude_f': 'float64',
}

TSI_CRITICAL_COLUMNS = [
    'timestamp',
    'native_sensor_id',  # Changed from device_id
    'pm2_5',
    'temperature'
]

WU_EXPECTED_SCHEMA = {
    'timestamp': 'datetime64',
    'native_sensor_id': 'object',
    'temperature': 'float64',
    'temperature_high': 'float64',
    'temperature_low': 'float64',
    'humidity': 'float64',
    'humidity_high': 'float64',
    'humidity_low': 'float64',
    'precip_rate': 'float64',
    'precip_total': 'float64',
    'wind_speed_avg': 'float64',
    'wind_speed_high': 'float64',
    'wind_speed_low': 'float64',
    'wind_gust_avg': 'float64',
    'wind_gust_high': 'float64',
    'wind_gust_low': 'float64',
    'wind_direction_avg': 'float64',
    'pressure_max': 'float64',
    'pressure_min': 'float64',
    'pressure_trend': 'float64',
    'solar_radiation': 'float64',
    'uv_high': 'float64',
    'wind_chill_avg': 'float64',
    'wind_chill_high': 'float64',
    'wind_chill_low': 'float64',
    'heat_index_avg': 'float64',
    'heat_index_high': 'float64',
    'heat_index_low': 'float64',
    'dew_point_avg': 'float64',
    'dew_point_high': 'float64',
    'dew_point_low': 'float64',
    'qc_status': 'float64',
    'obsTimeLocal': 'object',
    'ts': 'datetime64',
    'lat_f': 'float64',
    'lon_f': 'float64',
    'epoch': 'float64',
    'lat': 'float64',
    'lon': 'float64',
    'tz': 'object',
}

WU_CRITICAL_COLUMNS = [
    'timestamp',
    'native_sensor_id',
    'temperature',
    'humidity',
    'pressure_max'
]


def validate_tsi_schema(df: pd.DataFrame) -> bool:
    """Validate TSI data schema."""
    return validate_schema_consistency(df, TSI_EXPECTED_SCHEMA, "TSI")


def validate_wu_schema(df: pd.DataFrame) -> bool:
    """Validate Weather Underground data schema."""
    return validate_schema_consistency(df, WU_EXPECTED_SCHEMA, "WU")


def check_tsi_coverage(df: pd.DataFrame) -> bool:
    """Check TSI critical column coverage."""
    return check_null_coverage(df, TSI_CRITICAL_COLUMNS, min_coverage=0.90, source_name="TSI")


def check_wu_coverage(df: pd.DataFrame) -> bool:
    """Check Weather Underground critical column coverage."""
    return check_null_coverage(df, WU_CRITICAL_COLUMNS, min_coverage=0.95, source_name="WU")
