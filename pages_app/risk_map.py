"""Risk Map page — interactive folium map showing flood risk zones."""

import streamlit as st
import streamlit.components.v1 as components
import folium
from streamlit_folium import st_folium

from core.db import get_active_alerts_capped, get_alerts, get_low_points
from components.map_builder import (
    add_historical_events_layer,
    build_full_dashboard_map,
)
from components.popup_builder import build_full_location_popup
from core.risk_engine import calculate_risk_score
from core.ml_model import predict_risk_ml
from core.weather_client import get_current_rainfall, get_rainfall_forecast
from core.radar_client import check_radar_coverage_for_hail


def _caption(msg):
    st.markdown(
        f"<p style='color:#B0B3B8 !important;font-size:13px;'>{msg}</p>",
        unsafe_allow_html=True,
    )


def _subheader(msg):
    st.markdown(
        f"<h3 style='color:#E4E6EB !important;'>{msg}</h3>",
        unsafe_allow_html=True,
    )


def _info_box(msg):
    st.markdown(
        f"<div style='background:#1E2A3A;border:1px solid #2D4F6A;border-radius:8px;"
        f"padding:10px 14px;margin:8px 0;color:#B0D4F1 !important;'>{msg}</div>",
        unsafe_allow_html=True,
    )


def _warn_box(msg):
    st.markdown(
        f"<div style='background:#3D3520;border:1px solid #8A6D3B;border-radius:8px;"
        f"padding:10px 14px;margin:8px 0;color:#F0D68A !important;'>{msg}</div>",
        unsafe_allow_html=True,
    )


def _success_box(msg):
    st.markdown(
        f"<div style='background:#1B3A2D;border:1px solid #2D6A4F;border-radius:8px;"
        f"padding:10px 14px;margin:8px 0;color:#6FCF97 !important;'>{msg}</div>",
        unsafe_allow_html=True,
    )


def _err_box(msg):
    st.markdown(
        f"<div style='background:#3D1F1F;border:1px solid #A94442;border-radius:8px;"
        f"padding:10px 14px;margin:8px 0;color:#F5B7B1 !important;'>{msg}</div>",
        unsafe_allow_html=True,
    )


def render():
    st.markdown(
        "<h1 style='color:#FAFAFA !important;'>\U0001F5FA\uFE0F Risk Map \u2014 Hail City Flood Monitoring</h1>",
        unsafe_allow_html=True,
    )
    _caption(
        "Real-time monitoring of rainfall-driven water accumulation risk "
        "across Hail City"
    )

    low_points = get_low_points()
    active_alerts = get_active_alerts_capped(limit=30)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        show_satellite = st.checkbox("Show Satellite Layer", value=True)
    with col2:
        show_radar = st.checkbox("Show Radar Layer", value=True)
    with col3:
        show_historical = st.checkbox("Show Historical Events", value=False)
    with col4:
        show_sentinel = st.checkbox("\U0001F4E1 \u0639\u0631\u0636 \u0635\u0648\u0631 Sentinel-2", value=False)

    _caption(
        "\U0001F4E1 \u0635\u0648\u0631 Sentinel-2 \u0627\u0644\u0641\u0639\u0644\u064A\u0629 (\u062A\u062D\u062F\u064A\u062B \u0643\u0644 ~5 \u0623\u064A\u0627\u0645\u060C \u0648\u0644\u064A\u0633\u062A \u0644\u062D\u0638\u064A\u0629)"
    )

    if show_radar:
        coverage = check_radar_coverage_for_hail()
        if not coverage["radar_available"]:
            _info_box(coverage["coverage_note"])

    map_obj = build_full_dashboard_map(
        low_points,
        alerts=active_alerts,
        include_satellite=show_satellite,
        include_radar=show_radar,
    )

    if show_historical:
        try:
            from core.db import get_all_historical_events

            hist_events = get_all_historical_events()
            map_obj = add_historical_events_layer(map_obj, hist_events)
        except Exception as e:
            _warn_box("Could not load historical events layer: " + str(e))

    if show_sentinel:
        try:
            from components.map_builder import add_sentinel2_overlay

            map_obj, sentinel_status = add_sentinel2_overlay(map_obj)
            if not sentinel_status["sentinel_added"]:
                _info_box("\u2139\ufe0f " + sentinel_status["note"])
        except Exception as e:
            _info_box("\u2139\ufe0f \u0635\u0648\u0631 Sentinel-2 \u063A\u064A\u0631 \u0645\u062A\u0627\u062D\u0629 \u062D\u0627\u0644\u064A\u0627\u064B: " + str(e))

    map_data = st_folium(
        map_obj, height=750, use_container_width=True, returned_objects=["last_object_clicked"]
    )

    clicked = map_data and map_data.get("last_object_clicked")

    if clicked is not None:
        lat = clicked["lat"]
        lon = clicked["lng"]
        _subheader("\U0001F4CD Location Details")
        _caption(f"\U0001F9ED \u0627\u0644\u0625\u062D\u062F\u0627\u062B\u064A\u0627\u062A \u0627\u0644\u0645\u062D\u062F\u062F\u0629: {lat:.5f}, {lon:.5f}")

        try:
            current_rain = get_current_rainfall(lat, lon)
            forecast = get_rainfall_forecast(lat, lon)
        except Exception as e:
            _warn_box("Could not fetch weather data for clicked point: " + str(e))
            return

        try:
            risk = calculate_risk_score(
                lat,
                lon,
                rainfall_mm=current_rain.get("rainfall_mm", 0.0),
                forecast_3h_mm=forecast.get("forecast_3h", 0.0),
            )
        except Exception as e:
            _warn_box("Could not calculate risk for clicked point: " + str(e))
            return

        nearest = risk.get("nearest_low_point") or {}
        nname = nearest.get("street_name", "\u2014")
        ndist = nearest.get("distance_km", "\u2014")
        nsource = risk.get("nearest_low_point_source", "")
        source_suffix = " (OSM-estimated)" if nsource == "osm_inferred" else ""
        ndist_str = f"{ndist:.2f}" if isinstance(ndist, (int, float)) else "\u2014"
        _caption(
            f"\U0001F4CD \u0623\u0642\u0631\u0628 \u0646\u0642\u0637\u0629 \u0645\u0639\u0631\u0648\u0641\u0629: "
            f"{nname} \u2014 \u0627\u0644\u0645\u0633\u0627\u0641\u0629: {ndist_str} \u0643\u0645{source_suffix}"
        )

        water_data = None
        satellite_acquisition_date = None
        with st.spinner("\U0001F4F0\ufe0f \u062C\u0627\u0631\u064A \u0627\u0644\u062A\u062D\u0642\u0642 \u0645\u0646 \u0635\u0648\u0631 \u0627\u0644\u0623\u0642\u0645\u0627\u0631 \u0627\u0644\u0635\u0646\u0627\u0639\u064A\u0629..."):
            try:
                from core.satellite_client import fetch_latest_sentinel2_image
                from core.water_detection import analyze_satellite_image_for_water

                delta = 0.009
                bbox = (lon - delta, lat - delta, lon + delta, lat + delta)
                sat_result = fetch_latest_sentinel2_image(bbox)
                if sat_result.get("success"):
                    satellite_acquisition_date = sat_result.get("acquisition_date")
                    water_data = analyze_satellite_image_for_water(sat_result["image_data"])
            except Exception:
                pass
        street_for_popup = nname if nname != "\u2014" else None
        popup_html = build_full_location_popup(
            risk_data=risk,
            weather_data={
                "rainfall_mm": current_rain.get("rainfall_mm"),
                "forecast_1h": forecast.get("forecast_1h"),
                "forecast_3h": forecast.get("forecast_3h"),
            },
            water_data=water_data,
            satellite_acquisition_date=satellite_acquisition_date,
            street_name=street_for_popup,
            latitude=lat,
            longitude=lon,
        )
        components.html(popup_html, height=500, scrolling=True)
        _caption(
            "\u2139\ufe0f \u0627\u0644\u062A\u062D\u0642\u0642 \u0645\u0646 \u0627\u0644\u0645\u064A\u0627\u0647 \u0639\u0628\u0631 \u0627\u0644\u0623\u0642\u0645\u0627\u0631 \u0627\u0644\u0635\u0646\u0627\u0639\u064A\u0629 "
            "\u064A\u062A\u0637\u0644\u0628 \u0627\u0639\u062A\u0645\u0627\u062F Sentinel Hub \u0646\u0634\u0637 \u0648\u0635\u0648\u0631\u0629 \u063A\u064A\u0631 "
            "\u0645\u0644\u0628\u062F\u0629 \u0628\u0627\u0644\u063A\u064A\u0648\u0645 \u062E\u0644\u0627\u0644 \u0622\u062E\u0631 10 \u0623\u064A\u0627\u0645 \u2014 "
            "\u0642\u062F \u0644\u0627 \u064A\u0643\u0648\u0646 \u0645\u062A\u0627\u062D\u064B\u0627 \u0644\u0643\u0644 \u0627\u0644\u0645\u0648\u0627\u0642\u0639 \u0623\u0648 \u0627\u0644\u0623\u0648\u0642\u0627\u062A"
        )

        try:
            ml_result = predict_risk_ml(
                lat,
                lon,
                current_rainfall_mm=current_rain.get("rainfall_mm", 0.0),
            )
        except Exception as e:
            ml_result = {
                "success": False,
                "error": str(e),
                "ml_available": False,
            }

        left, right = st.columns(2)
        rl = risk.get("risk_level", "low")
        with left:
            if rl == "critical":
                _err_box(f"**Risk Level: {rl.upper()}**")
            elif rl == "high":
                _warn_box(f"**Risk Level: {rl.upper()}**")
            elif rl == "moderate":
                _info_box(f"**Risk Level: {rl.upper()}**")
            else:
                _success_box(f"**Risk Level: {rl.upper()}**")
            st.metric("Total Score", risk.get("total_score", "N/A"))

        with right:
            st.metric(
                "Current Rainfall",
                f"{current_rain.get('rainfall_mm', 'N/A')} mm",
            )
            st.metric(
                "3h Forecast",
                f"{forecast.get('forecast_3h', 'N/A')} mm",
            )

        with st.expander("Full Score Breakdown"):
            breakdown = [
                {
                    "Component": "Rainfall Score",
                    "Max": 40,
                    "Score": risk.get("rainfall_score", "N/A"),
                },
                {
                    "Component": "Elevation Score",
                    "Max": 30,
                    "Score": risk.get("elevation_score", "N/A"),
                },
                {
                    "Component": "Historical Score",
                    "Max": 20,
                    "Score": risk.get("historical_score", "N/A"),
                },
                {
                    "Component": "Satellite Score",
                    "Max": 10,
                    "Score": risk.get("satellite_score", "N/A"),
                },
            ]
            st.table(breakdown)
            _caption(f"Decision source: {risk.get('decision_source', 'N/A')}")

            if ml_result.get("success"):
                st.markdown("**\U0001F9E0 ML Pattern Confirmation**")
                sev = ml_result["predicted_severity"]
                conf = ml_result["confidence"]
                st.metric("ML Predicted Severity", sev.upper() if sev else "N/A")
                st.metric("Confidence", f"{conf:.1%}" if conf else "N/A")
                _caption(
                    f"Interpretation: {ml_result['interpretation']} \u2014 "
                    "ML enhances (does not override) rule-based assessment"
                )
            elif ml_result.get("ml_available") is False:
                _caption("\U0001F9E0 ML model unavailable \u2014 using rule-based only")
    else:
        _caption(
            "\U0001F446 Click anywhere on the map to see detailed risk "
            "information for that location"
        )
