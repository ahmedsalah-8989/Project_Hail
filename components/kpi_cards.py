"""KPI card components for Streamlit dashboard — synced with live rain status."""

from datetime import datetime, timedelta

from core.db import get_alerts, get_all_historical_events, get_low_points, get_total_feedback_count
from core.weather_client import city_has_active_rain
from core.weather_client import get_current_rainfall, get_rainfall_forecast
from config.settings import HAIL_CITY_CENTER


def calculate_active_alerts_kpi(alerts: list[dict] = None) -> dict:
    if not city_has_active_rain():
        return {
            "label": "Active Alerts",
            "value": 0,
            "breakdown": {"critical": 0, "high": 0, "moderate": 0, "low": 0},
            "delta_note": None,
        }
    if alerts is None:
        alerts = get_alerts()
    active = [a for a in alerts if a.get("resolved", 0) == 0]
    breakdown = {"critical": 0, "high": 0, "moderate": 0, "low": 0}
    for a in active:
        lvl = a.get("risk_level", "low")
        if lvl in breakdown:
            breakdown[lvl] += 1
    return {
        "label": "Active Alerts",
        "value": len(active),
        "breakdown": breakdown,
        "delta_note": None,
    }


def calculate_highest_risk_area_kpi(alerts: list[dict] = None) -> dict:
    if not city_has_active_rain():
        return {
            "label": "Highest Risk Area",
            "value": "\u2014",
            "risk_score": None,
            "street_name": None,
        }
    if alerts is None:
        alerts = get_alerts()
    if not alerts:
        return {
            "label": "Highest Risk Area",
            "value": "No active alerts",
            "risk_score": None,
            "street_name": None,
        }
    unresolved = [a for a in alerts if a.get("resolved", 0) == 0]
    candidates = unresolved if unresolved else alerts
    top = max(candidates, key=lambda a: a.get("risk_score", 0))
    return {
        "label": "Highest Risk Area",
        "value": top.get("street_name") or "Unknown location",
        "risk_score": top.get("risk_score"),
        "street_name": top.get("street_name"),
    }


def calculate_total_monitored_points_kpi(low_points: list[dict] = None) -> dict:
    if low_points is None:
        low_points = get_low_points(source="client_verified")
    inferred = get_low_points(source="osm_inferred")
    return {
        "label": "Monitored Locations",
        "value": len(low_points),
        "total_with_inferred": len(low_points) + len(inferred),
        "delta_note": None,
    }


def calculate_recent_rainfall_trend_kpi(alerts: list[dict] = None, days: int = 7) -> dict:
    if alerts is None:
        alerts = get_alerts()
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for a in alerts:
        ts = a.get("alert_timestamp")
        if ts is None:
            continue
        try:
            alert_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            continue
        if alert_dt >= cutoff:
            recent.append(a)
    rainfall_values = [a.get("rainfall_mm") for a in recent if a.get("rainfall_mm") is not None]
    if not rainfall_values:
        return {"label": f"Avg Rainfall ({days}d)", "value": "No data", "unit": "mm"}
    avg = sum(rainfall_values) / len(rainfall_values)
    return {"label": f"Avg Rainfall ({days}d)", "value": round(avg, 1), "unit": "mm"}


def calculate_historical_events_summary_kpi(historical_events: list[dict] = None) -> dict:
    if historical_events is None:
        historical_events = get_all_historical_events()
    unique_dates = len(set(e.get("event_date") for e in historical_events if e.get("event_date")))
    return {
        "label": "Historical Flood Events",
        "value": len(historical_events),
        "unique_dates": unique_dates,
    }


def build_live_weather_kpis() -> dict:
    lat, lon = HAIL_CITY_CENTER
    try:
        w = get_current_rainfall(lat, lon)
        f = get_rainfall_forecast(lat, lon)
    except Exception:
        w = {"temperature_c": None, "humidity_pct": None, "wind_speed_ms": None, "success": False}
        f = {"forecast_3h": None}
    try:
        pending = get_total_feedback_count()
    except Exception:
        pending = 0
    return {
        "temperature_c": w.get("temperature_c") if w.get("temperature_c") is not None else "\u2014",
        "wind_speed_ms": w.get("wind_speed_ms") if w.get("wind_speed_ms") is not None else "\u2014",
        "humidity_pct": w.get("humidity_pct") if w.get("humidity_pct") is not None else "\u2014",
        "forecast_3h_mm": f.get("forecast_3h", 0.0) if f.get("forecast_3h") is not None else 0.0,
        "pending_feedback": pending,
        "feedback_threshold": 30,
    }


def build_dashboard_kpi_summary() -> dict:
    alerts = get_alerts()
    low_points = get_low_points()
    historical_events = get_all_historical_events()
    return {
        "active_alerts": calculate_active_alerts_kpi(alerts),
        "highest_risk_area": calculate_highest_risk_area_kpi(alerts),
        "monitored_points": calculate_total_monitored_points_kpi(low_points),
        "rainfall_trend": calculate_recent_rainfall_trend_kpi(alerts),
        "historical_summary": calculate_historical_events_summary_kpi(historical_events),
    }
