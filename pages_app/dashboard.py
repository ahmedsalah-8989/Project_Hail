"""Dashboard page — main overview of current conditions and risk levels."""

import streamlit as st
import pandas as pd
from streamlit_folium import st_folium

from components.kpi_cards import build_dashboard_kpi_summary, build_live_weather_kpis
from components.map_builder import build_full_dashboard_map
from core.db import get_active_alerts_capped, get_alerts, get_all_historical_events, get_low_points
from core.risk_engine import compute_historical_risk_snapshot
from core.weather_client import city_has_active_rain


def _err_box(msg):
    st.markdown(
        f"<div style='background:#3D1F1F;border:1px solid #A94442;border-radius:8px;"
        f"padding:10px 14px;margin:8px 0;color:#F5B7B1 !important;'>{msg}</div>",
        unsafe_allow_html=True,
    )


def _info_box(msg):
    st.markdown(
        f"<div style='background:#1E2A3A;border:1px solid #2D4F6A;border-radius:8px;"
        f"padding:10px 14px;margin:8px 0;color:#B0D4F1 !important;'>{msg}</div>",
        unsafe_allow_html=True,
    )


def _success_box(msg):
    st.markdown(
        f"<div style='background:#1B3A2D;border:1px solid #2D6A4F;border-radius:8px;"
        f"padding:10px 14px;margin:8px 0;color:#6FCF97 !important;'>{msg}</div>",
        unsafe_allow_html=True,
    )


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


def render():
    st.markdown(
        "<h1 style='color:#FAFAFA !important;'>\U0001F4CA Dashboard \u2014 Hail Flood Early Warning System</h1>",
        unsafe_allow_html=True,
    )
    _caption("System-wide overview of flood risk monitoring across Hail City")

    # ── SECTION 0: Live Weather + System KPIs ──
    try:
        lw = build_live_weather_kpis()
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("\U0001F321\ufe0f Temperature", f"{lw['temperature_c']} \u00b0C" if lw["temperature_c"] != "\u2014" else "\u2014")
        with c2:
            wind = lw["wind_speed_ms"]
            st.metric("\U0001F4A8 Wind Speed", f"{wind} m/s" if wind != "\u2014" else "\u2014")
        with c3:
            hum = lw["humidity_pct"]
            st.metric("\U0001F4A7 Humidity", f"{hum}%" if hum != "\u2014" else "\u2014")
        with c4:
            fr = lw["forecast_3h_mm"]
            st.metric("\U0001F327\ufe0f Rain 3h Forecast", f"{fr} mm" if isinstance(fr, (int, float)) else "\u2014")
        with c5:
            fb = lw["pending_feedback"]
            th = lw["feedback_threshold"]
            st.metric("\U0001F9E0 Pending ML Feedback", f"{fb} / {th}")
    except Exception as e:
        _err_box("Could not load live weather KPIs: " + str(e))

    # ── SECTION 1: KPI Row ──
    try:
        kpis = build_dashboard_kpi_summary()
    except Exception as e:
        _err_box("Could not load KPI data: " + str(e))
        kpis = {
            "active_alerts": {"value": "N/A", "breakdown": {}},
            "highest_risk_area": {"value": "N/A", "risk_score": None},
            "monitored_points": {"value": "N/A"},
            "rainfall_trend": {"label": "Avg Rainfall (7d)", "value": "N/A"},
            "historical_summary": {"value": "N/A", "unique_dates": None},
        }

    try:
        left, mid1, mid2, mid3, right = st.columns(5)
        with left:
            aa = kpis.get("active_alerts", {})
            st.metric("Active Alerts", aa.get("value", "N/A"))
            bd = aa.get("breakdown", {})
            _caption(
                f"C:{bd.get('critical',0)} H:{bd.get('high',0)} "
                f"M:{bd.get('moderate',0)} L:{bd.get('low',0)}"
            )

        with mid1:
            hr = kpis.get("highest_risk_area", {})
            st.metric("Highest Risk Area", hr.get("value", "N/A"))
            rs = hr.get("risk_score")
            _caption(f"Score: {rs}" if rs is not None else "Score: \u2014")

        with mid2:
            mp = kpis.get("monitored_points", {})
            st.metric("Monitored Locations", mp.get("value", "N/A"))

        with mid3:
            rt = kpis.get("rainfall_trend", {})
            val = rt.get("value", "N/A")
            unit = rt.get("unit", "")
            st.metric(rt.get("label", "Avg Rainfall (7d)"), f"{val} {unit}" if unit else val)

        with right:
            hs = kpis.get("historical_summary", {})
            st.metric("Historical Events", hs.get("value", "N/A"))
            ud = hs.get("unique_dates")
            if ud is not None:
                _caption(f"{ud} unique dates")
    except Exception as e:
        _err_box("Error displaying KPI metrics: " + str(e))

    # ── SECTION 2: Map ──
    _subheader("\U0001F5FA\uFE0F City-Wide Monitoring Map")
    try:
        low_points = get_low_points()
        alerts = get_active_alerts_capped(limit=30)
        map_obj = build_full_dashboard_map(
            low_points,
            alerts,
            include_satellite=False,
            include_radar=False,
        )
        st_folium(map_obj, height=750, use_container_width=True, returned_objects=[], key="dashboard_map")
    except Exception as e:
        _err_box("Could not render monitoring map: " + str(e))

    # ── SECTION 3: Recent Alerts Table (synced with map's live state) ──
    _subheader("\U0001F6A8 Recent Alerts")
    try:
        if not city_has_active_rain():
            _success_box("\u2705 Weather is stable. No critical flood areas detected at the moment.")
        else:
            alerts = get_alerts()
            if not alerts:
                _info_box("No alerts recorded yet.")
            else:
                top = sorted(
                    alerts,
                    key=lambda a: a.get("alert_timestamp", ""),
                    reverse=True,
                )[:10]

                rows = []
                for a in top:
                    traffic = (
                        "Yes" if a.get("traffic_disruption_predicted") else "No"
                    )
                    rows.append(
                        {
                            "Timestamp": a.get("alert_timestamp", "\u2014"),
                            "Street": a.get("street_name", "\u2014"),
                            "Risk Level": a.get("risk_level", "low").upper(),
                            "Score": a.get("risk_score", "\u2014"),
                            "Rainfall (mm)": a.get("rainfall_mm", "\u2014") if a.get("rainfall_mm") is not None else "\u2014",
                            "Traffic Impact": traffic,
                        }
                    )

                df = pd.DataFrame(rows)
                st.dataframe(df, use_container_width=True)
    except Exception as e:
        _err_box("Could not load alerts table: " + str(e))

    # ── SECTION 4: Historical Risk Snapshot ──
    _subheader("\U0001F50D \u0627\u0644\u0631\u0635\u062F \u0627\u0644\u062A\u0627\u0631\u064A\u062E\u064A \u0627\u0644\u062D\u0642\u064A\u0642\u064A \u2014 \u0622\u062E\u0631 \u062D\u062F\u062B \u0645\u0624\u0643\u062F")
    try:
        all_events = get_all_historical_events()
        if not all_events:
            _info_box("\u0644\u0627 \u062A\u0648\u062C\u062F \u0623\u062D\u062F\u0627\u062B \u062A\u0627\u0631\u064A\u062E\u064A\u0629 \u0645\u0624\u0643\u062F\u0629 \u0628\u0639\u062F.")
        else:
            unique_dates = sorted({e["event_date"] for e in all_events})
            most_recent = unique_dates[-1]
            snapshot = compute_historical_risk_snapshot(most_recent)
            s = snapshot["summary"]
            hp = s["highest_risk_point"]
            highest_label = f"{hp['street_name']} ({hp['score']})" if hp["street_name"] else f"\u0646\u0642\u0637\u0629 \u0628\u062F\u0631\u062C\u0629 {hp['score']}"

            cols = st.columns(4)
            with cols[0]:
                st.metric("\u062A\u0627\u0631\u064A\u062E \u0627\u0644\u062D\u062F\u062B", most_recent)
            with cols[1]:
                st.metric("\u0646\u0642\u0627\u0637 \u062E\u0637\u0631 \u062D\u0631\u062C\u0629", s["critical_count"])
            with cols[2]:
                st.metric("\u0646\u0642\u0627\u0637 \u062E\u0637\u0631 \u0639\u0627\u0644\u064A", s["high_count"])
            with cols[3]:
                st.metric("\u0623\u0639\u0644\u0649 \u0646\u0642\u0637\u0629 \u062E\u0637\u0648\u0631\u0629", highest_label)

            _caption(
                "\U0001F4CA \u0647\u0630\u0627 \u062A\u062D\u0644\u064A\u0644 \u062A\u0627\u0631\u064A\u062E\u064A \u0644\u0623\u0633\u0648\u0623 \u062D\u062F\u062B \u0645\u0624\u0643\u062F \u0645\u0633\u062C\u0651\u0644\u060C \u0628\u0646\u0627\u0621\u064B \u0639\u0644\u0649 \u0628\u064A\u0627\u0646\u0627\u062A \u0627\u0644\u0623\u0645\u0637\u0627\u0631 \u0627\u0644\u0641\u0639\u0644\u064A\u0629 \u0648\u062C\u063A\u0631\u0627\u0641\u064A\u0629 \u0627\u0644\u0645\u062F\u064A\u0646\u0629 \u2014 \u0648\u0644\u064A\u0633 \u062D\u0627\u0644\u0629 \u0644\u062D\u0638\u064A\u0629"
            )
            _info_box(
                "\U0001F4A1 \u0644\u0639\u0631\u0636 \u0627\u0644\u062A\u0641\u0627\u0635\u064A\u0644 \u0627\u0644\u0643\u0627\u0645\u0644\u0629 \u0648\u062A\u063A\u064A\u064A\u0631 \u0627\u0644\u062A\u0627\u0631\u064A\u062E\u060C "
                "\u0627\u0646\u062A\u0642\u0644 \u0625\u0644\u0649 \u0635\u0641\u062D\u0629 History \u0645\u0646 \u0627\u0644\u0642\u0627\u0626\u0645\u0629 \u0627\u0644\u062C\u0627\u0646\u0628\u064A\u0629"
            )
    except Exception as e:
        _err_box("\u062AA\u0639\u0630\u0631 \u062A\u062D\u0645\u064A\u0644 \u0627\u0644\u0631\u0635\u062F \u0627\u0644\u062A\u0627\u0631\u064A\u062E\u064A: " + str(e))
