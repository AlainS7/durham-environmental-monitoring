#!/usr/bin/env python3
"""Generate gitignored residence assignment SQL with real native_sensor_id values.

The template file intentionally keeps dummy native IDs safe for public version
control. This script looks up serial-to-native mapping from BigQuery and
substitutes `dummy_sensor_id` placeholders.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from google.cloud import bigquery

MAPPING_SQL = """
SELECT
  TRIM(serial) AS sensor_name,
  ARRAY_AGG(DISTINCT native_sensor_id ORDER BY native_sensor_id) AS native_sensor_ids
FROM `{project}.{raw_dataset}.tsi_raw_materialized`
WHERE serial IS NOT NULL
  AND TRIM(serial) != ''
  AND native_sensor_id IS NOT NULL
  AND TRIM(native_sensor_id) != ''
GROUP BY sensor_name
"""

ASSIGNMENT_LINE_RE = re.compile(
    r"^\s*\(\s*'[^']+'\s*,\s*'dummy_sensor_id'\s*,\s*'(?P<sensor_name>[^']+)'\s*,"
)


def fetch_sensor_mapping(
    client: bigquery.Client,
    project: str,
    raw_dataset: str,
) -> tuple[dict[str, str], dict[str, list[str]]]:
    """Return serial->native map and ambiguous serials with multiple native ids."""
    dataset = client.get_dataset(f"{project}.{raw_dataset}")
    query = MAPPING_SQL.format(project=project, raw_dataset=raw_dataset)
    job = client.query(query, location=dataset.location)

    mapping: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    for row in job.result():
        sensor_name = str(row["sensor_name"])
        native_sensor_ids = [str(v) for v in row["native_sensor_ids"] if v]
        if len(native_sensor_ids) == 1:
            mapping[sensor_name] = native_sensor_ids[0]
        elif len(native_sensor_ids) > 1:
            ambiguous[sensor_name] = native_sensor_ids
    return mapping, ambiguous


def substitute_template(
    template_sql: str,
    mapping: dict[str, str],
) -> tuple[str, set[str], int]:
    """Replace dummy_sensor_id by sensor_name lookup; return sql, missing names, count."""
    missing: set[str] = set()
    replaced = 0
    output_lines: list[str] = []

    for line in template_sql.splitlines(keepends=True):
        match = ASSIGNMENT_LINE_RE.match(line)
        if not match:
            output_lines.append(line)
            continue

        sensor_name = match.group("sensor_name")
        native_sensor_id = mapping.get(sensor_name)
        if native_sensor_id is None:
            missing.add(sensor_name)
            output_lines.append(line)
            continue

        output_lines.append(line.replace("'dummy_sensor_id'", f"'{native_sensor_id}'", 1))
        replaced += 1

    return "".join(output_lines), missing, replaced


def print_mapping_issues(missing: set[str], ambiguous: dict[str, list[str]]) -> None:
    if ambiguous:
        print(
            "[ERROR] Ambiguous serial mapping (multiple native_sensor_id values):",
            file=sys.stderr,
        )
        for sensor_name in sorted(ambiguous):
            choices = ", ".join(ambiguous[sensor_name])
            print(f"  - {sensor_name}: {choices}", file=sys.stderr)
    if missing:
        print(
            "[ERROR] Missing native_sensor_id mapping for template sensor_name values:",
            file=sys.stderr,
        )
        for sensor_name in sorted(missing):
            print(f"  - {sensor_name}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate residence sensor assignment SQL from BigQuery serial mapping.",
    )
    parser.add_argument("--project", required=True, help="GCP project ID")
    parser.add_argument(
        "--raw-dataset",
        required=True,
        help="Dataset containing tsi_raw_materialized (e.g., sensors)",
    )
    parser.add_argument(
        "--template",
        default="transformations/sql/07_residence_sensor_assignments.template.sql",
        help="Template SQL path containing dummy_sensor_id placeholders",
    )
    parser.add_argument(
        "--output",
        default="transformations/sql/07_residence_sensor_assignments.sql",
        help="Output SQL path (gitignored production file)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write output file; otherwise print SQL to stdout",
    )
    args = parser.parse_args()

    template_path = Path(args.template)
    output_path = Path(args.output)

    template_sql = template_path.read_text(encoding="utf-8")
    client = bigquery.Client(project=args.project)
    mapping, ambiguous = fetch_sensor_mapping(client, args.project, args.raw_dataset)

    rendered_sql, missing, replaced = substitute_template(template_sql, mapping)
    print(f"Resolved {replaced} sensor assignments from BigQuery mapping.", file=sys.stderr)

    if missing or ambiguous:
        print_mapping_issues(missing, ambiguous)
        if args.execute:
            raise SystemExit(
                "Refusing to write output due to missing/ambiguous sensor mappings.",
            )

    if args.execute:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered_sql, encoding="utf-8")
        print(f"Wrote generated SQL to {output_path}", file=sys.stderr)
        return

    print(rendered_sql, end="")


if __name__ == "__main__":
    main()
