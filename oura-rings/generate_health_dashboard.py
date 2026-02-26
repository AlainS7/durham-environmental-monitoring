#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate a self-contained HTML health dashboard from Oura Ring data.

Produces: dashboard/resident_health_dashboard.html

Charts included
---------------
1. HRV over time — all residents (with cross-person variability band)
2. HRV within-person variability (rolling std per resident)
3. Sleep score over time — all residents
4. Readiness score over time — all residents
5. Resting HR + Max HR during sleep — all residents
6. HR and HRV variability box plots per resident (spread comparison)
7. Sleep duration over time — all residents
8. Optional: Environmental correlation — HRV vs indoor temperature
   (requires BigQuery access, skipped gracefully if unavailable)

Usage
-----
    cd oura-rings/
    python generate_health_dashboard.py [--days 90] [--residents 1,2,3] [--output ../dashboard/resident_health_dashboard.html]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
PATS_DIR = SCRIPT_DIR / "pats"
DEFAULT_OUTPUT = SCRIPT_DIR.parent / "dashboard" / "resident_health_dashboard.html"

# All resident numbers that have PAT files
ALL_RESIDENTS = sorted(
    int(p.stem.replace("pat_r", ""))
    for p in PATS_DIR.glob("pat_r*.env")
    if p.stem != "pat_r.env.example"
)

# ──────────────────────────────────────────────
# Import project helpers (must run from oura-rings/)
# ──────────────────────────────────────────────
sys.path.insert(0, str(SCRIPT_DIR))
from oura_client import OuraClient  # noqa: E402
from oura_collector import get_resident_token  # noqa: E402


# ──────────────────────────────────────────────
# Data fetching
# ──────────────────────────────────────────────


def fetch_resident_data(
    resident_no: int, start_date: str, end_date: str
) -> dict[str, Any]:
    """Fetch all health metrics for one resident. Returns empty dict on error."""
    token = get_resident_token(resident_no, str(PATS_DIR))
    if not token:
        log.warning(f"  R{resident_no}: no token — skipping")
        return {}

    params = {"start_date": start_date, "end_date": end_date}
    data: dict[str, Any] = {}
    try:
        with OuraClient(token) as client:
            log.info(f"  R{resident_no}: daily sleep")
            data["daily_sleep"] = client.get_daily_sleep(**params)
            log.info(f"  R{resident_no}: sleep periods")
            data["sleep_periods"] = client.get_sleep_periods(**params)
            log.info(f"  R{resident_no}: readiness")
            data["readiness"] = client.get_daily_readiness(**params)
            log.info(f"  R{resident_no}: activity")
            data["activity"] = client.get_daily_activity(**params)
            log.info(f"  R{resident_no}: heart rate")
            data["heart_rate"] = client.get_heart_rate(**params)
    except Exception as exc:
        log.error(f"  R{resident_no}: API error — {exc}")
    return data


# ──────────────────────────────────────────────
# Data transformation
# ──────────────────────────────────────────────


def build_daily_df(raw: dict[str, Any], resident_no: int) -> pd.DataFrame:
    """Flatten all daily metrics for one resident into a single DataFrame."""
    rows: dict[str, dict] = {}  # keyed by date string

    # --- daily sleep scores + avg HRV from daily_sleep
    for entry in raw.get("daily_sleep", []):
        d = entry["day"]
        rows.setdefault(d, {})["day"] = d
        rows[d]["sleep_score"] = entry.get("score")
        rows[d]["hrv_average_daily"] = entry.get("contributors", {}).get("hrv_balance")

    # --- readiness
    for entry in raw.get("readiness", []):
        d = entry["day"]
        rows.setdefault(d, {})["day"] = d
        rows[d]["readiness_score"] = entry.get("score")

    # --- activity
    for entry in raw.get("activity", []):
        d = entry["day"]
        rows.setdefault(d, {})["day"] = d
        rows[d]["activity_score"] = entry.get("score")
        rows[d]["active_calories"] = entry.get("active_calories")
        rows[d]["steps"] = entry.get("steps")

    # --- sleep periods: resting HR, max HR, total sleep, avg HRV from sensor
    for entry in raw.get("sleep_periods", []):
        d = entry.get("day") or (entry.get("bedtime_start") or "")[:10]
        if not d:
            continue
        rows.setdefault(d, {})["day"] = d
        avg_hrv = entry.get("average_hrv")
        low_hr = entry.get("lowest_heart_rate")
        avg_hr = entry.get("average_heart_rate")
        duration_sec = entry.get("total_sleep_duration") or entry.get("time_in_bed")

        # Keep the best-quality values (prefer long sleep periods)
        prev_dur = rows[d].get("_max_duration", 0)
        curr_dur = duration_sec or 0
        if curr_dur >= prev_dur:
            rows[d]["_max_duration"] = curr_dur
            if avg_hrv is not None:
                rows[d]["hrv_sleep"] = round(avg_hrv, 1)
            if low_hr is not None:
                rows[d]["resting_hr"] = low_hr
            if avg_hr is not None:
                rows[d]["avg_hr_sleep"] = round(avg_hr, 1)
            if duration_sec is not None:
                rows[d]["total_sleep_min"] = round(duration_sec / 60, 1)

        # Derive max HR from 5-min HR array if present
        hr_5min: list[int] | None = (
            entry.get("heart_rate", {}).get("items")
            if isinstance(entry.get("heart_rate"), dict)
            else None
        )
        if hr_5min:
            valid = [v for v in hr_5min if v and v > 0]
            if valid:
                rows[d]["max_hr_sleep"] = max(valid)

    # --- heart_rate timeseries: daily max HR
    hr_daily: dict[str, int] = {}
    for entry in raw.get("heart_rate", []):
        ts = entry.get("timestamp", "")[:10]
        bpm = entry.get("bpm")
        if ts and bpm:
            hr_daily[ts] = max(hr_daily.get(ts, 0), bpm)

    for d, max_bpm in hr_daily.items():
        rows.setdefault(d, {})["day"] = d
        rows[d]["max_hr_day"] = max_bpm

    # Assemble DataFrame
    df = pd.DataFrame(list(rows.values()))
    if df.empty:
        return df
    df = df.drop(columns=["_max_duration"], errors="ignore")
    df["day"] = pd.to_datetime(df["day"])
    df["resident"] = f"R{resident_no}"
    df = df.sort_values("day").reset_index(drop=True)
    return df


# ──────────────────────────────────────────────
# Optional: BigQuery env data for correlation
# ──────────────────────────────────────────────


def fetch_env_data(start_date: str, end_date: str) -> pd.DataFrame:
    """Pull daily indoor temperature per residence from BigQuery."""
    try:
        from google.cloud import bigquery  # type: ignore

        client = bigquery.Client(project="durham-weather-466502")
        query = f"""
        SELECT
          DATE(day_ts)  AS day,
          residence_id,
          ROUND(AVG(avg_value), 1) AS indoor_temp_f
        FROM `durham-weather-466502.sensors_shared.residence_readings_daily`
        WHERE sensor_role = 'Indoor'
          AND metric_name = 'temperature'
          AND day_ts BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
        df = client.query(query).to_dataframe()
        df["day"] = pd.to_datetime(df["day"])
        # Map residence_id (R1..R13) to resident label
        df["resident"] = df["residence_id"]
        log.info(f"BigQuery: {len(df)} rows of env data")
        return df
    except Exception as exc:
        log.warning(
            f"BigQuery env data unavailable ({exc}) — skipping correlation panel"
        )
        return pd.DataFrame()


# ──────────────────────────────────────────────
# HTML generation with Plotly
# ──────────────────────────────────────────────

PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"

THERMAL_COLORS = {
    "Cold": "#3274D9",
    "Cool": "#73BF69",
    "Comfortable": "#56A64B",
    "Warm": "#F2CC0C",
    "Hot": "#E02F44",
}

RESIDENT_PALETTE = [
    "#1f77b4",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#aec7e8",
    "#ffbb78",
    "#98df8a",
]


def _temp_to_state(t_f: float) -> str:
    if t_f < 62:
        return "Cold"
    if t_f < 66:
        return "Cool"
    if t_f < 72:
        return "Comfortable"
    if t_f < 78:
        return "Warm"
    return "Hot"


def make_traces_per_resident(
    combined: pd.DataFrame,
    y_col: str,
    residents: list[str],
    mode: str = "lines+markers",
    show_legend: bool = True,
) -> list[dict]:
    traces = []
    for i, res in enumerate(residents):
        sub = combined[combined["resident"] == res].dropna(subset=[y_col])
        if sub.empty:
            continue
        traces.append(
            {
                "type": "scatter",
                "x": sub["day"].dt.strftime("%Y-%m-%d").tolist(),
                "y": sub[y_col].tolist(),
                "name": res,
                "mode": mode,
                "marker": {
                    "size": 5,
                    "color": RESIDENT_PALETTE[i % len(RESIDENT_PALETTE)],
                },
                "line": {
                    "color": RESIDENT_PALETTE[i % len(RESIDENT_PALETTE)],
                    "width": 1.5,
                },
                "legendgroup": res,
                "showlegend": show_legend,
            }
        )
    return traces


def make_band_traces(
    combined: pd.DataFrame,
    y_col: str,
    band_color: str = "rgba(100,100,200,0.15)",
) -> list[dict]:
    """Cross-resident min/max/avg band."""
    grp = combined.dropna(subset=[y_col]).groupby("day")[y_col]
    days = grp.mean().index.strftime("%Y-%m-%d").tolist()
    mn = grp.min().tolist()
    mx = grp.max().tolist()
    avg = grp.mean().round(1).tolist()
    return [
        {
            "type": "scatter",
            "x": days + days[::-1],
            "y": mx + mn[::-1],
            "fill": "toself",
            "fillcolor": band_color,
            "line": {"color": "transparent"},
            "name": "All-resident range",
            "showlegend": True,
            "hoverinfo": "skip",
        },
        {
            "type": "scatter",
            "x": days,
            "y": avg,
            "mode": "lines",
            "line": {"color": "rgba(60,60,180,0.8)", "width": 2, "dash": "dot"},
            "name": "Cross-resident avg",
        },
    ]


def make_rolling_std_traces(
    combined: pd.DataFrame,
    y_col: str,
    window: int = 14,
    residents: list[str] | None = None,
) -> list[dict]:
    """Rolling std (within-person variability)."""
    residents = residents or combined["resident"].unique().tolist()
    traces = []
    for i, res in enumerate(residents):
        sub = combined[combined["resident"] == res].dropna(subset=[y_col]).copy()
        if len(sub) < window:
            continue
        sub = sub.set_index("day").sort_index()
        sub["roll_std"] = sub[y_col].rolling(window, min_periods=5).std()
        sub = sub.reset_index()
        traces.append(
            {
                "type": "scatter",
                "x": sub["day"].dt.strftime("%Y-%m-%d").tolist(),
                "y": sub["roll_std"].round(2).tolist(),
                "name": res,
                "mode": "lines",
                "line": {
                    "color": RESIDENT_PALETTE[i % len(RESIDENT_PALETTE)],
                    "width": 1.5,
                },
            }
        )
    return traces


def make_box_traces(
    combined: pd.DataFrame,
    y_col: str,
    residents: list[str],
) -> list[dict]:
    traces = []
    for i, res in enumerate(residents):
        vals = combined[combined["resident"] == res][y_col].dropna().tolist()
        if not vals:
            continue
        traces.append(
            {
                "type": "box",
                "y": vals,
                "name": res,
                "marker": {"color": RESIDENT_PALETTE[i % len(RESIDENT_PALETTE)]},
                "boxpoints": "outliers",
            }
        )
    return traces


def make_scatter_corr_traces(
    health: pd.DataFrame,
    env: pd.DataFrame,
    y_col: str,
    residents: list[str],
) -> list[dict]:
    """Scatter of env indoor temp vs health metric, coloured by thermal state."""
    traces: list[dict] = []
    # Align on resident + day
    health_slim = health[["resident", "day", y_col]].dropna()
    # Try to match R1..R13 from env to resident labels
    merged = health_slim.merge(
        env[["resident", "day", "indoor_temp_f"]],
        on=["resident", "day"],
        how="inner",
    )
    if merged.empty:
        return []

    merged["thermal_state"] = merged["indoor_temp_f"].apply(_temp_to_state)
    for state, color in THERMAL_COLORS.items():
        sub = merged[merged["thermal_state"] == state]
        if sub.empty:
            continue
        traces.append(
            {
                "type": "scatter",
                "mode": "markers",
                "x": sub["indoor_temp_f"].round(1).tolist(),
                "y": sub[y_col].round(1).tolist(),
                "name": state,
                "marker": {"color": color, "size": 7, "opacity": 0.8},
                "text": sub["resident"].tolist(),
                "hovertemplate": "%{text}<br>Temp: %{x}°F<br>"
                + y_col
                + ": %{y}<extra></extra>",
            }
        )
    return traces


def build_html(
    combined: pd.DataFrame,
    env: pd.DataFrame,
    output_path: Path,
    days: int,
) -> None:
    """Build the full HTML dashboard and write to file."""
    residents = (
        sorted(combined["resident"].unique().tolist()) if not combined.empty else []
    )

    def layout(title: str, xlab: str = "Date", ylab: str = "") -> dict:
        return {
            "title": {"text": title, "font": {"size": 16}},
            "xaxis": {"title": xlab, "showgrid": True, "gridcolor": "#eee"},
            "yaxis": {"title": ylab, "showgrid": True, "gridcolor": "#eee"},
            "legend": {"orientation": "h", "y": -0.25},
            "plot_bgcolor": "#fafafa",
            "paper_bgcolor": "#fff",
            "hovermode": "x unified",
            "margin": {"t": 50, "b": 60, "l": 60, "r": 20},
        }

    def chart_block(fig_data: dict, div_id: str, height: int = 420) -> str:
        return (
            f'<div id="{div_id}" style="width:100%;height:{height}px;"></div>\n'
            f'<script>Plotly.newPlot("{div_id}",'
            f"{json.dumps(fig_data['data'])},"
            f"{json.dumps(fig_data['layout'])},"
            f"{{responsive:true,displayModeBar:false}});</script>\n"
        )

    def section(title: str, inner: str) -> str:
        if not inner.strip():
            return ""
        return f'<h2 class="section-title">{title}</h2>\n<div class="chart-card">{inner}</div>\n'

    # ── build individual chart blocks ──────────────────────────────────────
    c: dict[str, str] = {}  # chart_id → HTML block

    if not combined.empty:
        # 1. HRV over time + band
        hrv_traces = make_band_traces(
            combined, "hrv_sleep", "rgba(60,100,200,0.12)"
        ) + make_traces_per_resident(combined, "hrv_sleep", residents)
        if hrv_traces:
            c["hrv"] = chart_block(
                {
                    "data": hrv_traces,
                    "layout": layout(
                        "HRV During Sleep — All Residents", ylab="HRV (ms)"
                    ),
                },
                "chart_hrv",
            )

        # 2. HRV within-person rolling variability
        hrv_var = make_rolling_std_traces(combined, "hrv_sleep", 14, residents)
        if hrv_var:
            c["hrv_var"] = chart_block(
                {
                    "data": hrv_var,
                    "layout": layout(
                        "Within-Person HRV Variability (14-day Rolling Std)",
                        ylab="Std Dev (ms)",
                    ),
                },
                "chart_hrv_var",
            )

        # 3. HRV box plots
        hrv_box = make_box_traces(combined, "hrv_sleep", residents)
        if hrv_box:
            c["hrv_box"] = chart_block(
                {
                    "data": hrv_box,
                    "layout": {
                        **layout(
                            "HRV Distribution per Resident",
                            xlab="Resident",
                            ylab="HRV (ms)",
                        ),
                        "hovermode": "closest",
                    },
                },
                "chart_hrv_box",
                350,
            )

        # 4. Resting HR
        hr_rest = make_traces_per_resident(combined, "resting_hr", residents)
        if hr_rest:
            c["resting_hr"] = chart_block(
                {
                    "data": hr_rest,
                    "layout": layout(
                        "Resting Heart Rate (Lowest HR During Sleep)", ylab="BPM"
                    ),
                },
                "chart_resting_hr",
            )

        # 5. Max HR
        max_hr_col = (
            "max_hr_day" if "max_hr_day" in combined.columns else "max_hr_sleep"
        )
        max_hr = make_traces_per_resident(combined, max_hr_col, residents)
        if max_hr:
            c["max_hr"] = chart_block(
                {
                    "data": max_hr,
                    "layout": layout("Max Heart Rate Per Day", ylab="BPM"),
                },
                "chart_max_hr",
            )

        # 6. HR box plots
        hr_box = make_box_traces(combined, max_hr_col, residents)
        if hr_box:
            c["hr_box"] = chart_block(
                {
                    "data": hr_box,
                    "layout": {
                        **layout(
                            "Max HR Distribution per Resident",
                            xlab="Resident",
                            ylab="BPM",
                        ),
                        "hovermode": "closest",
                    },
                },
                "chart_hr_box",
                350,
            )

        # 7. Sleep score
        sleep_sc = make_band_traces(
            combined, "sleep_score", "rgba(100,180,100,0.12)"
        ) + make_traces_per_resident(combined, "sleep_score", residents)
        if sleep_sc:
            c["sleep_score"] = chart_block(
                {
                    "data": sleep_sc,
                    "layout": layout(
                        "Sleep Score — All Residents", ylab="Score (0-100)"
                    ),
                },
                "chart_sleep_score",
            )

        # 8. Readiness score
        read_sc = make_band_traces(
            combined, "readiness_score", "rgba(200,150,100,0.12)"
        ) + make_traces_per_resident(combined, "readiness_score", residents)
        if read_sc:
            c["readiness"] = chart_block(
                {
                    "data": read_sc,
                    "layout": layout(
                        "Readiness Score — All Residents", ylab="Score (0-100)"
                    ),
                },
                "chart_readiness",
            )

        # 9. Sleep duration
        sleep_dur = make_traces_per_resident(combined, "total_sleep_min", residents)
        if sleep_dur:
            c["sleep_dur"] = chart_block(
                {
                    "data": sleep_dur,
                    "layout": layout("Total Sleep Duration", ylab="Minutes"),
                },
                "chart_sleep_dur",
            )

        # 10 & 11. Environmental correlation
        if not env.empty:
            corr_hrv = make_scatter_corr_traces(combined, env, "hrv_sleep", residents)
            if corr_hrv:
                c["hrv_temp"] = chart_block(
                    {
                        "data": corr_hrv,
                        "layout": {
                            **layout(
                                "HRV vs Indoor Temperature (by Thermal State)",
                                "Indoor Temp (°F)",
                                "HRV (ms)",
                            ),
                            "hovermode": "closest",
                        },
                    },
                    "chart_hrv_temp",
                )
            corr_sleep = make_scatter_corr_traces(
                combined, env, "sleep_score", residents
            )
            if corr_sleep:
                c["sleep_temp"] = chart_block(
                    {
                        "data": corr_sleep,
                        "layout": {
                            **layout(
                                "Sleep Score vs Indoor Temperature (by Thermal State)",
                                "Indoor Temp (°F)",
                                "Sleep Score",
                            ),
                            "hovermode": "closest",
                        },
                    },
                    "chart_sleep_temp",
                )

    # ── assemble page ──────────────────────────────────────────────────────
    n_residents = len(residents)
    gen_ts = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    has_env = bool(c.get("hrv_temp") or c.get("sleep_temp"))

    body_parts = [
        # meta cards
        f"""<div class="meta-row">
  <div class="meta-card"><div class="label">Residents</div><div class="value">{n_residents}</div></div>
  <div class="meta-card"><div class="label">Period</div><div class="value">Last {days} days</div></div>
  <div class="meta-card"><div class="label">Env Correlation</div><div class="value">{"Yes" if has_env else "N/A"}</div></div>
</div>""",
        section("HRV (Heart Rate Variability)", c.get("hrv", "")),
        section(
            "Within-Person HRV Variability (14-day Rolling Std)", c.get("hrv_var", "")
        ),
        section("HRV Distribution per Resident", c.get("hrv_box", "")),
        section("Resting Heart Rate", c.get("resting_hr", "")),
        section("Max Heart Rate per Day", c.get("max_hr", "")),
        section("Max HR Distribution per Resident", c.get("hr_box", "")),
        section("Sleep Score", c.get("sleep_score", "")),
        section("Readiness Score", c.get("readiness", "")),
        section("Sleep Duration", c.get("sleep_dur", "")),
        section("HRV vs Indoor Temperature", c.get("hrv_temp", "")) if has_env else "",
        section("Sleep Score vs Indoor Temperature", c.get("sleep_temp", ""))
        if has_env
        else "",
    ]

    if not c:
        body_parts.append(
            "<p style='color:red;padding:24px;'>No Oura data could be fetched. "
            "Check PAT tokens and network access.</p>"
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Durham — Resident Health Dashboard</title>
  <script src="{PLOTLY_CDN}"></script>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #f5f6fa; color: #222; margin: 0; padding: 0;
    }}
    header {{
      background: #1a1a2e; color: #fff; padding: 20px 32px;
      display: flex; align-items: center; justify-content: space-between;
    }}
    header h1 {{ margin: 0; font-size: 1.4rem; font-weight: 600; }}
    header p  {{ margin: 0; font-size: 0.85rem; opacity: 0.75; }}
    .badge {{
      background: #e94560; color: #fff; border-radius: 20px;
      padding: 4px 12px; font-size: 0.8rem; white-space: nowrap;
    }}
    .container {{ max-width: 1400px; margin: 0 auto; padding: 24px 32px; }}
    .section-title {{
      font-size: 1.05rem; font-weight: 700; color: #1a1a2e;
      border-left: 4px solid #e94560; padding-left: 10px;
      margin: 32px 0 12px;
    }}
    .chart-card {{
      background: #fff; border-radius: 10px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.08);
      padding: 16px; margin-bottom: 24px;
    }}
    .meta-row {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 24px; }}
    .meta-card {{
      background: #fff; border-radius: 8px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.07);
      padding: 14px 20px; min-width: 140px;
    }}
    .meta-card .label {{ font-size: 0.75rem; color: #888; text-transform: uppercase; }}
    .meta-card .value {{ font-size: 1.5rem; font-weight: 700; color: #1a1a2e; }}
    footer {{ text-align: center; padding: 24px; font-size: 0.78rem; color: #aaa; }}
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Durham — Resident Health Dashboard</h1>
      <p>Oura Ring · Sleep · HRV · Heart Rate · Readiness · Activity</p>
    </div>
    <span class="badge">Generated {gen_ts}</span>
  </header>

  <div class="container">
    {"".join(p for p in body_parts if p)}
  </div>

  <footer>
    Durham Environmental Monitoring Project ·
    Data: Oura Ring API v2 + BigQuery sensors_shared ·
    Generated {gen_ts}
  </footer>
</body>
</html>
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    log.info(f"Dashboard written → {output_path}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate resident health dashboard HTML."
    )
    parser.add_argument(
        "--days", type=int, default=90, help="Days of history to fetch (default 90)"
    )
    parser.add_argument(
        "--residents",
        type=str,
        default=None,
        help="Comma-separated resident numbers, e.g. 1,3,5 (default: all)",
    )
    parser.add_argument(
        "--output", type=str, default=str(DEFAULT_OUTPUT), help="Output HTML path"
    )
    parser.add_argument(
        "--no-bq", action="store_true", help="Skip BigQuery env data fetch"
    )
    args = parser.parse_args()

    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=args.days)).isoformat()
    output = Path(args.output)

    if args.residents:
        target = [int(x.strip()) for x in args.residents.split(",")]
    else:
        target = ALL_RESIDENTS

    log.info(f"Fetching data for {len(target)} resident(s): {target}")
    log.info(f"Date range: {start_date} → {end_date}")

    all_frames: list[pd.DataFrame] = []
    for res_no in target:
        log.info(f"Resident {res_no}")
        raw = fetch_resident_data(res_no, start_date, end_date)
        if raw:
            df = build_daily_df(raw, res_no)
            if not df.empty:
                all_frames.append(df)
                log.info(f"  → {len(df)} days of data")
            else:
                log.warning("  → empty after transform")

    combined = (
        pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()
    )
    log.info(
        f"Combined: {len(combined)} rows, {combined['resident'].nunique() if not combined.empty else 0} residents"
    )

    env = pd.DataFrame()
    if not args.no_bq:
        log.info("Fetching environmental data from BigQuery…")
        env = fetch_env_data(start_date, end_date)

    build_html(combined, env, output, args.days)
    print(f"\n✅  Dashboard ready: {output}")
    print(f"   Open in browser: open {output}")


if __name__ == "__main__":
    main()
