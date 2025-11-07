#!/usr/bin/env python3
"""
BigQuery Cost Tracker for Oura Pipeline

Tracks and reports BigQuery costs for the Oura data pipeline.
Includes:
- Storage costs (per table)
- Query costs (if INFORMATION_SCHEMA is available)
- Upload/ingestion estimates
- Daily/monthly cost trends

Usage:
    python scripts/track_oura_costs.py --dataset oura
    python scripts/track_oura_costs.py --dataset oura --date 2025-11-01 --summary
"""

from __future__ import annotations
import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from google.cloud import bigquery

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_table_storage_costs(
    client: bigquery.Client, dataset: str, table_prefix: str = "oura"
) -> Dict[str, Any]:
    """Get storage costs for Oura tables."""
    dataset_ref = client.dataset(dataset)
    tables = list(client.list_tables(dataset_ref))

    storage_costs = {}
    total_bytes = 0

    for table_item in tables:
        if not table_item.table_id.startswith(table_prefix):
            continue

        table_ref = dataset_ref.table(table_item.table_id)
        table = client.get_table(table_ref)

        bytes_size = table.num_bytes or 0
        num_rows = table.num_rows or 0
        total_bytes += bytes_size

        # BigQuery storage pricing: $0.02 per GB per month (active), $0.01 per GB per month (long-term)
        # Assuming active storage (data accessed in last 90 days)
        monthly_cost = (bytes_size / 1e9) * 0.02

        storage_costs[table_item.table_id] = {
            "rows": num_rows,
            "size_bytes": bytes_size,
            "size_gb": bytes_size / 1e9,
            "monthly_cost_usd": monthly_cost,
            "created": table.created.isoformat() if table.created else None,
            "modified": table.modified.isoformat() if table.modified else None,
        }

    return {
        "tables": storage_costs,
        "total_bytes": total_bytes,
        "total_gb": total_bytes / 1e9,
        "total_monthly_cost_usd": (total_bytes / 1e9) * 0.02,
    }


def get_query_costs(
    client: bigquery.Client,
    project: str,
    dataset: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> Dict[str, Any]:
    """
    Get query costs from INFORMATION_SCHEMA.JOBS.

    Note: Requires specific permissions to access INFORMATION_SCHEMA.
    """
    if not start_date:
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    query = f"""
    SELECT
        DATE(creation_time) as query_date,
        user_email,
        COUNT(*) as num_queries,
        SUM(total_bytes_processed) as total_bytes_processed,
        SUM(total_bytes_billed) as total_bytes_billed,
        SUM(total_slot_ms) as total_slot_ms
    FROM
        `{project}.region-us.INFORMATION_SCHEMA.JOBS_BY_PROJECT`
    WHERE
        creation_time BETWEEN '{start_date}' AND '{end_date}'
        AND (
            REGEXP_CONTAINS(query, r'oura_')
            OR referenced_tables LIKE '%{dataset}.oura_%'
        )
        AND job_type = 'QUERY'
        AND state = 'DONE'
    GROUP BY
        query_date, user_email
    ORDER BY
        query_date DESC
    """

    try:
        results = client.query(query).result()

        daily_costs = []
        total_bytes_billed = 0

        for row in results:
            bytes_billed = row.total_bytes_billed or 0
            total_bytes_billed += bytes_billed

            # BigQuery pricing: $5 per TB queried
            cost = (bytes_billed / 1e12) * 5.0

            daily_costs.append(
                {
                    "date": row.query_date.isoformat() if row.query_date else None,
                    "user": row.user_email,
                    "num_queries": row.num_queries,
                    "bytes_processed": row.total_bytes_processed,
                    "bytes_billed": bytes_billed,
                    "cost_usd": cost,
                }
            )

        return {
            "daily_costs": daily_costs,
            "total_bytes_billed": total_bytes_billed,
            "total_cost_usd": (total_bytes_billed / 1e12) * 5.0,
            "date_range": {"start": start_date, "end": end_date},
        }

    except Exception as e:
        return {
            "error": str(e),
            "message": "Query cost tracking requires INFORMATION_SCHEMA access permissions",
        }


def estimate_monthly_costs(storage_costs: Dict[str, Any]) -> Dict[str, float]:
    """Estimate monthly costs based on current usage."""
    # Storage cost (already calculated)
    storage_monthly = storage_costs["total_monthly_cost_usd"]

    # Estimate query costs based on typical usage patterns
    # Assume: 1 query per day per table, scanning 10% of data on average
    num_tables = len(storage_costs["tables"])
    avg_scan_fraction = 0.1
    queries_per_day = num_tables * 1  # 1 query/day/table
    queries_per_month = queries_per_day * 30

    bytes_per_query = storage_costs["total_bytes"] * avg_scan_fraction
    monthly_query_bytes = bytes_per_query * queries_per_month
    query_monthly = (monthly_query_bytes / 1e12) * 5.0

    return {
        "storage_monthly_usd": storage_monthly,
        "query_monthly_usd_estimated": query_monthly,
        "total_monthly_usd_estimated": storage_monthly + query_monthly,
    }


def print_cost_summary(
    storage_costs: Dict[str, Any],
    query_costs: Dict[str, Any] | None = None,
    monthly_estimates: Dict[str, float] | None = None,
) -> None:
    """Print formatted cost summary."""
    print("\n" + "=" * 70)
    print("BigQuery Cost Summary - Oura Pipeline")
    print("=" * 70)

    # Storage costs
    print("\n📦 STORAGE COSTS")
    print("-" * 70)
    print(f"Total tables: {len(storage_costs['tables'])}")
    print(f"Total size: {storage_costs['total_gb']:.4f} GB")
    print(f"Monthly storage cost: ${storage_costs['total_monthly_cost_usd']:.6f}")

    print("\nPer-table breakdown:")
    for table_name, info in sorted(storage_costs["tables"].items()):
        print(
            f"  {table_name:40s} {info['rows']:>8,} rows | "
            f"{info['size_gb']:>8.4f} GB | "
            f"${info['monthly_cost_usd']:>8.6f}/mo"
        )

    # Query costs
    if query_costs and "error" not in query_costs:
        print("\n🔍 QUERY COSTS")
        print("-" * 70)
        date_range = query_costs["date_range"]
        print(f"Period: {date_range['start']} to {date_range['end']}")
        print(f"Total bytes billed: {query_costs['total_bytes_billed'] / 1e9:.2f} GB")
        print(f"Total query cost: ${query_costs['total_cost_usd']:.6f}")

        if query_costs["daily_costs"]:
            print("\nDaily breakdown:")
            for day in query_costs["daily_costs"][:10]:  # Show last 10 days
                print(
                    f"  {day['date']} | {day['num_queries']:>3} queries | "
                    f"{day['bytes_billed'] / 1e9:>8.2f} GB | "
                    f"${day['cost_usd']:>8.6f}"
                )

    elif query_costs and "error" in query_costs:
        print("\n🔍 QUERY COSTS")
        print("-" * 70)
        print(f"⚠️  {query_costs['message']}")

    # Monthly estimates
    if monthly_estimates:
        print("\n💰 MONTHLY COST ESTIMATES")
        print("-" * 70)
        print(f"Storage:         ${monthly_estimates['storage_monthly_usd']:.6f}")
        print(
            f"Queries (est.):  ${monthly_estimates['query_monthly_usd_estimated']:.6f}"
        )
        print(
            f"{'Total (est.):':17s}${monthly_estimates['total_monthly_usd_estimated']:.6f}"
        )
        print("\n📝 Note: Query cost is estimated based on typical usage patterns")
        print("   Actual costs may vary based on query frequency and complexity")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Track BigQuery costs for Oura pipeline"
    )
    parser.add_argument(
        "--dataset",
        default="oura",
        help="BigQuery dataset name (default: oura)",
    )
    parser.add_argument(
        "--table-prefix",
        default="oura",
        help="Table name prefix (default: oura)",
    )
    parser.add_argument(
        "--project",
        default=None,
        help="GCP project ID (default: from env or ADC)",
    )
    parser.add_argument(
        "--start-date",
        help="Start date for query cost analysis (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        help="End date for query cost analysis (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Show only summary (skip per-table details)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output in JSON format",
    )

    args = parser.parse_args()

    # Initialize BigQuery client
    project = args.project or os.getenv("BQ_PROJECT")
    client = bigquery.Client(project=project)

    # Get storage costs
    storage_costs = get_table_storage_costs(client, args.dataset, args.table_prefix)

    # Get query costs if permissions allow
    query_costs = None
    if project:
        query_costs = get_query_costs(
            client, project, args.dataset, args.start_date, args.end_date
        )

    # Calculate monthly estimates
    monthly_estimates = estimate_monthly_costs(storage_costs)

    # Output results
    if args.json:
        import json

        output = {
            "storage": storage_costs,
            "queries": query_costs,
            "monthly_estimates": monthly_estimates,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print_cost_summary(storage_costs, query_costs, monthly_estimates)


if __name__ == "__main__":
    main()
