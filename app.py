"""Main application entry point — sidebar, navigation, and cross-page CSS."""

from datetime import datetime

import streamlit as st
from pages_app import dashboard, risk_map, report, history
from core import scheduler

# ── Start background scheduler (exactly once across Streamlit hot-reloads) ──
if "scheduler_started" not in st.session_state:
    scheduler.start_scheduler_thread()
    st.session_state["scheduler_started"] = True

st.set_page_config(
    page_title="Hail Flood Early Warning System",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ────────────────────────────────────────────────────────────────────────────
# CUSTOM CSS — high-contrast typography, permanently locked sidebar, dark KPIs
# ────────────────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
    /* ── Hide Streamlit chrome ── */
    #MainMenu, footer, header {visibility: hidden;}

    /* ── Force sidebar container to always display at full width ── */
    [data-testid="stSidebar"],
    section[data-testid="stSidebar"] {
        display: block !important;
        visibility: visible !important;
        min-width: 300px !important;
        max-width: 300px !important;
        transform: none !important;
        transition: none !important;
    }

    /* ── Adjust main content margin so it doesn't overlap the forced sidebar ── */
    [data-testid="stAppViewBlockContainer"] {
        margin-left: 20px !important;
    }

    /* ── Hide all sidebar collapse toggle buttons ── */
    [data-testid="stSidebarCollapseButton"],
    button[aria-label="Collapse sidebar"],
    button[aria-label="Expand sidebar"],
    .stSidebarCollapseButton {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        height: 0 !important;
        width: 0 !important;
    }

    /* ── Heading weight ── */
    .stMarkdown h1,
    .stMarkdown h2,
    .stMarkdown h3,
    .stMarkdown h4 {
        font-weight: 700 !important;
    }



    /* ── Sidebar separator ── */
    section[data-testid="stSidebar"] hr {
        border-color: #374151 !important;
    }

    /* Sidebar status badge */
    section[data-testid="stSidebar"] .sync-badge {
        display: inline-block;
        background: #1B3A2D;
        color: #6FCF97 !important;
        border: 1px solid #2D6A4F;
        border-radius: 14px;
        padding: 3px 14px;
        font-size: 0.8rem;
        font-weight: 600;
        margin: 4px 0 8px;
    }

    /* Sidebar model metrics (re-assert after .stMarkdown * override) */
    section[data-testid="stSidebar"] .model-metric {
        font-size: 0.85rem;
        color: #D1D5DB !important;
        margin: 3px 0;
    }
    section[data-testid="stSidebar"] .model-metric strong {
        color: #FFFFFF !important;
    }

    /* ──────────────────────────────────────────────────────────────────────
       DARK KPI METRIC CARDS (high contrast on light page background)
       ────────────────────────────────────────────────────────────────────── */
    div[data-testid="stMetric"] {
        background: #262730 !important;
        border: 1px solid #3E3F4A;
        border-radius: 10px;
        padding: 18px 14px 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.25);
        transition: box-shadow .15s ease;
    }
    div[data-testid="stMetric"]:hover {
        box-shadow: 0 4px 14px rgba(0,0,0,0.35);
    }
    /* Metric label */
    div[data-testid="stMetric"] > div:first-child {
        font-size: 0.85rem;
        font-weight: 600;
        color: #E0E0E0 !important;
        letter-spacing: 0.02em;
    }
    /* Metric value */
    div[data-testid="stMetric"] > div:nth-child(2) {
        font-size: 1.6rem;
        font-weight: 700;
        color: #FFFFFF !important;
    }
    /* Metric delta */
    div[data-testid="stMetric"] div[data-testid="stMetricDelta"] svg,
    div[data-testid="stMetric"] div[data-testid="stMetricDelta"] {
        color: #00E5FF !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ────────────────────────────────────────────────────────────────────────────
# SIDEBAR — navigation at top, system / model status at bottom
# ────────────────────────────────────────────────────────────────────────────
st.sidebar.markdown("### \U0001f6a8 \u0646\u0638\u0627\u0645 \u0627\u0644\u0625\u0646\u0630\u0627\u0631 \u0627\u0644\u0645\u0628\u0643\u0631")

# ── Navigation (TOP) ──
page = st.sidebar.radio(
    "\u0627\u0644\u0630\u0647\u0627\u0628 \u0625\u0644\u0649",
    ["Dashboard", "Risk Map", "Report", "History"],
)

st.sidebar.markdown("---")

# ── System Control & Status (BOTTOM) ──
st.sidebar.markdown("**\U0001F504 System Control & Status**")
st.sidebar.markdown(
    '<span class="sync-badge">\u25cf Auto-Sync: Active (Every 30 Mins)</span>',
    unsafe_allow_html=True,
)

ts = scheduler.LAST_RUN_TIMESTAMP
if ts:
    st.sidebar.markdown(
        f"<p style='color:#B0B3B8 !important;font-size:13px;'>\u23F0 Last Cycle: {ts}</p>",
        unsafe_allow_html=True,
    )
else:
    st.sidebar.markdown(
        "<p style='color:#B0B3B8 !important;font-size:13px;'>\u23F0 Last Cycle: Waiting for first run...</p>",
        unsafe_allow_html=True,
    )

if st.sidebar.button("\U0001f504 Check Now", type="primary", key="check_now_btn"):
    with st.spinner("\u062C\u0627\u0631\u064A \u0627\u0644\u0641\u062D\u0635..."):
        result = scheduler.run_automatic_update_cycle()
    pts = result.get("low_points_monitored", 0)
    status = result.get("execution_status", "failed")
    if status == "success":
        st.sidebar.success(f"\u2705 Cycle done: {pts} points")
    else:
        st.sidebar.error(f"\u274c Cycle failed: {pts} points")

# ── Model Info block (BOTTOM) ──
st.sidebar.markdown("---")
st.sidebar.markdown("**\U0001F9E0 Model & Data Status**")
try:
    from core.db import get_last_training_run, get_total_feedback_count

    last_run = get_last_training_run()
    pending_fb = get_total_feedback_count()
    if last_run:
        ver = last_run.get("model_version", "N/A")
        acc = last_run.get("accuracy", "N/A")
        trained_at = last_run.get("trained_at", "")
        st.sidebar.markdown(
            f'<div class="model-metric">Version: <strong>{ver}</strong></div>',
            unsafe_allow_html=True,
        )
        acc_str = f"{acc:.2%}" if isinstance(acc, (int, float)) else str(acc)
        st.sidebar.markdown(
            f'<div class="model-metric">Accuracy: <strong>{acc_str}</strong></div>',
            unsafe_allow_html=True,
        )
        st.sidebar.markdown(
            f'<div class="model-metric">Trained: <strong>{trained_at[:10] if trained_at else "\u2014"}</strong></div>',
            unsafe_allow_html=True,
        )
    else:
        st.sidebar.markdown(
            '<div class="model-metric">Model: <strong>Not trained yet</strong></div>',
            unsafe_allow_html=True,
        )
    st.sidebar.markdown(
        f'<div class="model-metric">Pending ML feedback: <strong>{pending_fb} / 30</strong></div>',
        unsafe_allow_html=True,
    )
except Exception:
    st.sidebar.markdown(
        '<div class="model-metric">Model status: <strong>N/A</strong></div>',
        unsafe_allow_html=True,
    )

# ────────────────────────────────────────────────────────────────────────────
# NEW-ALERTS BANNER (shown on any page)
# ────────────────────────────────────────────────────────────────────────────
from core.db import get_alert_count_since

if "last_seen_timestamp" not in st.session_state:
    st.session_state["last_seen_timestamp"] = datetime.now().isoformat()

new_count = get_alert_count_since(st.session_state["last_seen_timestamp"])
if new_count > 0:
    st.warning(
        f"\u26a0\ufe0f \u062A\u0645 \u0631\u0635\u062F {new_count} \u062A\u0646\u0628\u064A\u0647 \u062C\u062F\u064A\u062F \u0645\u0646\u0630 \u0622\u062E\u0631 \u0632\u064A\u0627\u0631\u0629 \u2014 "
        f"\u0631\u0627\u062C\u0639 \u0635\u0641\u062D\u0629 \u0627\u0644\u062A\u0642\u0627\u0631\u064A\u0631 \u0623\u0648 \u0644\u0648\u062D\u0629 \u0627\u0644\u0645\u0639\u0644\u0648\u0645\u0627\u062A",
        icon="\U0001f514",
    )
    if st.button("\u2705 \u062A\u0645 \u0627\u0644\u0627\u0637\u0644\u0627\u0639 / Mark as seen", key="mark_seen_btn"):
        st.session_state["last_seen_timestamp"] = datetime.now().isoformat()
        st.rerun()

# ────────────────────────────────────────────────────────────────────────────
# PAGE ROUTING
# ────────────────────────────────────────────────────────────────────────────
if page == "Dashboard":
    dashboard.render()
elif page == "Risk Map":
    risk_map.render()
elif page == "Report":
    report.render()
elif page == "History":
    history.render()
