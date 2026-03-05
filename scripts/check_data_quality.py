#!/usr/bin/env python3
"""
Data Quality Monitoring Script

Monitors BigQuery tables for schema consistency and data coverage issues.
Checks both raw and transformed tables for quality metrics.
Alerts if any metrics drop below configured thresholds.

Usage:
    python scripts/check_data_quality.py --start 2025-10-01 --end 2025-10-04
    python scripts/check_data_quality.py --days 7  # Check last 7 days
    python scripts/check_data_quality.py --source TSI --verbose
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Tuple

from google.cloud import bigquery

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.schema_validation import (
    TSI_EXPECTED_SCHEMA,
    WU_EXPECTED_SCHEMA,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
log = logging.getLogger(__name__)

# Quality thresholds
COVERAGE_THRESHOLDS = {
    'TSI': 0.90,  # 90% minimum coverage for TSI data
    'WU': 0.95,   # 95% minimum coverage for WU data
}

EXPECTED_SCHEMAS = {
    'TSI': TSI_EXPECTED_SCHEMA,
    'WU': WU_EXPECTED_SCHEMA,
}


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Monitor BigQuery data quality for sensor data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    # Date range options
    date_group = parser.add_mutually_exclusive_group(required=True)
    date_group.add_argument(
        '--days',
        type=int,
        help='Check last N days of data',
    )
    date_group.add_argument(
        '--start',
        type=str,
        help='Start date (YYYY-MM-DD)',
    )
    
    parser.add_argument(
        '--end',
        type=str,
        help='End date (YYYY-MM-DD), required if --start is used',
    )
    
    parser.add_argument(
        '--source',
        type=str,
        choices=['TSI', 'WU', 'both'],
        default='both',
        help='Data source to check (default: both)',
    )
    
    parser.add_argument(
        '--dataset',
        type=str,
        default='sensors',
        help='BigQuery dataset name (default: sensors)',
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose logging',
    )
    
    parser.add_argument(
        '--fail-on-issues',
        action='store_true',
        help='Exit with error code if quality issues found',
    )
    
    args = parser.parse_args()
    
    # Validate date arguments
    if args.start and not args.end:
        parser.error('--end is required when --start is specified')
    
    return args


def calculate_date_range(args: argparse.Namespace) -> Tuple[str, str]:
    """Calculate start and end dates based on arguments."""
    if args.days:
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=args.days - 1)
        return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')
    else:
        return args.start, args.end


def check_raw_table_schema(
    client: bigquery.Client,
    dataset: str,
    source: str,
    start_date: str,
    end_date: str,
) -> Tuple[bool, List[str]]:
    """
    Check that raw materialized table has data for the date range.
    
    Returns:
        Tuple of (is_valid, issues_list)
    """
    log.info(f"Checking raw {source} table from {start_date} to {end_date}")
    
    issues = []
    
    # Determine table name based on source
    if source == 'TSI':
        table_name = 'tsi_raw_materialized'
        date_col = 'ts'
    else:  # WU - would need to update this if WU uses different naming
        log.warning(f"Skipping raw table check for {source} (not implemented)")
        return True, []
    
    # Query to count records per day
    query = f"""
    SELECT 
        DATE({date_col}) as date,
        COUNT(*) as row_count
    FROM `{dataset}.{table_name}`
    WHERE DATE({date_col}) BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY date
    ORDER BY date
    """
    
    try:
        df = client.query(query).to_dataframe()
        
        if df.empty:
            issues.append(f"No raw {source} data found for date range")
            return False, issues
        
        # Check for expected days
        expected_days = (
            datetime.strptime(end_date, '%Y-%m-%d').date() -
            datetime.strptime(start_date, '%Y-%m-%d').date()
        ).days + 1
        
        actual_days = len(df)
        if actual_days < expected_days:
            missing_days = expected_days - actual_days
            issues.append(
                f"Raw {source} table missing {missing_days} days "
                f"(expected {expected_days}, found {actual_days})"
            )
            log.warning(f"Missing days in raw {source}: expected {expected_days}, found {actual_days}")
        
        # Check for days with very low record counts (potential issues)
        low_count_threshold = 100  # Arbitrary threshold
        low_days = df[df['row_count'] < low_count_threshold]
        if not low_days.empty:
            for _, row in low_days.iterrows():
                issues.append(
                    f"Raw {source} on {row['date']}: only {row['row_count']} records "
                    f"(below {low_count_threshold} threshold)"
                )
                log.warning(f"Low record count for raw {source} on {row['date']}: {row['row_count']}")
        
        if not issues:
            log.info(f"Raw {source} table check passed ({actual_days} days, {df['row_count'].sum()} total records)")
            return True, []
        
        return False, issues
        
    except Exception as e:
        issues.append(f"Error checking raw {source} table: {str(e)}")
        log.error(f"Failed to check raw {source} table: {e}", exc_info=True)
        return False, issues


def check_coverage(
    client: bigquery.Client,
    dataset: str,
    source: str,
    start_date: str,
    end_date: str,
) -> Tuple[bool, List[str]]:
    """
    Check data coverage in transformed tables.
    
    Returns:
        Tuple of (is_valid, issues_list)
    """
    log.info(f"Checking coverage for {source} from {start_date} to {end_date}")
    
    issues = []
    threshold = COVERAGE_THRESHOLDS[source]
    
    # Query long-format table for coverage
    # Note: TSI metrics can be identified by pm2_5, ncpm*, co2_ppm, etc.
    # WU metrics can be identified by dewpoint, pressure_in, etc.
    tsi_metrics = ['pm2_5', 'pm10', 'pm1_0', 'pm4_0', 'ncpm0_5', 'ncpm1_0', 'ncpm2_5', 'ncpm4_0', 
                   'ncpm10', 'temperature', 'humidity', 'co2_ppm', 'co_ppm', 'baro_inhg', 
                   'o3_ppb', 'no2_ppb', 'so2_ppb', 'ch2o_ppb']
    wu_metrics = ['dewpoint', 'pressure_in', 'wind_speed', 'wind_gust']
    
    if source == 'TSI':
        metric_filter = "AND l.metric_name IN ({})".format(
            ', '.join(f"'{m}'" for m in tsi_metrics)
        )
    else:  # WU
        metric_filter = "AND l.metric_name IN ({})".format(
            ', '.join(f"'{m}'" for m in wu_metrics)
        )
    
    query = f"""
    SELECT 
        DATE(l.timestamp) as date,
        l.metric_name as metric,
        COUNT(*) as reading_count,
        COUNT(DISTINCT l.native_sensor_id) as device_count,
        COUNTIF(l.value IS NULL) as null_count,
        COUNTIF(l.value IS NOT NULL) as valid_count
    FROM `{dataset}.sensor_readings_long` l
    WHERE DATE(l.timestamp) BETWEEN '{start_date}' AND '{end_date}'
      {metric_filter}
    GROUP BY date, metric
    ORDER BY date, metric
    """
    
    try:
        df = client.query(query).to_dataframe()
        
        if df.empty:
            issues.append(f"No transformed data found for {source} in date range")
            return False, issues
        
        # Calculate coverage by metric
        df['coverage'] = df['valid_count'] / (df['valid_count'] + df['null_count'])
        
        # Check for metrics below threshold
        low_coverage = df[df['coverage'] < threshold]
        
        if not low_coverage.empty:
            for _, row in low_coverage.iterrows():
                issues.append(
                    f"{source} {row['metric']} on {row['date']}: "
                    f"{row['coverage']:.1%} coverage (below {threshold:.0%} threshold)"
                )
                log.warning(
                    f"Low coverage: {source} {row['metric']} on {row['date']}: {row['coverage']:.1%}"
                )
        
        # Check for missing days
        expected_days = (
            datetime.strptime(end_date, '%Y-%m-%d').date() -
            datetime.strptime(start_date, '%Y-%m-%d').date()
        ).days + 1
        
        actual_days = df['date'].nunique()
        if actual_days < expected_days:
            issues.append(
                f"{source} missing {expected_days - actual_days} days in date range "
                f"(expected {expected_days}, found {actual_days})"
            )
            log.warning(f"Missing days for {source}: expected {expected_days}, found {actual_days}")
        
        if not issues:
            log.info(f"Coverage validation passed for {source}")
            return True, []
        
        return False, issues
        
    except Exception as e:
        issues.append(f"Error checking coverage: {str(e)}")
        log.error(f"Failed to check coverage: {e}", exc_info=True)
        return False, issues


def check_raw_tsi_metrics(
    client: bigquery.Client,
    dataset: str,
    start_date: str,
    end_date: str,
) -> Tuple[bool, List[str]]:
    """
    Check for NULL values in critical TSI raw metrics (pm2_5, temperature, humidity).
    
    These metrics should NEVER be NULL if TSI data is properly collected.
    NULL values indicate the TSI parser was bypassed or API data malformed.
    
    Returns:
        Tuple of (is_valid, issues_list)
    """
    log.info(f"Checking TSI raw metric NULLs from {start_date} to {end_date}")
    
    issues = []
    
    # Check for NULL values in critical TSI metrics
    query = f"""
    SELECT 
        DATE(ts) as date,
        COUNT(*) as total_records,
        COUNTIF(pm2_5 IS NULL) as null_pm25,
        COUNTIF(temperature IS NULL) as null_temp,
        COUNTIF(humidity IS NULL) as null_humidity,
        COUNTIF(co2_ppm IS NULL) as null_co2,
        ROUND(100.0 * COUNTIF(pm2_5 IS NULL) / COUNT(*), 2) as null_pm25_pct,
        ROUND(100.0 * COUNTIF(temperature IS NULL) / COUNT(*), 2) as null_temp_pct,
        ROUND(100.0 * COUNTIF(humidity IS NULL) / COUNT(*), 2) as null_humidity_pct
    FROM `{dataset}.tsi_raw_materialized`
    WHERE DATE(ts) BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY date
    ORDER BY date DESC
    """
    
    try:
        df = client.query(query).to_dataframe()
        
        if df.empty:
            issues.append("No TSI raw data found in date range")
            return False, issues
        
        # Critical metrics should have <2% NULL values
        # (Some NULL is OK for co2 due to sensor failures, but pm2_5/temp/humidity should be solid)
        critical_threshold = 2.0  # 2%
        
        for _, row in df.iterrows():
            date = row['date']
            total = row['total_records']
            
            # Check pm2_5 (most critical)
            if row['null_pm25_pct'] > critical_threshold:
                issues.append(
                    f"TSI pm2_5 on {date}: {row['null_pm25_pct']:.1f}% NULL "
                    f"({row['null_pm25']}/{total} records) - CRITICAL: Parser may have failed"
                )
                log.error(
                    f"HIGH NULL rate for TSI pm2_5 on {date}: {row['null_pm25_pct']:.1f}%"
                )
            
            # Check temperature
            if row['null_temp_pct'] > critical_threshold:
                issues.append(
                    f"TSI temperature on {date}: {row['null_temp_pct']:.1f}% NULL "
                    f"({row['null_temp']}/{total} records)"
                )
                log.warning(
                    f"HIGH NULL rate for TSI temperature on {date}: {row['null_temp_pct']:.1f}%"
                )
            
            # Check humidity
            if row['null_humidity_pct'] > critical_threshold:
                issues.append(
                    f"TSI humidity on {date}: {row['null_humidity_pct']:.1f}% NULL "
                    f"({row['null_humidity']}/{total} records)"
                )
                log.warning(
                    f"HIGH NULL rate for TSI humidity on {date}: {row['null_humidity_pct']:.1f}%"
                )
        
        if not issues:
            log.info(f"TSI raw metric NULL check passed (all <{critical_threshold}%)")
            return True, []
        
        return False, issues
        
    except Exception as e:
        issues.append(f"Error checking TSI raw metrics: {str(e)}")
        log.error(f"Failed to check TSI raw metrics: {e}", exc_info=True)
        return False, issues


def check_aggregate_consistency(
    client: bigquery.Client,
    dataset: str,
    source: str,
    start_date: str,
    end_date: str,
) -> Tuple[bool, List[str]]:
    """
    Check that aggregate tables are consistent with raw data.
    
    Returns:
        Tuple of (is_valid, issues_list)
    """
    log.info(f"Checking aggregate consistency for {source} from {start_date} to {end_date}")
    
    issues = []
    
    # Compare row counts between long and hourly tables
    # Use metric names to identify source
    tsi_metrics = ['pm2_5', 'pm10', 'pm1_0', 'pm4_0', 'ncpm0_5', 'ncpm1_0', 'ncpm2_5', 'ncpm4_0', 
                   'ncpm10', 'temperature', 'humidity', 'co2_ppm', 'co_ppm', 'baro_inhg', 
                   'o3_ppb', 'no2_ppb', 'so2_ppb', 'ch2o_ppb']
    wu_metrics = ['dewpoint', 'pressure_in', 'wind_speed', 'wind_gust']
    
    if source == 'TSI':
        metric_filter = "AND l.metric_name IN ({})".format(
            ', '.join(f"'{m}'" for m in tsi_metrics)
        )
    else:  # WU
        metric_filter = "AND l.metric_name IN ({})".format(
            ', '.join(f"'{m}'" for m in wu_metrics)
        )
    
    query = f"""
    WITH long_counts AS (
        SELECT 
            DATE(l.timestamp) as date,
            COUNT(*) as long_count
        FROM `{dataset}.sensor_readings_long` l
        WHERE DATE(l.timestamp) BETWEEN '{start_date}' AND '{end_date}'
          {metric_filter}
        GROUP BY date
    ),
    hourly_counts AS (
        SELECT 
            DATE(h.hour_ts) as date,
            COUNT(*) as hourly_count
        FROM `{dataset}.sensor_readings_hourly` h
        WHERE DATE(h.hour_ts) BETWEEN '{start_date}' AND '{end_date}'
          AND ({metric_filter.replace('l.metric_name', 'h.metric_name').replace('AND ', '')})
        GROUP BY date
    )
    SELECT 
        COALESCE(l.date, h.date) as date,
        COALESCE(l.long_count, 0) as long_count,
        COALESCE(h.hourly_count, 0) as hourly_count
    FROM long_counts l
    FULL OUTER JOIN hourly_counts h ON l.date = h.date
    ORDER BY date
    """
    
    try:
        df = client.query(query).to_dataframe()
        
        if df.empty:
            issues.append(f"No aggregate data found for {source} in date range")
            return False, issues
        
        # Check for days with data in long but not hourly
        missing_hourly = df[(df['long_count'] > 0) & (df['hourly_count'] == 0)]
        if not missing_hourly.empty:
            for _, row in missing_hourly.iterrows():
                issues.append(
                    f"{source} has {row['long_count']} long-format records on {row['date']} "
                    f"but no hourly aggregates"
                )
                log.warning(f"Missing hourly aggregates for {source} on {row['date']}")
        
        # Hourly count should be roughly long_count / 60 (minutes per hour)
        df['expected_hourly'] = df['long_count'] / 60
        df['hourly_ratio'] = df['hourly_count'] / df['expected_hourly']
        
        # Allow 50-150% range (some variation is expected due to aggregation)
        anomalies = df[(df['hourly_ratio'] < 0.5) | (df['hourly_ratio'] > 1.5)]
        if not anomalies.empty:
            for _, row in anomalies.iterrows():
                issues.append(
                    f"{source} on {row['date']}: unexpected hourly/long ratio {row['hourly_ratio']:.2f} "
                    f"(long: {row['long_count']}, hourly: {row['hourly_count']})"
                )
                log.warning(
                    f"Aggregate anomaly for {source} on {row['date']}: "
                    f"ratio {row['hourly_ratio']:.2f}"
                )
        
        if not issues:
            log.info(f"Aggregate consistency validation passed for {source}")
            return True, []
        
        return False, issues
        
    except Exception as e:
        issues.append(f"Error checking aggregate consistency: {str(e)}")
        log.error(f"Failed to check aggregate consistency: {e}", exc_info=True)
        return False, issues


def main():
    """Main execution function."""
    args = parse_args()
    
    if args.verbose:
        log.setLevel(logging.DEBUG)
        logging.getLogger('src.utils.schema_validation').setLevel(logging.DEBUG)
    
    # Calculate date range
    start_date, end_date = calculate_date_range(args)
    log.info(f"Checking data quality from {start_date} to {end_date}")
    
    # Initialize BigQuery client
    client = bigquery.Client()
    
    # Determine sources to check
    sources = ['TSI', 'WU'] if args.source == 'both' else [args.source]
    
    all_issues = []
    
    # Run checks for each source
    for source in sources:
        log.info(f"\n{'='*60}")
        log.info(f"Checking {source} data quality")
        log.info(f"{'='*60}")
        
        # Check raw table schema
        schema_valid, schema_issues = check_raw_table_schema(
            client, args.dataset, source, start_date, end_date
        )
        all_issues.extend(schema_issues)
        
        # Check TSI raw metrics for NULL values (critical for early detection)
        if source == 'TSI':
            raw_metrics_valid, raw_metrics_issues = check_raw_tsi_metrics(
                client, args.dataset, start_date, end_date
            )
            all_issues.extend(raw_metrics_issues)
        
        # Check coverage
        coverage_valid, coverage_issues = check_coverage(
            client, args.dataset, source, start_date, end_date
        )
        all_issues.extend(coverage_issues)
        
        # Check aggregate consistency
        agg_valid, agg_issues = check_aggregate_consistency(
            client, args.dataset, source, start_date, end_date
        )
        all_issues.extend(agg_issues)
    
    # Summary report
    log.info(f"\n{'='*60}")
    log.info("DATA QUALITY SUMMARY")
    log.info(f"{'='*60}")
    
    if all_issues:
        log.error(f"Found {len(all_issues)} data quality issues:")
        for i, issue in enumerate(all_issues, 1):
            log.error(f"  {i}. {issue}")
        
        if args.fail_on_issues:
            sys.exit(1)
    else:
        log.info("✓ All data quality checks passed!")
        log.info(f"  - Date range: {start_date} to {end_date}")
        log.info(f"  - Sources: {', '.join(sources)}")
        log.info(f"  - Dataset: {args.dataset}")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
