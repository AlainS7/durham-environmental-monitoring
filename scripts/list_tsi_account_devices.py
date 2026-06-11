#!/usr/bin/env python3
"""
List TSI Link devices visible to OAuth client credentials (same account as collectors).

Endpoints (see archive/hot_durham_project/app/backend/server.js):
  POST https://api-prd.tsilink.com/api/v3/external/oauth/client_credential/accesstoken?grant_type=client_credentials
  GET  https://api-prd.tsilink.com/api/v3/external/devices

Credentials (first match wins):
  1) --cred-file PATH          JSON: {"key":"<client_id>","secret":"<client_secret>"}
  2) TSI_CLIENT_ID + TSI_CLIENT_SECRET
  3) DUMMY_TSI_CLIENT_ID + DUMMY_TSI_CLIENT_SECRET
  4) --dotenv                    load .env if python-dotenv installed

Stdlib only (no httpx).
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

AUTH_URL = "https://api-prd.tsilink.com/api/v3/external/oauth/client_credential/accesstoken"
DEVICES_URL = "https://api-prd.tsilink.com/api/v3/external/devices"


def _post_form(url: str, fields: dict[str, str], timeout: float = 60.0) -> dict[str, Any]:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url + "?grant_type=client_credentials",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def _get_json(url: str, headers: dict[str, str], timeout: float = 120.0) -> Any:
    req = urllib.request.Request(url, method="GET", headers=headers)
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def _load_creds(args: argparse.Namespace) -> tuple[str, str]:
    if args.cred_file:
        raw = json.loads(open(args.cred_file, encoding="utf-8").read())
        cid = raw.get("key") or raw.get("client_id") or raw.get("clientId")
        sec = raw.get("secret") or raw.get("client_secret") or raw.get("clientSecret")
        if not cid or not sec:
            sys.exit("cred file must include key/client_id and secret/client_secret")
        return str(cid), str(sec)

    import os

    cid = os.getenv("TSI_CLIENT_ID") or os.getenv("DUMMY_TSI_CLIENT_ID")
    sec = os.getenv("TSI_CLIENT_SECRET") or os.getenv("DUMMY_TSI_CLIENT_SECRET")
    if cid and sec:
        return cid, sec

    sys.exit(
        "No credentials: pass --cred-file <json> or set "
        "TSI_CLIENT_ID + TSI_CLIENT_SECRET (or DUMMY_TSI_*)."
    )


def _flatten_device_row(obj: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k in (
        "device_id",
        "id",
        "deviceId",
        "serial",
        "serial_number",
        "name",
        "friendly_name",
        "friendlyName",
        "model",
        "is_indoor",
        "isIndoor",
    ):
        if k in obj and obj[k] is not None:
            out[k] = obj[k]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cred-file", help='JSON {"key":"...","secret":"..."}')
    ap.add_argument(
        "--dotenv",
        action="store_true",
        help="Load .env from cwd if python-dotenv is installed",
    )
    ap.add_argument(
        "--filter-substr",
        action="append",
        default=[],
        help="Keep devices whose JSON contains substring (repeatable), e.g. AA-16",
    )
    ap.add_argument("--raw", action="store_true", help="Print full JSON response")
    args = ap.parse_args()

    if args.dotenv:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            sys.exit("--dotenv requires: pip install python-dotenv")

    client_id, client_secret = _load_creds(args)

    try:
        auth = _post_form(
            AUTH_URL,
            {"client_id": client_id, "client_secret": client_secret},
        )
    except urllib.error.HTTPError as e:
        sys.exit(f"auth HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:800]}")

    token = auth.get("access_token")
    if not token:
        sys.exit(f"auth response missing access_token: {auth!r}")

    try:
        payload = _get_json(
            DEVICES_URL,
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
        )
    except urllib.error.HTTPError as e:
        sys.exit(f"devices HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:800]}")

    if args.raw:
        print(json.dumps(payload, indent=2))
        return

    if isinstance(payload, list):
        devices = [x for x in payload if isinstance(x, dict)]
    elif isinstance(payload, dict):
        inner = None
        for key in ("devices", "data", "items", "results"):
            if key in payload and isinstance(payload[key], list):
                inner = payload[key]
                break
        if inner is None:
            print(json.dumps(payload, indent=2)[:4000])
            sys.exit(
                "Unexpected /devices shape; use --raw. Top-level keys: "
                + repr(list(payload.keys())[:30])
            )
        devices = [x for x in inner if isinstance(x, dict)]
    else:
        sys.exit(f"Unexpected /devices type: {type(payload)}")

    rows = [_flatten_device_row(d) for d in devices]

    if args.filter_substr:
        lowered = [s.lower() for s in args.filter_substr]

        def keep(row: dict[str, Any]) -> bool:
            blob = json.dumps(row, default=str).lower()
            return all(s in blob for s in lowered)

        rows = [row for row in rows if keep(row)]

    print(f"devices_returned={len(devices)} shown={len(rows)}")
    for row in rows:
        print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    main()
