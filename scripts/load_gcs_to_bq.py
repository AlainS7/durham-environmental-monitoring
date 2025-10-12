#!/usr/bin/env python3
"""
Load parquet files from GCS directly to BigQuery, replacing data for specified date range.
This bypasses external table schema issues by loading files directly.
"""

import argparse
from datetime import datetime, timedelta
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days) + 1):
        yield start_date + timedelta(n)

def load_parquet_to_bq(project_id, dataset_id, table_id, gcs_uri, partition_date):
    """Load parquet file from GCS to BigQuery partitioned table."""
    client = bigquery.Client(project=project_id)
    table_ref = f"{project_id}.{dataset_id}.{table_id}"
    
    # Configure the load job
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        autodetect=True,  # Let BigQuery infer schema from Parquet
        time_partitioning=bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="ts",
        ),
        clustering_fields=["native_sensor_id"],  # Match existing table clustering
    )
    
    # Delete existing partition data first
    delete_query = f"""
    DELETE FROM `{table_ref}`
    WHERE DATE(ts) = '{partition_date}'
    """
    
    try:
        print(f"Deleting existing data for {partition_date}...")
        client.query(delete_query).result()
    except NotFound:
        print(f"Table {table_ref} doesn't exist yet, will be created.")
    except Exception as e:
        print(f"Note: Could not delete partition (may not exist): {e}")
    
    # Load the parquet file
    print(f"Loading {gcs_uri} to {table_ref}...")
    load_job = client.load_table_from_uri(
        gcs_uri,
        table_ref,
        job_config=job_config
    )
    
    load_job.result()  # Wait for the job to complete
    
    table = client.get_table(table_ref)
    print(f"✅ Loaded {load_job.output_rows} rows for {partition_date}. Total table rows: {table.num_rows}")
    
    return load_job.output_rows

def main():
    parser = argparse.ArgumentParser(description="Load GCS parquet files to BigQuery")
    parser.add_argument("--project", default="durham-weather-466502", help="GCP project ID")
    parser.add_argument("--dataset", default="sensors", help="BigQuery dataset")
    parser.add_argument("--source", required=True, choices=["WU", "TSI"], help="Data source")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--bucket", default="sensor-data-to-bigquery", help="GCS bucket")
    
    args = parser.parse_args()
    
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_date = datetime.strptime(args.end, "%Y-%m-%d").date()
    
    table_id = f"{args.source.lower()}_raw_materialized"
    total_rows = 0
    success_count = 0
    
    print(f"\n{'='*80}")
    print(f"Loading {args.source} data from GCS to BigQuery")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Target table: {args.project}.{args.dataset}.{table_id}")
    print(f"{'='*80}\n")
    
    for single_date in daterange(start_date, end_date):
        date_str = single_date.strftime("%Y-%m-%d")
        gcs_uri = f"gs://{args.bucket}/raw/source={args.source}/agg=raw/dt={date_str}/{args.source}-{date_str}.parquet"
        
        try:
            rows = load_parquet_to_bq(
                project_id=args.project,
                dataset_id=args.dataset,
                table_id=table_id,
                gcs_uri=gcs_uri,
                partition_date=date_str
            )
            if rows is not None:
                total_rows += rows
            success_count += 1
        except Exception as e:
            print(f"❌ Error loading {date_str}: {e}")
            continue
    
    print(f"\n{'='*80}")
    print(f"Summary: Loaded {success_count}/{(end_date - start_date).days + 1} days")
    print(f"Total rows loaded: {total_rows}")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()
