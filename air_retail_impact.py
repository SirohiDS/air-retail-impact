"""
air_retail_impact.py
====================
Retail Intelligence Pipeline — Air Quality Edition

Fetches real-time PM2.5 data from OpenAQ v3 for 10 global high-street
locations, applies a retail footfall elasticity model, and outputs:
  - retail_risk.json   : structured risk report
  - Console summary    : pandas-formatted table

Usage:
    python air_retail_impact.py
    (you will be prompted for your OpenAQ API key)

Get a free API key at: https://explore.openaq.org/register
"""

import json
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

WHO_SAFETY_LIMIT = 15.0          # µg/m³  WHO 24-hour guideline for PM2.5
OPENAQ_BASE      = "https://api.openaq.org/v3"
PM25_PARAM_ID    = 2             # OpenAQ v3 parameter ID for PM2.5
REQUEST_TIMEOUT  = 20            # seconds per HTTP call
RETRY_DELAY      = 2             # seconds between retries on 429

# ---------------------------------------------------------------------------
# Target cities  (10 global high-street retail districts)
# ---------------------------------------------------------------------------

CITIES = [
    {"name": "London",       "district": "High St",        "lat": 51.5074,  "lon": -0.1278,  "iso": "GB"},
    {"name": "Delhi",        "district": "Connaught Place", "lat": 28.6328,  "lon": 77.2197,  "iso": "IN"},
    {"name": "New York",     "district": "5th Ave",         "lat": 40.7580,  "lon": -73.9785, "iso": "US"},
    {"name": "Beijing",      "district": "Wangfujing",      "lat": 39.9042,  "lon": 116.4074, "iso": "CN"},
    {"name": "Mumbai",       "district": "Dharavi",         "lat": 19.0176,  "lon": 72.8562,  "iso": "IN"},
    {"name": "Lahore",       "district": "Old City",        "lat": 31.5497,  "lon": 74.3436,  "iso": "PK"},
    {"name": "Dhaka",        "district": "Motijheel",       "lat": 23.7355,  "lon": 90.4081,  "iso": "BD"},
    {"name": "Bangkok",      "district": "Silom",           "lat": 13.7234,  "lon": 100.5228, "iso": "TH"},
    {"name": "Cairo",        "district": "Downtown",        "lat": 30.0444,  "lon": 31.2357,  "iso": "EG"},
    {"name": "Mexico City",  "district": "Zócalo",          "lat": 19.4326,  "lon": -99.1332, "iso": "MX"},
]

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def _get(url: str, params: dict, headers: dict) -> dict | None:
    """GET with one retry on 429 rate-limit."""
    for attempt in range(2):
        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 429:
            print(f"    [rate-limited] waiting {RETRY_DELAY}s …")
            time.sleep(RETRY_DELAY)
            continue
        resp.raise_for_status()
        return resp.json()
    return None


def fetch_location(lat: float, lon: float, api_key: str) -> tuple[int | None, int | None]:
    """
    Find the nearest OpenAQ location with a PM2.5 sensor.

    Returns (location_id, pm25_sensor_id) or (None, None).
    Searches within a 25 km radius, expanding to country-wide if nothing found.
    """
    headers = {"X-API-Key": api_key}

    for radius in (10_000, 25_000):
        data = _get(
            f"{OPENAQ_BASE}/locations",
            {
                "coordinates":  f"{lat},{lon}",
                "radius":        radius,
                "parameters_id": PM25_PARAM_ID,
                "limit":         5,
            },
            headers,
        )
        if data and data.get("results"):
            break
    else:
        return None, None

    for loc in data["results"]:
        for sensor in loc.get("sensors", []):
            param = sensor.get("parameter", {})
            param_id   = param.get("id")   if isinstance(param, dict) else None
            param_name = param.get("name", "") if isinstance(param, dict) else str(param)
            if param_id == PM25_PARAM_ID or "pm25" in param_name.lower():
                return loc["id"], sensor["id"]

    return None, None


def fetch_latest_pm25(location_id: int, api_key: str) -> tuple[float | None, str | None]:
    """
    Get the most recent PM2.5 reading for a location.

    Returns (value, utc_timestamp_str) or (None, None).
    """
    headers = {"X-API-Key": api_key}
    data = _get(f"{OPENAQ_BASE}/locations/{location_id}/latest", {}, headers)

    if not data:
        return None, None

    for m in data.get("results", []):
        param = m.get("parameter", {})
        pid   = param.get("id") if isinstance(param, dict) else None
        pname = param.get("name", "") if isinstance(param, dict) else str(param)

        if pid == PM25_PARAM_ID or "pm25" in pname.lower():
            dt_block = m.get("datetime", {})
            ts = dt_block.get("utc") if isinstance(dt_block, dict) else None
            return m.get("value"), ts

    return None, None


def fetch_hourly_history(sensor_id: int, api_key: str, limit: int = 24) -> list[dict]:
    """
    Fetch hourly-averaged PM2.5 for the last `limit` hours from a sensor.

    Returns a list of {"datetime": str, "value": float}.
    """
    headers = {"X-API-Key": api_key}
    data    = _get(
        f"{OPENAQ_BASE}/sensors/{sensor_id}/hours",
        {"limit": limit},
        headers,
    )

    if not data:
        return []

    history = []
    for h in data.get("results", []):
        # OpenAQ v3 sensors/hours may use `period.datetimeTo` or top-level `datetime`
        ts = None
        period = h.get("period", {})
        if isinstance(period, dict):
            dt_to = period.get("datetimeTo") or period.get("datetime_to", {})
            ts = dt_to.get("utc") if isinstance(dt_to, dict) else None
        if ts is None:
            dt_block = h.get("datetime", {})
            ts = dt_block.get("utc") if isinstance(dt_block, dict) else None

        val = h.get("value") or h.get("average")
        if ts is not None and val is not None:
            history.append({"datetime": ts, "value": round(float(val), 2)})

    return sorted(history, key=lambda x: x["datetime"])

# ---------------------------------------------------------------------------
# Business logic
# ---------------------------------------------------------------------------

def calculate_footfall_impact(pm25: float) -> tuple[str, str, int]:
    """
    Apply the retail footfall elasticity model.

    Returns (impact_label, revenue_risk, footfall_pct_change).
    """
    if pm25 <= WHO_SAFETY_LIMIT:
        return "Normal (100%)", "Low", 0
    elif pm25 <= 100:
        return "Slight Decrease (-5%)", "Low", -5
    elif pm25 <= 250:
        return "Significant Avoidance (-20%)", "Medium", -20
    else:
        return "Retail Standstill (-50%)", "High", -50


def calculate_forecasts(pm25: float) -> tuple[float, float]:
    """
    24-hour persistence forecast and optimistic recovery forecast.

    Persistence : current reading assumed to hold (worst-case baseline).
    Recovery    : 10% air-quality improvement, mapped to PM2.5 reduction.
    """
    persistence = round(pm25, 2)
    recovery    = round(pm25 * 0.90, 2)
    return persistence, recovery

# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline(api_key: str) -> list[dict]:
    results = []

    print(f"\n{'=' * 62}")
    print(f"  AIR QUALITY RETAIL IMPACT PIPELINE  —  {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 62}\n")

    for city in CITIES:
        label = f"{city['name']} ({city['district']})"
        print(f"  ▶  {label}")

        # Shared stub for cities where data cannot be retrieved
        def _no_data_record(reason: str) -> dict:
            print(f"     ⚠  {reason}\n")
            return {
                "city":                      label,
                "country":                   city["iso"],
                "pm25":                      None,
                "footfall_impact":           "No Data",
                "revenue_risk":              "Unknown",
                "footfall_pct":              None,
                "persistence_forecast_pm25": None,
                "recovery_forecast_pm25":    None,
                "hourly_history":            [],
                "last_updated":              datetime.now(timezone.utc).isoformat(),
            }

        try:
            # 1. Locate nearest monitoring station
            location_id, sensor_id = fetch_location(city["lat"], city["lon"], api_key)

            if location_id is None:
                results.append(_no_data_record("No PM2.5 station found within 25 km."))
                continue

            # 2. Latest PM2.5 reading
            pm25_value, ts = fetch_latest_pm25(location_id, api_key)

            if pm25_value is None:
                results.append(_no_data_record("Station found but no recent PM2.5 reading."))
                continue

            pm25_value = round(float(pm25_value), 2)
            print(f"     PM2.5 = {pm25_value} µg/m³  (station #{location_id})")

            # 3. Business logic
            footfall, risk, pct = calculate_footfall_impact(pm25_value)
            persistence, recovery = calculate_forecasts(pm25_value)

            # 4. Hourly history for chart (best-effort)
            history = []
            if sensor_id:
                try:
                    history = fetch_hourly_history(sensor_id, api_key)
                    print(f"     📊 {len(history)} hourly data points fetched")
                except Exception as e:
                    print(f"     ⚠  History fetch failed: {e}")

            results.append({
                "city":                      label,
                "country":                   city["iso"],
                "pm25":                      pm25_value,
                "footfall_impact":           footfall,
                "revenue_risk":              risk,
                "footfall_pct":              pct,
                "persistence_forecast_pm25": persistence,
                "recovery_forecast_pm25":    recovery,
                "hourly_history":            history,
                "last_updated":              ts or datetime.now(timezone.utc).isoformat(),
            })
            print()

        except requests.exceptions.HTTPError as e:
            results.append(_no_data_record(f"HTTP error: {e}"))
        except requests.exceptions.RequestException as e:
            results.append(_no_data_record(f"Network error: {e}"))

    # 5. Write JSON
    output_path = "retail_risk.json"
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)

    print(f"✅  Saved {output_path}  ({len(results)} cities)\n")

    # 6. Console summary via pandas
    df = pd.DataFrame([
        {
            "City":            r["city"],
            "PM2.5 (µg/m³)":  r["pm25"],
            "Footfall Impact": r["footfall_impact"],
            "Revenue Risk":    r["revenue_risk"],
            "Persistence":     r["persistence_forecast_pm25"],
            "Recovery (-10%)": r["recovery_forecast_pm25"],
        }
        for r in results
    ])
    pd.set_option("display.max_colwidth", 35)
    pd.set_option("display.width", 110)
    print(df.to_string(index=False))
    print()

    return results


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("┌─────────────────────────────────────────────┐")
    print("│  Air Quality Retail Impact Pipeline  v1.0   │")
    print("│  OpenAQ v3 · PM2.5 · WHO 15 µg/m³ limit   │")
    print("└─────────────────────────────────────────────┘\n")
    print("Get a free API key at: https://explore.openaq.org/register\n")

    api_key = input("Enter your OpenAQ API key: ").strip()
    if not api_key:
        print("ERROR: API key cannot be empty.")
        sys.exit(1)

    run_pipeline(api_key)
