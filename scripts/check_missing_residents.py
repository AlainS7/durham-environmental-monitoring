#!/usr/bin/env python3
"""Check which residents are missing data after Nov 4."""

from google.cloud import bigquery

client = bigquery.Client(project="durham-weather-466502")

query = """
WITH resident_coverage AS (
  SELECT 
    resident,
    DATE(day) as day,
    COUNT(*) as records
  FROM `durham-weather-466502.oura.oura_daily_sleep`
  WHERE day >= '2025-11-04'
  GROUP BY resident, day
)
SELECT 
  resident,
  STRING_AGG(CAST(day AS STRING), ', ' ORDER BY day) as days_with_data,
  COUNT(DISTINCT day) as days_count
FROM resident_coverage
GROUP BY resident
ORDER BY resident
"""

print("Resident data coverage since Nov 4, 2025:")
print("=" * 80)

results = client.query(query).result()
all_residents = set(range(1, 15)) - {12}  # Exclude R12

residents_with_data = set()
for row in results:
    residents_with_data.add(row.resident)
    print(f"Resident {row.resident:2d}: {row.days_count} days - {row.days_with_data}")

missing = sorted(all_residents - residents_with_data)
if missing:
    print(f"\n❌ Missing residents (no data since Nov 4): {missing}")
else:
    print(f"\n✅ All residents have data")

# Now check which residents we expect to have
print("\n" + "=" * 80)
print("Checking PAT files availability:")

from pathlib import Path

pats_dir = Path("oura-rings/pats")
for r in sorted(all_residents):
    pat_file = pats_dir / f"pat_r{r}.env"
    status = "✅" if pat_file.exists() else "❌"
    in_bq = "✅" if r in residents_with_data else "❌"
    print(f"Resident {r:2d}: PAT file {status}  |  Recent BQ data {in_bq}")
