#!/usr/bin/env python3
"""Safe secret presence/missing-key summary.

Outputs a single INFO line summarizing which required keys are present in each secret.
No secret values or lengths are logged. Suitable for use in public logs.

Usage (locally):
    PROJECT_ID=your-project TSI_CREDS_SECRET_ID=tsi_creds WU_API_KEY_SECRET_ID=wu_api_key \
  python scripts/secret_summary.py

If running inside Cloud Run with env vars already set, just execute the script.
"""
from __future__ import annotations
import logging
from typing import List
import sys
import pathlib

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
log = logging.getLogger("secret_summary")

try:
    # Ensure repo root (parent of scripts/) is on PYTHONPATH so 'src' package is importable when run directly.
    REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from src.config.app_config import app_config
except Exception as e:  # pragma: no cover
    log.critical(f"Failed to import app_config: {e}")
    raise SystemExit(1)

SPEC = [
    ("db_creds", lambda: app_config.db_creds, ["DB_USER","DB_PASSWORD","DB_HOST","DB_PORT","DB_NAME"]),
    ("tsi_creds", lambda: app_config.tsi_creds, ["key","secret"]),
    ("wu_api_key", lambda: app_config.wu_api_key, ["test_api_key"]),
]

def summarize():
    parts: List[str] = []
    for name, getter, required in SPEC:
        try:
            val = getter()
        except Exception as e:  # pragma: no cover
            parts.append(f"{name}: ERROR({e})")
            continue
        if not val:
            parts.append(f"{name}: MISSING")
            continue
        present = [k for k in required if isinstance(val, dict) and k in val]
        missing = [k for k in required if k not in present]
        parts.append(f"{name}: present={present or 'none'} missing={missing or 'none'}")
    log.info("Secret summary: %s", " | "+" | ".join(parts))

if __name__ == "__main__":
    summarize()
