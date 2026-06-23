"""Folium map builder utilities."""

import math
from datetime import datetime, timedelta

import folium
from folium.plugins import Fullscreen

from config.settings import HAIL_CITY_CENTER, HAIL_CITY_RADIUS_KM
from core.radar_client import get_latest_radar_tile_url
from core.risk_engine import calculate_risk_score
from core.satellite_client import get_satellite_tile_layer_url
from core.weather_client import get_current_rainfall, get_rainfall_forecast
from components.popup_builder import build_risk_popup_html


def create_base_map(center=None, zoom_start=12) -> folium.Map:
    if center is None:
        center = HAIL_CITY_CENTER
    m = folium.Map(location=center, zoom_start=zoom_start, tiles="OpenStreetMap", control_scale=True)
    Fullscreen(
        position="topleft",
        title="\u0639\u0631\u0636 \u0645\u0644\u0621 \u0627\u0644\u0634\u0627\u0634\u0629",
        title_cancel="\u062e\u0631\u0648\u062c \u0645\u0646 \u0645\u0644\u0621 \u0627\u0644\u0634\u0627\u0634\u0629",
        force_separate_button=True,
    ).add_to(m)
    return m


def add_satellite_layer(map_obj: folium.Map) -> folium.Map:
    tile = get_satellite_tile_layer_url()
    folium.TileLayer(
        tiles=tile["esri_tile_url"],
        attr="Esri World Imagery",
        name="Satellite View",
        overlay=False,
        control=True,
    ).add_to(map_obj)
    return map_obj


def add_radar_layer(map_obj: folium.Map) -> tuple[folium.Map, dict]:
    result = get_latest_radar_tile_url()
    if result["success"]:
        folium.TileLayer(
            tiles=result["tile_url_template"],
            attr="RainViewer",
            name=f"Rain Radar ({result['timestamp']})",
            overlay=True,
            control=True,
            opacity=0.6,
        ).add_to(map_obj)
        return map_obj, {"radar_added": True, "note": None}
    return map_obj, {"radar_added": False, "note": "Radar coverage in this region is limited"}


_HIST_COLORS = {
    "critical": "#D32F2F",
    "high": "#F57C00",
    "moderate": "#FBC02D",
    "low": "#388E3C",
    "stable": "#388E3C",
}


def add_low_points_layer(
    map_obj: folium.Map,
    low_points: list[dict],
    history_lookup: dict | None = None,
    live_risk_lookup: dict | None = None,
) -> folium.Map:
    for p in low_points:
        rw = p["risk_weight"]
        is_osm = p.get("source", "client_verified") == "osm_inferred"
        key = (round(p["latitude"], 5), round(p["longitude"], 5))
        color = "#388E3C"
        risk_level = "low"
        total_score = "\u2014"
        rainfall_score = None
        elevation_score = None
        historical_score = None
        satellite_score = None
        decision_source = "rule_based"

        if history_lookup:
            hs = history_lookup.get(key)
            if hs:
                risk_level = hs.get("risk_level", "low")
                total_score = hs.get("total_score", "\u2014")
                rainfall_score = hs.get("rainfall_score", "\u2014")
                elevation_score = hs.get("elevation_score", "\u2014")
                historical_score = hs.get("historical_score", "\u2014")
                satellite_score = hs.get("satellite_score", "\u2014")
                decision_source = hs.get("decision_source", decision_source)
                color = _HIST_COLORS.get(risk_level, color)
        elif live_risk_lookup:
            lr = live_risk_lookup.get(key)
            if lr:
                risk_level = lr.get("risk_level", "low")
                total_score = lr.get("total_score", "\u2014")
                rainfall_score = lr.get("rainfall_score", None)
                elevation_score = lr.get("elevation_score", None)
                historical_score = lr.get("historical_score", None)
                satellite_score = lr.get("satellite_score", None)
                decision_source = lr.get("decision_source", "rule_based")
                color = _HIST_COLORS.get(risk_level, color)

        risk_data = {
            "risk_level": risk_level,
            "total_score": total_score,
            "rainfall_score": rainfall_score,
            "elevation_score": elevation_score,
            "historical_score": historical_score,
            "satellite_score": satellite_score,
            "decision_source": decision_source,
            "latitude": p["latitude"],
            "longitude": p["longitude"],
            "nearest_low_point": {
                "latitude": p["latitude"],
                "longitude": p["longitude"],
                "elevation_estimate": p["elevation_estimate"],
                "risk_weight": rw,
            },
            "nearest_low_point_source": p.get("source", "client_verified"),
        }
        display_name = p["street_name"]
        tooltip_text = display_name
        if is_osm:
            display_name = display_name + " \u200e(OSM-estimated)"
            tooltip_text = tooltip_text + " \u200e(OSM)"
        common_popup = folium.Popup(
            build_risk_popup_html(risk_data, street_name=display_name),
            max_width=360,
        )
        if risk_level in ("critical", "high", "moderate"):
            icon_color = {"critical": "darkred", "high": "red", "moderate": "orange"}[risk_level]
            folium.Marker(
                location=[p["latitude"], p["longitude"]],
                icon=folium.Icon(color=icon_color, icon="exclamation-triangle", prefix="fa"),
                popup=common_popup,
                tooltip=tooltip_text,
            ).add_to(map_obj)
        else:
            radius = 3 + (rw * 6) if is_osm else 4
            folium.CircleMarker(
                location=[p["latitude"], p["longitude"]],
                radius=radius,
                color="#388E3C",
                fill=True,
                fill_color="#388E3C",
                fill_opacity=0.5,
                weight=1,
                popup=common_popup,
                tooltip=tooltip_text,
            ).add_to(map_obj)
    return map_obj


ALERTS_MAX_AGE_HOURS = 2

def _alert_age_hours(alert: dict, now: datetime = None) -> float:
    if now is None:
        now = datetime.now()
    try:
        ts = alert.get("alert_timestamp", "")
        return (now - datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
    except (ValueError, TypeError, KeyError):
        return 999

def add_alerts_layer(map_obj: folium.Map, alerts: list[dict], recalculate_recent_hours: int = 6) -> folium.Map:
    LIVE_CAP = 15
    icon_map = {"critical": "darkred", "high": "red", "moderate": "orange", "low": "lightgray"}
    now = datetime.now()

    seen = set()
    deduped = []
    for a in sorted(alerts, key=lambda x: x.get("alert_timestamp", ""), reverse=True):
        key = (round(a["latitude"], 5), round(a["longitude"], 5))
        if key not in seen:
            seen.add(key)
            deduped.append(a)

    # Filter to recent alerts only — stale ones should not render danger icons
    deduped = [a for a in deduped if _alert_age_hours(a, now) <= ALERTS_MAX_AGE_HOURS]
    if not deduped:
        return map_obj

    live_count = 0
    hist_count = 0
    total_deduped = len(deduped)

    for a in deduped:
        color = icon_map.get(a.get("risk_level", "low"), "lightgray")
        try:
            alert_time = datetime.strptime(a["alert_timestamp"], "%Y-%m-%d %H:%M:%S")
            age_hours = (datetime.now() - alert_time).total_seconds() / 3600
        except (ValueError, TypeError, KeyError):
            age_hours = 999
        is_recent = age_hours <= recalculate_recent_hours

        risk_data = None

        if is_recent and live_count < LIVE_CAP:
            try:
                current_rain = get_current_rainfall(a["latitude"], a["longitude"])
                forecast = get_rainfall_forecast(a["latitude"], a["longitude"])
                live_risk = calculate_risk_score(
                    a["latitude"],
                    a["longitude"],
                    rainfall_mm=current_rain.get("rainfall_mm", 0.0),
                    forecast_3h_mm=forecast.get("forecast_3h", 0.0),
                )
                risk_data = dict(live_risk)
                risk_data["alert_context"] = {
                    "is_live": True,
                    "logged_at": a["alert_timestamp"],
                    "logged_risk_level": a.get("risk_level"),
                    "logged_score": a.get("risk_score"),
                    "age_hours": round(age_hours, 1),
                }
                live_count += 1
            except Exception:
                pass

        if risk_data is None:
            hist_count += 1
            risk_data = {
                "risk_level": a.get("risk_level", "low"),
                "total_score": a.get("risk_score", "—"),
                "rainfall_score": None,
                "elevation_score": None,
                "historical_score": None,
                "satellite_score": None,
                "decision_source": a.get("decision_source", "rule_based"),
                "latitude": a["latitude"],
                "longitude": a["longitude"],
                "alert_context": {
                    "is_live": False,
                    "logged_at": a["alert_timestamp"],
                    "logged_risk_level": a.get("risk_level"),
                    "logged_score": a.get("risk_score"),
                    "age_hours": round(age_hours, 1),
                },
            }

        folium.Marker(
            location=[a["latitude"], a["longitude"]],
            icon=folium.Icon(color=color, icon="exclamation-triangle", prefix="fa"),
            popup=folium.Popup(
                build_risk_popup_html(risk_data, street_name=a.get("street_name")),
                max_width=360,
            ),
        ).add_to(map_obj)

    print(
        f"[add_alerts_layer] {len(alerts)} input -> {total_deduped} unique locations; "
        f"{live_count} live recalc, {hist_count} historical-only"
    )
    return map_obj


def add_historical_events_layer(
    map_obj: folium.Map, historical_events: list[dict], date_filter: str = None
) -> folium.Map:
    for ev in historical_events:
        if date_filter is not None and ev.get("event_date") != date_filter:
            continue
        rs = calculate_risk_score(
            ev["latitude"],
            ev["longitude"],
            rainfall_mm=ev.get("actual_rainfall_mm", 0.0),
            forecast_3h_mm=0.0,
        )
        risk_data = {
            "risk_level": ev.get("severity", "moderate"),
            "total_score": rs["total_score"],
            "rainfall_score": rs["rainfall_score"],
            "elevation_score": rs["elevation_score"],
            "historical_score": rs["historical_score"],
            "satellite_score": rs["satellite_score"],
            "decision_source": "\u0623\u0631\u0634\u064a\u0641 \u0627\u0644\u0646\u0638\u0627\u0645 \u0627\u0644\u062a\u0627\u0631\u064a\u062e\u064a (Snapshot)",
            "latitude": ev["latitude"],
            "longitude": ev["longitude"],
            "nearest_low_point_source": rs.get("nearest_low_point_source"),
        }
        folium.CircleMarker(
            location=[ev["latitude"], ev["longitude"]],
            radius=4,
            color="#4B0082",
            fill=True,
            fill_opacity=0.5,
            popup=folium.Popup(
                build_risk_popup_html(risk_data, street_name=ev.get("nearest_street_name", ev.get("event_date"))),
                max_width=360,
            ),
        ).add_to(map_obj)
    return map_obj


def add_layer_control(map_obj: folium.Map) -> folium.Map:
    folium.LayerControl(collapsed=False).add_to(map_obj)
    return map_obj


def add_sentinel2_overlay(map_obj, bbox_coords=None):
    if bbox_coords is None:
        lat_c, lon_c = HAIL_CITY_CENTER
        radius_km = HAIL_CITY_RADIUS_KM
        lat_delta = radius_km / 111.0
        lon_delta = radius_km / (111.0 * math.cos(math.radians(lat_c)))
        bbox_coords = (lon_c - lon_delta, lat_c - lat_delta, lon_c + lon_delta, lat_c + lat_delta)

    from core.satellite_client import fetch_sentinel2_truecolor_overlay

    result = fetch_sentinel2_truecolor_overlay(bbox_coords)
    if result["success"]:
        folium.raster_layers.ImageOverlay(
            image=f"data:image/png;base64,{result['image_base64']}",
            bounds=result["bounds"],
            name=f"Sentinel-2 ({result['acquisition_date']})",
            opacity=0.7,
            overlay=True,
            control=True,
        ).add_to(map_obj)
        note = f"\u0635\u0648\u0631\u0629 \u0645\u0646 {result['acquisition_date']}\u060c \u062F\u0648\u0631\u0629 \u062A\u062C\u062F\u064A\u062F \u0641\u0639\u0644\u064A\u0629 \u062A\u0642\u0631\u064A\u0628\u0627\u064B 5 \u0623\u064A\u0627\u0645"
    else:
        note = "Sentinel-2 imagery unavailable (credentials not configured, no cloud-free image in lookback window, network restrictions, or API limit reached)"

    return map_obj, {"sentinel_added": result["success"], "note": note}


def compute_live_risk_lookup(low_points: list[dict]) -> dict:
    from core.weather_client import city_has_active_rain

    if not city_has_active_rain():
        return {}
    from core.db import get_latest_weather_by_point

    weather_map = get_latest_weather_by_point()

    lookup = {}
    for p in low_points:
        key = (round(p["latitude"], 5), round(p["longitude"], 5))
        w = weather_map.get(p["id"], {})
        try:
            rs = calculate_risk_score(
                p["latitude"],
                p["longitude"],
                rainfall_mm=w.get("rainfall_mm", 0.0),
                forecast_3h_mm=w.get("forecast_3h", 0.0),
            )
            lookup[key] = rs
        except Exception:
            pass
    return lookup


def build_full_dashboard_map(
    low_points: list[dict],
    alerts: list[dict] = None,
    include_satellite: bool = True,
    include_radar: bool = True,
    use_live_risk: bool = True,
) -> folium.Map:
    m = create_base_map()
    radar_status = {"radar_added": False, "note": None}
    if include_satellite:
        m = add_satellite_layer(m)
    if include_radar:
        m, radar_status = add_radar_layer(m)
    live_risk = compute_live_risk_lookup(low_points) if use_live_risk else None
    m = add_low_points_layer(m, low_points, live_risk_lookup=live_risk)
    if alerts:
        m = add_alerts_layer(m, alerts)
    m = add_layer_control(m)
    return m
