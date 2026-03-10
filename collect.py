"""Collect TaiPower real-time generation data and append to rolling history.

Runs every 5 minutes via GitHub Actions.
Keeps a rolling 8-day window in data/history.json.
Writes data/dashboard.json for frontend consumption.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

HISTORY_PATH = Path("data/history.json")
DASHBOARD_PATH = Path("data/dashboard.json")
MAX_AGE_HOURS = 8 * 24  # 8 days

TAIPOWER_URL = "https://www.taipower.com.tw/d006/loadGraph/loadGraph/data/genary.json"

# Map HTML anchor names to column prefixes and renewable flag
_TYPE_MAP: dict[str, tuple[str, bool]] = {
    "solar": ("solar", True),
    "wind": ("wind", True),
    "hydro": ("hydro", True),
    "lng": ("lng", False),
    "ipplng": ("ipp_lng", False),
    "coal": ("coal", False),
    "ippcoal": ("ipp_coal", False),
    "cogen": ("cogen", False),
    "fueloil": ("oil", False),
    "EnergyStorageSystem": ("storage", False),
    "OtherRenewableEnergy": ("other_renewable", True),
}

_ANCHOR_RE = re.compile(r"<A NAME='(\w+)'></A>")


def _parse_subtotal_mw(value: str) -> float | None:
    """Parse MW from subtotal format like '15918.1(27.068%)'."""
    if not value or not isinstance(value, str):
        return None
    paren = value.find("(")
    num_str = value[:paren].strip() if paren > 0 else value.strip()
    try:
        return float(num_str)
    except (ValueError, TypeError):
        return None


def fetch_taipower() -> dict:
    """Fetch and parse TaiPower generation data into a flat record."""
    resp = requests.get(
        TAIPOWER_URL,
        timeout=30,
        headers={"User-Agent": "taipower-data-collector/1.0"},
    )
    resp.raise_for_status()
    raw = resp.json()

    aa_data = raw.get("aaData", [])
    if not aa_data:
        raise ValueError("No aaData in TaiPower response")

    # Parse timestamp
    ts_str = raw.get("", "")
    try:
        ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        ts = datetime.now(timezone.utc)

    # Find subtotal rows
    type_data: dict[str, dict[str, float | None]] = {}
    for row in aa_data:
        if not isinstance(row, list) or len(row) < 6:
            continue
        unit_name = row[2].strip() if isinstance(row[2], str) else ""
        if not unit_name.startswith("小計"):
            continue
        energy_type_html = row[0] if isinstance(row[0], str) else ""
        match = _ANCHOR_RE.search(energy_type_html)
        if not match:
            continue
        anchor = match.group(1)
        type_data[anchor] = {
            "capacity_mw": _parse_subtotal_mw(str(row[3])),
            "output_mw": _parse_subtotal_mw(str(row[4])),
        }

    # Build record
    renewable_mw = 0.0
    total_mw = 0.0
    record: dict[str, Any] = {"timestamp": ts.isoformat()}

    for anchor, (col_prefix, is_renewable) in _TYPE_MAP.items():
        data = type_data.get(anchor, {})
        mw = data.get("output_mw") or 0.0
        if data.get("output_mw") is not None:
            record[f"{col_prefix}_mw"] = data["output_mw"]
        if data.get("capacity_mw") is not None:
            record[f"{col_prefix}_capacity_mw"] = data["capacity_mw"]
        total_mw += mw
        if is_renewable:
            renewable_mw += mw

    record["renewable_mw"] = round(renewable_mw, 1)
    record["total_mw"] = round(total_mw, 1)
    record["renewable_pct"] = round(renewable_mw / total_mw * 100, 2) if total_mw > 0 else 0.0

    return record


def load_history() -> list[dict]:
    if HISTORY_PATH.exists():
        try:
            return json.loads(HISTORY_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []


def prune_old(records: list[dict]) -> list[dict]:
    now = datetime.now(timezone.utc)
    result = []
    for r in records:
        try:
            ts = datetime.fromisoformat(r["timestamp"])
            if (now - ts).total_seconds() / 3600 <= MAX_AGE_HOURS:
                result.append(r)
        except (KeyError, ValueError):
            continue
    return result


def build_dashboard(records: list[dict]) -> dict:
    """Build dashboard JSON from history."""
    if not records:
        return {"updated_at": datetime.now(timezone.utc).isoformat() + "Z", "records": []}

    sorted_recs = sorted(records, key=lambda r: r.get("timestamp", ""))

    # Time series
    ts_fields = ["renewable_pct", "solar_mw", "wind_mw", "hydro_mw", "total_mw", "renewable_mw"]
    time_series: dict[str, Any] = {
        "timestamps": [r["timestamp"] for r in sorted_recs],
    }
    for field in ts_fields:
        time_series[field] = [r.get(field) for r in sorted_recs]

    # Daily peaks
    daily: dict[str, dict] = {}
    for r in sorted_recs:
        date = r.get("timestamp", "")[:10]
        if not date:
            continue
        if date not in daily:
            daily[date] = {
                "solar_mw_max": 0, "wind_mw_max": 0, "hydro_mw_max": 0,
                "renewable_mw_max": 0, "total_mw_max": 0, "renewable_pct_max": 0,
                "count": 0,
            }
        d = daily[date]
        for key in ["solar_mw", "wind_mw", "hydro_mw", "renewable_mw", "total_mw", "renewable_pct"]:
            d[f"{key}_max"] = max(d[f"{key}_max"], r.get(key) or 0)
        d["count"] += 1

    return {
        "updated_at": datetime.now(timezone.utc).isoformat() + "Z",
        "latest": sorted_recs[-1],
        "record_count": len(sorted_recs),
        "time_series": time_series,
        "daily_peaks": [{"date": d, **v} for d, v in sorted(daily.items())],
    }


def main():
    print("Collecting TaiPower data...")
    try:
        record = fetch_taipower()
    except Exception as e:
        print(f"Error fetching TaiPower data: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  renewable: {record.get('renewable_pct')}% | "
          f"solar: {record.get('solar_mw')} MW | "
          f"wind: {record.get('wind_mw')} MW | "
          f"total: {record.get('total_mw')} MW")

    history = load_history()
    history.append(record)
    history = prune_old(history)

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False))
    print(f"  history: {len(history)} records")

    dashboard = build_dashboard(history)
    DASHBOARD_PATH.write_text(json.dumps(dashboard, indent=2, ensure_ascii=False))
    print(f"  dashboard: {len(dashboard.get('daily_peaks', []))} daily entries")


if __name__ == "__main__":
    main()
