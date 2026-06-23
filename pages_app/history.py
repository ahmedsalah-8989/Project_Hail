"""History page — timeline of past events, alerts, and risk scores."""

import datetime as dt
from datetime import datetime

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from components.map_builder import add_layer_control, add_low_points_layer, create_base_map
from core.db import get_all_historical_events, get_low_points
from core.risk_engine import compute_historical_risk_snapshot
from core.weather_client import get_current_rainfall, get_rainfall_forecast

_SOURCE_AR = {
    "client_confirmed": "\u0645\u0624\u0643\u062f \u0645\u0646 \u0627\u0644\u0639\u0645\u064a\u0644",
    "client_confirmed_citywide": "\u0645\u0624\u0643\u062f \u0645\u0646 \u0627\u0644\u0639\u0645\u064a\u0644 (\u0639\u0644\u0649 \u0645\u0633\u062a\u0648\u0649 \u0627\u0644\u0645\u062f\u064a\u0646\u0629)",
}

_SEVERITY_AR = {
    "critical": "\u062d\u0631\u062c",
    "high": "\u0639\u0627\u0644\u064a",
    "moderate": "\u0645\u062a\u0648\u0633\u0637",
    "low": "\u0645\u0646\u062e\u0641\u0636",
}


def render():
    st.markdown(
        "<h1 style='color:#FAFAFA !important;'>\U0001F552 History \u2014 Past Flood Events</h1>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<p style='color: #B0B3B8 !important; font-size: 14px;'>"
        "Browse historical water accumulation events by date across Hail City"
        "</p>",
        unsafe_allow_html=True,
    )

    try:
        all_events = get_all_historical_events()
    except Exception as e:
        st.error(f"Failed to load historical events: {e}")
        all_events = []

    today = dt.date.today()
    unique_dates = sorted({e["event_date"] for e in all_events}) if all_events else []
    min_date = (
        datetime.strptime(unique_dates[0], "%Y-%m-%d").date() if unique_dates else today
    )

    # ── Date picker ──
    container = st.container(border=True)
    with container:
        st.markdown(
            "<h3 style='color: #E4E6EB !important;'>\U0001F4C5 Select Date</h3>",
            unsafe_allow_html=True,
        )
        picked = st.date_input(
            "Choose a date to view flood risk data",
            value=today,
            min_value=min_date,
            max_value=today,
        )
        selected_date = picked.strftime("%Y-%m-%d")
        st.markdown(
            "<p style='color: #B0B3B8 !important; font-size: 13px;'>"
            "\U0001F4CC Calendar shows dates from "
            f"{min_date.strftime('%Y-%m-%d')} through today"
            "</p>",
            unsafe_allow_html=True,
        )

    # ── Today's live weather snapshot ──
    if selected_date == today.strftime("%Y-%m-%d"):
        st.markdown(
            f"<h3 style='color: #E4E6EB !important;'>\U0001F4CD Today: {selected_date} — Live Conditions</h3>",
            unsafe_allow_html=True,
        )
        try:
            from config.settings import HAIL_CITY_CENTER

            lat, lon = HAIL_CITY_CENTER
            w = get_current_rainfall(lat, lon)
            f = get_rainfall_forecast(lat, lon)
            wcols = st.columns(4)
            with wcols[0]:
                st.metric(
                    "\U0001F321\ufe0f Temp",
                    f"{w.get('temperature_c', '\u2014')} \u00b0C"
                    if w.get("temperature_c") is not None
                    else "\u2014",
                )
            with wcols[1]:
                st.metric(
                    "\U0001F4A7 Humidity",
                    f"{w.get('humidity_pct', '\u2014')}%"
                    if w.get("humidity_pct") is not None
                    else "\u2014",
                )
            with wcols[2]:
                st.metric(
                    "\U0001F4A8 Wind",
                    f"{w.get('wind_speed_ms', '\u2014')} m/s"
                    if w.get("wind_speed_ms") is not None
                    else "\u2014",
                )
            with wcols[3]:
                fr = f.get("forecast_3h", 0.0)
                st.metric(
                    "\U0001F327\ufe0f Rain 3h Forecast",
                    f"{fr} mm" if fr else "\u2014",
                )
        except Exception:
            st.markdown(
                "<p style='color: #B0B3B8 !important; font-size: 13px;'>"
                "Live weather data unavailable for today"
                "</p>",
                unsafe_allow_html=True,
            )

    else:
        st.markdown(
            f"<h3 style='color: #E4E6EB !important;'>\U0001F4CD Historical View: {selected_date}</h3>",
            unsafe_allow_html=True,
        )

    # ── Filter events for selected date ──
    events_on_date = [e for e in all_events if e["event_date"] == selected_date]
    has_data = bool(events_on_date)

    if not has_data:
        st.markdown(
            "<div style='background: #2D2D3A; border: 1px solid #3E3F4A; border-radius: 8px; "
            "padding: 12px 16px; margin: 8px 0; color: #E4E6EB !important;'>"
            "\U0001F50D No historical flood logs found for this specific date. "
            "All monitoring points will display as Safe (Green) due to zero rainfall."
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div style='background: #1B3A2D; border: 1px solid #2D6A4F; border-radius: 8px; "
            f"padding: 12px 16px; margin: 8px 0; color: #6FCF97 !important;'>"
            f"\U0001F4CB Found {len(events_on_date)} event(s) logged for {selected_date}"
            f"</div>",
            unsafe_allow_html=True,
        )

    col_a, col_b = st.columns([3, 1])
    with col_a:
        st.empty()
    with col_b:
        st.metric(
            "\u0627\u0644\u0623\u062d\u062f\u0627\u062b \u0641\u064a \u0647\u0630\u0627 \u0627\u0644\u062a\u0627\u0631\u064a\u062e",
            len(events_on_date),
        )

    # ── Risk map for selected date ──
    st.markdown(
        f"<h3 style='color: #E4E6EB !important;'>\U0001F5FA\uFE0F Risk Map for {selected_date}</h3>",
        unsafe_allow_html=True,
    )
    try:
        low_points = get_low_points()

        with st.spinner("\u23F3 \u062C\u0627\u0631\u064A \u062D\u0633\u0627\u0628 \u0645\u0633\u062A\u0648\u064A\u0627\u062A \u0627\u0644\u062E\u0637\u0648\u0631\u0629..."):
            snapshot = compute_historical_risk_snapshot(
                selected_date,
                low_points=low_points,
                historical_events=all_events if all_events else None,
            )
            history_lookup = {}
            for pr in snapshot["per_point_results"]:
                key = (round(pr["latitude"], 5), round(pr["longitude"], 5))
                history_lookup[key] = {
                    "total_score": pr["total_score"],
                    "rainfall_score": pr["rainfall_score"],
                    "elevation_score": pr["elevation_score"],
                    "historical_score": pr["historical_score"],
                    "satellite_score": pr["satellite_score"],
                    "risk_level": pr["risk_level"],
                    "decision_source": pr["decision_source"],
                }

        # ── Zero-rainfall override: no events → all points safe (green) ──
        if not has_data:
            for key in history_lookup:
                history_lookup[key]["total_score"] = 0.0
                history_lookup[key]["risk_level"] = "low"
            snapshot["summary"] = {
                "critical_count": 0,
                "high_count": 0,
                "moderate_count": 0,
                "low_count": len(low_points),
                "highest_risk_point": {"street_name": "\u062C\u0645\u064A\u0639 \u0627\u0644\u0646\u0642\u0627\u0637 \u0622\u0645\u0646\u0629", "score": 0},
            }

        map_obj = create_base_map()
        map_obj = add_low_points_layer(
            map_obj, low_points, history_lookup=history_lookup
        )
        map_obj = add_layer_control(map_obj)
        st_folium(
            map_obj,
            height=750,
            use_container_width=True,
            returned_objects=[],
            key=f"history_map_{selected_date}",
        )

        s = snapshot["summary"]
        scols = st.columns(4)
        with scols[0]:
            st.metric("\u0646\u0642\u0627\u0637 \u062E\u0637\u0631 \u062D\u0631\u062C\u0629", s["critical_count"])
        with scols[1]:
            st.metric("\u0646\u0642\u0627\u0637 \u062E\u0637\u0631 \u0639\u0627\u0644\u064A", s["high_count"])
        with scols[2]:
            st.metric("\u0646\u0642\u0627\u0637 \u062E\u0637\u0631 \u0645\u062A\u0648\u0633\u0637", s["moderate_count"])
        with scols[3]:
            st.metric("\u0623\u0639\u0644\u0649 \u0646\u0642\u0637\u0629", s["highest_risk_point"]["street_name"])
    except Exception as e:
        st.markdown(
            "<div style='background: #3D1F1F; border: 1px solid #A94442; border-radius: 8px; "
            "padding: 10px 14px; margin: 8px 0; color: #F5B7B1 !important;'>"
            f"\u274c Could not render risk map: {e}"
            "</div>",
            unsafe_allow_html=True,
        )

    # ── Events table for selected date ──
    if has_data:
        st.markdown(
            "<h3 style='color: #E4E6EB !important;'>\U0001F4CB \u062a\u0641\u0627\u0635\u064a\u0644 \u0627\u0644\u0623\u062d\u062f\u0627\u062b \u0641\u064a \u0647\u0630\u0627 \u0627\u0644\u062a\u0627\u0631\u064a\u062e</h3>",
            unsafe_allow_html=True,
        )
        rows = []
        for e in events_on_date:
            rows.append(
                {
                    "\u0627\u0644\u0645\u0648\u0642\u0639": e.get("nearest_street_name", ""),
                    "\u0627\u0644\u062E\u0637\u0648\u0631\u0629": _SEVERITY_AR.get(
                        e.get("severity", "").lower(), e.get("severity", "")
                    ),
                    "\u0627\u0644\u0648\u0635\u0641": e.get("description", ""),
                    "\u0627\u0644\u0645\u0635\u062F\u0631": _SOURCE_AR.get(
                        e.get("source", ""), e.get("source", "")
                    ),
                }
            )
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)

    # ── Overview chart of all historical dates ──
    if all_events:
        st.markdown(
            "<h3 style='color: #E4E6EB !important;'>\U0001F4C8 \u0646\u0638\u0631\u0629 \u0639\u0627\u0645\u0629 \u0639\u0644\u0649 \u062C\u0645\u064A\u0639 \u0627\u0644\u062A\u0648\u0627\u0631\u064A\u062E \u0627\u0644\u062A\u0627\u0631\u064A\u062E\u064A\u0629</h3>",
            unsafe_allow_html=True,
        )
        try:
            counts = (
                pd.DataFrame(all_events)
                .groupby("event_date")
                .size()
                .reset_index(name="count")
            )
            counts = counts.sort_values("event_date")
            st.bar_chart(counts.set_index("event_date"))
        except Exception as e:
            st.markdown(
                "<div style='background: #3D1F1F; border: 1px solid #A94442; border-radius: 8px; "
                "padding: 10px 14px; margin: 8px 0; color: #F5B7B1 !important;'>"
                f"\u274c Could not render date overview chart: {e}"
                "</div>",
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            "<div style='background: #2D2D3A; border: 1px solid #3E3F4A; border-radius: 8px; "
            "padding: 12px 16px; margin: 8px 0; color: #E4E6EB !important;'>"
            "\U0001F4CB No historical event data to chart."
            "</div>",
            unsafe_allow_html=True,
        )
