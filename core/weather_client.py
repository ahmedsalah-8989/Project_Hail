"""Weather client for fetching forecast data from Open-Meteo API."""

import time
from datetime import datetime

import requests

from config.settings import (
    HAIL_CITY_CENTER,
    OPENMETEO_ARCHIVE_URL,
    OPENMETEO_BASE_URL,
)


def get_current_rainfall(latitude: float, longitude: float) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "precipitation,rain,weather_code,temperature_2m,relative_humidity_2m,wind_speed_10m",
        "timezone": "Asia/Riyadh",
    }
    try:
        resp = requests.get(
            f"{OPENMETEO_BASE_URL}/forecast", params=params, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})
        return {
            "rainfall_mm": current.get("precipitation", 0.0),
            "rain_mm": current.get("rain", 0.0),
            "weather_code": current.get("weather_code"),
            "temperature_c": current.get("temperature_2m"),
            "humidity_pct": current.get("relative_humidity_2m"),
            "wind_speed_ms": current.get("wind_speed_10m"),
            "success": True,
            "error": None,
        }
    except requests.RequestException as e:
        return {
            "rainfall_mm": 0.0,
            "rain_mm": 0.0,
            "weather_code": None,
            "temperature_c": None,
            "humidity_pct": None,
            "wind_speed_ms": None,
            "success": False,
            "error": str(e),
        }


def get_rainfall_forecast(latitude: float, longitude: float, hours: int = 6) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "precipitation,precipitation_probability",
        "forecast_days": 2,
        "timezone": "Asia/Riyadh",
    }
    try:
        resp = requests.get(
            f"{OPENMETEO_BASE_URL}/forecast", params=params, timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "forecast_1h": 0.0,
            "forecast_3h": 0.0,
            "hourly_data": [],
        }

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])
    precipitations = hourly.get("precipitation", [])
    probabilities = hourly.get("precipitation_probability", [])

    if not times:
        return {
            "success": False,
            "error": "No hourly time data returned",
            "forecast_1h": 0.0,
            "forecast_3h": 0.0,
            "hourly_data": [],
        }

    now_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
    now_str = now_hour.strftime("%Y-%m-%dT%H:%M")
    try:
        start_idx = times.index(now_str)
    except ValueError:
        print(
            f"Warning: current hour {now_str} not found in API response. Defaulting to index 0."
        )
        start_idx = 0

    forecast_1h = sum(precipitations[start_idx : start_idx + 1])
    forecast_3h = sum(precipitations[start_idx : start_idx + 3])

    hourly_data = []
    for i in range(start_idx, min(start_idx + hours, len(times))):
        hourly_data.append({
            "time": times[i],
            "precipitation": precipitations[i] if i < len(precipitations) else 0.0,
            "probability": probabilities[i] if i < len(probabilities) else 0,
        })

    return {
        "success": True,
        "error": None,
        "forecast_1h": forecast_1h,
        "forecast_3h": forecast_3h,
        "hourly_data": hourly_data,
    }


def city_has_active_rain() -> bool:
    """Single source of truth: does any low point have live rainfall or forecast > 0?"""
    from core.db import get_latest_weather_by_point
    wm = get_latest_weather_by_point()
    if not wm:
        return False
    return any(
        w.get("rainfall_mm", 0) > 0 or w.get("forecast_3h", 0) > 0
        for w in wm.values()
    )


def get_weather_for_all_low_points() -> list[dict]:
    from core.db import get_low_points

    points = get_low_points()
    results = []

    for i, point in enumerate(points):
        lat = point["latitude"]
        lon = point["longitude"]
        current = get_current_rainfall(lat, lon)
        forecast = get_rainfall_forecast(lat, lon)
        results.append({
            "id": point["id"],
            "latitude": lat,
            "longitude": lon,
            "street_name": point["street_name"],
            "risk_weight": point["risk_weight"],
            **current,
            **forecast,
        })
        print(
            f"Fetched weather for {i + 1}/{len(points)}: {point['street_name']}"
        )
        time.sleep(0.3)

    return results


def save_weather_readings_to_db(weather_data: list[dict]) -> int:
    from core.db import insert_weather_reading

    saved = 0
    for entry in weather_data:
        if not entry.get("success"):
            continue
        insert_weather_reading(
            latitude=entry["latitude"],
            longitude=entry["longitude"],
            rainfall_mm=entry.get("rainfall_mm", 0.0),
            rainfall_forecast_1h=entry.get("forecast_1h", 0.0),
            rainfall_forecast_3h=entry.get("forecast_3h", 0.0),
            source="open_meteo",
        )
        saved += 1
    return saved


def get_historical_rainfall(latitude: float, longitude: float, date: str) -> dict:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": date,
        "end_date": date,
        "daily": "precipitation_sum,rain_sum,precipitation_hours",
        "timezone": "Asia/Riyadh",
    }
    try:
        resp = requests.get(OPENMETEO_ARCHIVE_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        daily = data.get("daily", {})
        precip_sum = daily.get("precipitation_sum", [None])[0]
        rain_sum = daily.get("rain_sum", [None])[0]
        precip_hours = daily.get("precipitation_hours", [None])[0]
        return {
            "success": True,
            "error": None,
            "precipitation_sum_mm": float(precip_sum) if precip_sum is not None else 0.0,
            "rain_sum_mm": float(rain_sum) if rain_sum is not None else 0.0,
            "precipitation_hours": float(precip_hours) if precip_hours is not None else 0.0,
        }
    except requests.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "precipitation_sum_mm": 0.0,
            "rain_sum_mm": 0.0,
            "precipitation_hours": 0.0,
        }
