"""Collect Taiwan real-time AQI and reservoir data.

Runs every 30 minutes via acmacmini2 cron.
Writes data/tw_aqi.json and data/tw_reservoir.json for frontend consumption.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import os

import requests

TW_TZ = timezone(timedelta(hours=8))
DATA_DIR = Path("data")

# --- AQI ---

AQI_URL = "https://data.moenv.gov.tw/api/v2/aqx_p_432"
# Public open data API key (Taiwan MOENV), read from env or use default
AQI_API_KEY = os.environ.get("MOENV_API_KEY", "e8dd42e6-9b8b-43f8-991e-b3dee723a52d")

AQI_STATUS_COLOR: dict[str, str] = {
    "良好": "#00e400",
    "普通": "#ffff00",
    "對敏感族群不健康": "#ff7e00",
    "對所有族群不健康": "#ff0000",
    "非常不健康": "#8f3f97",
    "危害": "#7e0023",
}


def _safe_float(v: Any) -> float | None:
    if v is None or v == "" or v == "--" or v == "-":
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def fetch_aqi() -> dict:
    """Fetch Taiwan EPA real-time AQI data."""
    resp = requests.get(
        AQI_URL,
        params={
            "api_key": AQI_API_KEY,
            "limit": 1000,
            "sort": "ImportDate desc",
            "format": "json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()
    records = raw.get("records", [])

    stations: list[dict] = []
    for r in records:
        aqi = _safe_float(r.get("aqi"))
        if aqi is None:
            continue
        stations.append({
            "station": r.get("sitename", ""),
            "county": r.get("county", ""),
            "aqi": aqi,
            "pm25": _safe_float(r.get("pm2.5")),
            "pm10": _safe_float(r.get("pm10")),
            "o3": _safe_float(r.get("o3")),
            "status": r.get("status", ""),
            "color": AQI_STATUS_COLOR.get(r.get("status", ""), "#999"),
            "publish_time": r.get("publishtime", ""),
        })

    stations.sort(key=lambda s: s["aqi"], reverse=True)

    # Compute summary
    aqi_values = [s["aqi"] for s in stations]
    pm25_values = [s["pm25"] for s in stations if s["pm25"] is not None]

    now = datetime.now(TW_TZ)
    return {
        "updated_at": now.isoformat(),
        "station_count": len(stations),
        "avg_aqi": round(sum(aqi_values) / len(aqi_values), 1) if aqi_values else None,
        "max_aqi": max(aqi_values) if aqi_values else None,
        "avg_pm25": round(sum(pm25_values) / len(pm25_values), 1) if pm25_values else None,
        "worst_station": stations[0] if stations else None,
        "stations": stations,
    }


# --- Reservoir ---

RESERVOIR_URL = "https://data.wra.gov.tw/Service/OpenData.aspx"
RESERVOIR_ID = "50C8256D-30C5-4B8D-9B84-2E14D5C6DF71"


def fetch_reservoir() -> dict:
    """Fetch Taiwan WRA reservoir water levels."""
    resp = requests.get(
        RESERVOIR_URL,
        params={"format": "json", "id": RESERVOIR_ID},
        timeout=30,
    )
    resp.raise_for_status()
    raw = resp.json()

    # Handle various response formats
    if isinstance(raw, list):
        records = raw
    elif isinstance(raw, dict):
        records = raw.get("DailyOperationalStatisticsOfReservoirs_OPENDATA", [])
        if not records:
            records = raw.get("records", raw.get("data", []))
    else:
        records = []

    reservoirs: list[dict] = []
    for r in records:
        name = r.get("ReservoirName", r.get("reservoir_name", ""))
        if not name:
            continue
        pct = _safe_float(r.get("PercentageOfWaterStorageCapacity", r.get("storage_percentage")))
        level = _safe_float(r.get("WaterLevel", r.get("water_level")))
        inflow = _safe_float(r.get("InflowVolume", r.get("inflow_cms")))
        outflow = _safe_float(r.get("OutflowVolume", r.get("outflow_cms")))
        obs_time = r.get("ObservationTime", r.get("RecordTime", ""))

        reservoirs.append({
            "name": name,
            "storage_pct": pct,
            "water_level": level,
            "inflow": inflow,
            "outflow": outflow,
            "obs_time": obs_time,
        })

    # Sort by storage percentage (low first = more critical)
    reservoirs.sort(key=lambda r: r.get("storage_pct") or 999)

    pct_values = [r["storage_pct"] for r in reservoirs if r["storage_pct"] is not None]
    now = datetime.now(TW_TZ)
    return {
        "updated_at": now.isoformat(),
        "reservoir_count": len(reservoirs),
        "avg_storage_pct": round(sum(pct_values) / len(pct_values), 1) if pct_values else None,
        "min_storage_pct": min(pct_values) if pct_values else None,
        "critical_count": sum(1 for p in pct_values if p < 50),
        "reservoirs": reservoirs,
    }


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # AQI
    print("Collecting Taiwan AQI data...")
    try:
        aqi = fetch_aqi()
        (DATA_DIR / "tw_aqi.json").write_text(json.dumps(aqi, indent=2, ensure_ascii=False))
        print(f"  stations: {aqi['station_count']} | avg AQI: {aqi['avg_aqi']} | "
              f"worst: {aqi['worst_station']['station'] if aqi['worst_station'] else '?'} "
              f"({aqi['max_aqi']})")
    except Exception as e:
        print(f"  AQI error: {e}", file=sys.stderr)

    # Reservoir
    print("Collecting Taiwan reservoir data...")
    try:
        reservoir = fetch_reservoir()
        (DATA_DIR / "tw_reservoir.json").write_text(json.dumps(reservoir, indent=2, ensure_ascii=False))
        print(f"  reservoirs: {reservoir['reservoir_count']} | avg storage: {reservoir['avg_storage_pct']}% | "
              f"critical (<50%): {reservoir['critical_count']}")
    except Exception as e:
        print(f"  Reservoir error: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
