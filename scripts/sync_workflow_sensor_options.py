#!/usr/bin/env python3
"""Sync GitHub workflow sensor dropdown options from production config."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

BEGIN_MARKER = "# SENSOR_OPTIONS_BEGIN"
END_MARKER = "# SENSOR_OPTIONS_END"


def load_sensor_ids(config_path: Path) -> list[str]:
    payload = json.loads(config_path.read_text(encoding="utf-8"))

    wu_entries = payload.get("wu", [])
    tsi_entries = payload.get("tsi", [])

    sensor_ids: list[str] = []
    for entry in wu_entries:
        station_id = str(entry.get("stationId", "")).strip()
        if station_id:
            sensor_ids.append(station_id)

    for entry in tsi_entries:
        sensor_id = str(entry.get("id", "")).strip()
        if sensor_id:
            sensor_ids.append(sensor_id)

    # Stable de-duplication preserves source ordering.
    return list(dict.fromkeys(sensor_ids))


def render_sensor_lines(sensor_ids: Iterable[str], indent: str) -> str:
    return "".join(f"{indent}- {sensor_id}\n" for sensor_id in sensor_ids)


def replace_block(workflow_text: str, replacement_lines: str) -> str:
    pattern = re.compile(
        rf"(?P<indent>[ \t]*){re.escape(BEGIN_MARKER)}\n"
        r"(?P<body>.*?)"
        rf"(?P=indent){re.escape(END_MARKER)}",
        re.DOTALL,
    )

    match = pattern.search(workflow_text)
    if match is None:
        raise ValueError(
            f"Could not find '{BEGIN_MARKER}'/'{END_MARKER}' marker block in workflow file.",
        )

    indent = match.group("indent")
    block = (
        f"{indent}{BEGIN_MARKER}\n"
        f"{replacement_lines}"
        f"{indent}{END_MARKER}"
    )
    return workflow_text[: match.start()] + block + workflow_text[match.end() :]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync workflow sensor dropdown options from config/environments/production.json",
    )
    parser.add_argument(
        "--config",
        default="config/environments/production.json",
        help="Path to production sensor config JSON",
    )
    parser.add_argument(
        "--workflow",
        default=".github/workflows/manage-residence-assignment.yml",
        help="Path to target workflow file",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if workflow options are out of sync",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    workflow_path = Path(args.workflow)

    sensor_ids = load_sensor_ids(config_path)
    workflow_text = workflow_path.read_text(encoding="utf-8")

    marker_indent = " " * 10
    replacement_lines = render_sensor_lines(sensor_ids, marker_indent)
    updated_workflow_text = replace_block(workflow_text, replacement_lines)

    if args.check:
        if updated_workflow_text != workflow_text:
            print(
                "Workflow sensor options out of sync. "
                "Run: python scripts/sync_workflow_sensor_options.py",
                file=sys.stderr,
            )
            raise SystemExit(1)
        print("Workflow sensor options in sync.")
        return

    if updated_workflow_text == workflow_text:
        print("No workflow sensor option changes needed.")
        return

    workflow_path.write_text(updated_workflow_text, encoding="utf-8")
    print(f"Updated workflow sensor options: {workflow_path}")


if __name__ == "__main__":
    main()
