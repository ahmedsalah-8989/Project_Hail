"""Premium RTL Arabic popup cards for Folium map markers."""

from datetime import datetime


def _risk_theme(risk_level: str) -> tuple:
    themes = {
        "critical": ("#D32F2F", "#FFFFFF", "\u26a0\ufe0f \u062e\u0637\u0631 \u062d\u0631\u062c \u0644\u0644\u063a\u0627\u064a\u0629"),
        "high": ("#F57C00", "#FFFFFF", "\U0001f538 \u062e\u0637\u0631 \u0639\u0627\u0644\u064a"),
        "moderate": ("#FBC02D", "#000000", "\U0001f539 \u062e\u0637\u0631 \u0645\u062a\u0648\u0633\u0637"),
        "low": ("#388E3C", "#FFFFFF", "\u2705 \u0622\u0645\u0646 / \u062e\u0637\u0631 \u0645\u0646\u062e\u0641\u0636"),
    }
    return themes.get(risk_level, ("#757575", "#FFFFFF", "\u062e\u0637\u0631 \u063a\u064a\u0631 \u0645\u0639\u0631\u0648\u0641"))


def _arabic_name(name: str | None) -> str:
    if not name or name.strip() == "" or name == "Unnamed road":
        return "\u0637\u0631\u064a\u0642 \u063a\u064a\u0631 \u0645\u0633\u0645\u0651\u0649"
    return name


def _format_coord(value) -> str:
    try:
        return f"{float(value):.5f}"
    except (TypeError, ValueError):
        return "\u2014"


_CSS = """
<style>
.hail-card {
  width:340px; max-width:350px; font-family:'Segoe UI',Tahoma,Geneva,Verdana,sans-serif;
  direction:rtl; text-align:right; border-radius:12px; overflow:hidden;
  box-shadow:0 4px 20px rgba(0,0,0,0.25); background:#fff; margin:0;
}
.hail-header {
  padding:14px 16px; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:6px;
}
.hail-name {
  font-size:15px; font-weight:700; line-height:1.3; flex:1 1 auto; min-width:0; word-break:break-word;
}
.hail-badge {
  display:inline-block; padding:4px 10px; border-radius:20px; font-size:12px; font-weight:600; white-space:nowrap;
}
.hail-location {
  padding:8px 14px; font-size:13px; line-height:1.7; color:#333;
  border-bottom:1px solid #f0f0f0; background:#fafafa;
}
.hail-body { padding:10px 14px 6px 14px; }
.hail-table { width:100%; border-collapse:collapse; font-size:13px; }
.hail-table td { padding:6px 8px; border-bottom:1px solid #f0f0f0; vertical-align:middle; }
.hail-table tr:last-child td { border-bottom:none; }
.hail-label { color:#666; font-weight:500; width:55%; }
.hail-value { text-align:left; direction:ltr; font-weight:600; color:#222; width:45%; }
.hail-warning {
  margin:6px 14px 10px 14px; padding:10px 12px; border-radius:8px;
  font-size:13px; font-weight:600; line-height:1.5; text-align:center;
  background:#FFF3E0; color:#BF360C; border:1px solid #FFCC80;
}
.hail-source-note {
  margin:4px 0 0 0; padding:6px 0; font-size:11px; color:#999; text-align:center;
  border-top:1px dashed #eee;
}
@keyframes hail-flash { 0%,100%{opacity:1;} 50%{opacity:0.5;} }
.hail-warning-flash { animation:hail-flash 1.5s ease-in-out infinite; }
.hail-footer {
  padding:8px 14px; font-size:11px; color:#888; text-align:center;
  border-top:1px solid #eee; background:#fafafa;
}
</style>
"""


def _wrap_card(inner_html: str) -> str:
    return _CSS + '<div class="hail-card">' + inner_html + "</div>"


def build_risk_popup_html(risk_data: dict, street_name: str = None, latitude: float = None, longitude: float = None) -> str:
    rl = risk_data.get("risk_level", "low")
    bg, tc, badge = _risk_theme(rl)
    name = _arabic_name(street_name)
    score = risk_data.get("total_score", "N/A")

    if latitude is not None and longitude is not None:
        lat, lon = latitude, longitude
    else:
        nearest = risk_data.get("nearest_low_point") or {}
        lat = nearest.get("latitude", risk_data.get("latitude", "—"))
        lon = nearest.get("longitude", risk_data.get("longitude", "—"))

    nearest = risk_data.get("nearest_low_point") or {}
    elev = nearest.get("elevation_estimate", "—")
    rw = nearest.get("risk_weight", "—")

    rainfall_s = risk_data.get("rainfall_score", "—")
    elevation_s = risk_data.get("elevation_score", "—")
    historical_s = risk_data.get("historical_score", "—")
    satellite_s = risk_data.get("satellite_score", "—")

    decision = risk_data.get("decision_source", "rule_based")
    source_ar = (
        "\u0627\u0644\u0630\u0643\u0627\u0621 \u0627\u0644\u0627\u0635\u0637\u0646\u0627\u0639\u064a \u0627\u0644\u0645\u062d\u0633\u0651\u0646 (ML)"
        if decision == "ml_enhanced"
        else "\u0627\u0644\u0645\u062d\u0631\u0643 \u0627\u0644\u0642\u0627\u0639\u062f\u064a (Rule-based)"
    )

    _LEVEL_AR = {"critical": "\u062d\u0631\u062c", "high": "\u0639\u0627\u0644\u064a", "moderate": "\u0645\u062a\u0648\u0633\u0637", "low": "\u0622\u0645\u0646/\u0645\u0646\u062e\u0641\u0636"}

    alert_banner = ""
    ctx = risk_data.get("alert_context")
    if ctx is not None:
        logged_ar = _LEVEL_AR.get(ctx.get("logged_risk_level", ""), "\u063a\u064a\u0631 \u0645\u0639\u0631\u0648\u0641")
        if ctx.get("is_live"):
            alert_banner = (
                '<div class="hail-warning" style="margin:6px 14px 4px 14px;padding:8px 10px;font-size:12px;'
                'background:#E3F2FD;color:#1565C0;border:1px solid #90CAF9;animation:none;">'
                "\U0001f504 \u0645\u062d\u062f\u0651\u062b \u0627\u0644\u0622\u0646 "
                "(\u0643\u0627\u0646 \u0639\u0646\u062f \u0627\u0644\u062a\u0633\u062c\u064a\u0644: "
                + logged_ar + " \u2014 " + str(ctx.get("logged_score", "?")) + "/100\u060c "
                "\u0645\u0646\u0630 " + str(ctx.get("age_hours", "?")) + " \u0633\u0627\u0639\u0629)"
                "</div>"
            )
        else:
            if rainfall_s is None:
                rainfall_s = "\u063a\u064a\u0631 \u0645\u0633\u062c\u0651\u0644"
            if elevation_s is None:
                elevation_s = "\u063a\u064a\u0631 \u0645\u0633\u062c\u0651\u0644"
            if historical_s is None:
                historical_s = "\u063a\u064a\u0631 \u0645\u0633\u062c\u0651\u0644"
            if satellite_s is None:
                satellite_s = "\u063a\u064a\u0631 \u0645\u0633\u062c\u0651\u0644"
            logged_at = ctx.get("logged_at", "?")
            age_hours_val = ctx.get("age_hours", 999)
            age_str = f"{age_hours_val:.0f}" if isinstance(age_hours_val, (int, float)) else "?"
            alert_banner = (
                '<div class="hail-warning" style="margin:6px 14px 4px 14px;padding:8px 10px;font-size:12px;'
                'background:#FFF8E1;color:#F57F17;border:1px solid #FFE082;animation:none;">'
                "\U0001f4cb \u0633\u062c\u0644 \u062a\u0646\u0628\u064a\u0647 \u0645\u0646 " + logged_at
                + " (\u0645\u0646\u0630 " + age_str + " \u0633\u0627\u0639\u0629) \u2014 "
                "\u0627\u0644\u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u062a\u0641\u0635\u064a\u0644\u064a\u0629 "
                "\u063a\u064a\u0631 \u0645\u062d\u0641\u0648\u0638\u0629 \u0644\u0647\u0630\u0627 \u0627\u0644\u062a\u0646\u0628\u064a\u0647 \u0627\u0644\u0642\u062f\u064a\u0645"
                "</div>"
            )

    warning_html = ""
    storm_icons = "\u2601\ufe0f\u26c8\ufe0f"
    if rl == "critical":
        warning_html = (
            '<div class="hail-warning hail-warning-flash">'
            + storm_icons
            + " \u0645\u062a\u0648\u0642\u0639 \u0627\u0639\u0627\u0642\u0629 \u0627\u0644\u062d\u0631\u0643\u0629 \u0627\u0644\u0645\u0631\u0648\u0631\u064a\u0629 "
            "\u0648\u062a\u062c\u0645\u0639 \u0645\u064a\u0627\u0647 \u0634\u062f\u064a\u062f! "
            + storm_icons
            + "</div>"
        )
    elif rl == "high":
        warning_html = (
            '<div class="hail-warning">'
            + storm_icons
            + " \u0645\u062a\u0648\u0642\u0639 \u0627\u0639\u0627\u0642\u0629 \u0627\u0644\u062d\u0631\u0643\u0629 \u0627\u0644\u0645\u0631\u0648\u0631\u064a\u0629 "
            "\u0648\u062a\u062c\u0645\u0639 \u0645\u064a\u0627\u0647 \u0634\u062f\u064a\u062f! "
            + storm_icons
            + "</div>"
        )

    source_note = ""
    nearest_source = risk_data.get("nearest_low_point_source")
    if nearest_source == "osm_inferred":
        source_note = '<div class="hail-source-note">\u0645\u0644\u0627\u062d\u0638\u0629: \u0646\u0642\u0637\u0629 \u0645\u062d\u0633\u0648\u0628\u0629 \u0645\u0646 \u062e\u0631\u0627\u0626\u0637 \u0627\u0644\u0634\u0648\u0627\u0631\u0639 \u0627\u0644\u0645\u0641\u062a\u0648\u062d\u0629 (OSM)</div>'

    body_rows = (
        '<tr><td class="hail-label">\U0001f4d0 \u0627\u0644\u0627\u0631\u062a\u0641\u0627\u0639 \u0639\u0646 \u0633\u0637\u062d \u0627\u0644\u0628\u062d\u0631</td>'
        f'<td class="hail-value">{elev} \u0645\u062a\u0631</td></tr>'
        '<tr><td class="hail-label">\u2696\ufe0f \u0648\u0632\u0646 \u0627\u0644\u062e\u0637\u0648\u0631\u0629 \u0627\u0644\u062c\u063a\u0631\u0627\u0641\u064a</td>'
        f'<td class="hail-value">{rw}</td></tr>'
        '<tr><td class="hail-label">\U0001f4ca \u0633\u0643\u0648\u0631 \u0627\u0644\u062e\u0637\u0648\u0631\u0629 \u0627\u0644\u0625\u062c\u0645\u0627\u0644\u064a</td>'
        f'<td class="hail-value" style="font-size:18px;color:{bg};">{score} / 100</td></tr>'
        '<tr><td class="hail-label">\u2601\ufe0f \u0627\u0644\u0623\u0645\u0637\u0627\u0631</td>'
        f'<td class="hail-value">{rainfall_s} / 40</td></tr>'
        '<tr><td class="hail-label">\U0001f3d4\ufe0f \u0627\u0644\u0627\u0631\u062a\u0641\u0627\u0639</td>'
        f'<td class="hail-value">{elevation_s} / 30</td></tr>'
        '<tr><td class="hail-label">\U0001f4c5 \u0627\u0644\u062a\u0627\u0631\u064a\u062e\u064a</td>'
        f'<td class="hail-value">{historical_s} / 20</td></tr>'
        '<tr><td class="hail-label">\U0001f4e1 \u0627\u0644\u0623\u0642\u0645\u0627\u0631 \u0627\u0644\u0635\u0646\u0627\u0639\u064a\u0629</td>'
        f'<td class="hail-value">{satellite_s} / 10</td></tr>'
    )

    inner = (
        f'<div class="hail-header" style="background:{bg};color:{tc};">'
        f'<span class="hail-name">{name}</span>'
        f'<span class="hail-badge" style="background:rgba(255,255,255,0.25);color:{tc};">{badge}</span>'
        "</div>"
        + '<div class="hail-location">\U0001f4cd \u0627\u0644\u0645\u0648\u0642\u0639: '
        + name
        + "<br>\U0001f9ed \u0627\u0644\u0625\u062d\u062f\u0627\u062b\u064a\u0627\u062a: "
        + f"{_format_coord(lat)}, {_format_coord(lon)}"
        + "</div>"
        + '<div class="hail-body">'
        + alert_banner
        + '<table class="hail-table">' + body_rows + "</table>"
        + warning_html
        + source_note
        + "</div>"
        + f'<div class="hail-footer">\u0627\u0644\u0645\u0635\u062f\u0631: {source_ar}</div>'
    )

    return _wrap_card(inner)


def build_weather_popup_section(weather_data: dict) -> str:
    rain = weather_data.get("rainfall_mm")
    f1h = weather_data.get("forecast_1h")
    f3h = weather_data.get("forecast_3h")

    def v(x):
        return f"{x} \u0645\u0644\u0645" if x is not None else "\u2014"

    rows = (
        '<tr><td class="hail-label">\U0001f327 \u0627\u0644\u0623\u0645\u0637\u0627\u0631 \u0627\u0644\u062d\u0627\u0644\u064a\u0629</td>'
        f'<td class="hail-value">{v(rain)}</td></tr>'
        '<tr><td class="hail-label">\U0001f52e \u062a\u0648\u0642\u0639 \u0633\u0627\u0639\u0629</td>'
        f'<td class="hail-value">{v(f1h)}</td></tr>'
        '<tr><td class="hail-label">\U0001f52e \u062a\u0648\u0642\u0639 3 \u0633\u0627\u0639\u0627\u062a</td>'
        f'<td class="hail-value">{v(f3h)}</td></tr>'
    )

    inner = (
        '<div class="hail-header" style="background:#1565C0;color:#fff;">'
        '<span class="hail-name">\U0001f4c8 \u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0644\u0637\u0642\u0633</span>'
        "</div>"
        '<div class="hail-body"><table class="hail-table">' + rows + "</table></div>"
    )

    return _wrap_card(inner)


def build_water_detection_popup_section(water_data: dict = None) -> str:
    if water_data is None or not water_data.get("success"):
        inner = (
            '<div class="hail-header" style="background:#616161;color:#fff;">'
            '<span class="hail-name">\U0001f4a7 \u0627\u0644\u0643\u0634\u0641 \u0639\u0646 \u0627\u0644\u0645\u064a\u0627\u0647</span>'
            "</div>"
            '<div class="hail-body" style="padding:14px;font-size:13px;color:#888;text-align:center;">'
            "\u0643\u0634\u0641 \u0627\u0644\u0645\u064a\u0627\u0647 \u0639\u0628\u0631 \u0627\u0644\u0623\u0642\u0645\u0627\u0631 \u0627\u0644\u0635\u0646\u0627\u0639\u064a\u0629 "
            "\u063a\u064a\u0631 \u0645\u062a\u0627\u062d \u0644\u0647\u0630\u0627 \u0627\u0644\u0645\u0648\u0642\u0639"
            "<br><span style='font-size:11px;color:#aaa;'>\u0644\u0627 \u062a\u0648\u062c\u062f \u0635\u0648\u0631 \u062d\u062f\u064a\u062b\u0629 "
            "\u0623\u0648 \u0628\u064a\u0627\u0646\u0627\u062a \u0627\u0639\u062a\u0645\u0627\u062f</span>"
            "</div>"
        )
        return _wrap_card(inner)

    detected = water_data.get("water_detected", False)
    pct = water_data.get("water_coverage_pct", 0.0)
    ndwi = water_data.get("ndwi_mean", "\u2014")

    badge_color = "#1E90FF" if detected else "#388E3C"
    badge_text = "\u0646\u0639\u0645" if detected else "\u0644\u0627"

    rows = (
        '<tr><td class="hail-label">\U0001f4a7 \u0648\u062c\u0648\u062f \u0645\u064a\u0627\u0647</td>'
        f'<td class="hail-value"><span style="background:{badge_color};color:#fff;padding:2px 12px;'
        f'border-radius:12px;font-size:12px;font-weight:600;">{badge_text}</span></td></tr>'
        '<tr><td class="hail-label">\U0001f4ca \u0646\u0633\u0628\u0629 \u0627\u0644\u062a\u063a\u0637\u064a\u0629</td>'
        f'<td class="hail-value">{pct}%</td></tr>'
        '<tr><td class="hail-label">\U0001f4c9 \u0645\u062a\u0648\u0633\u0637 NDWI</td>'
        f'<td class="hail-value">{ndwi}</td></tr>'
    )

    inner = (
        '<div class="hail-header" style="background:#2E7D32;color:#fff;">'
        '<span class="hail-name">\U0001f4a7 \u0627\u0644\u0643\u0634\u0641 \u0639\u0646 \u0627\u0644\u0645\u064a\u0627\u0647</span>'
        "</div>"
        '<div class="hail-body"><table class="hail-table">' + rows + '</table>'
        '<div style="padding:6px 0 4px 0;font-size:11px;color:#999;text-align:center;">'
        "\u0627\u0633\u062a\u0646\u0627\u062f\u064b\u0627 \u0625\u0644\u0649 \u0635\u0648\u0631 Sentinel-2 "
        "(\u062a\u062a\u062c\u062f\u062f \u0643\u0644 ~5 \u0623\u064a\u0627\u0645\u060c \u0644\u064a\u0633 \u0641\u0648\u0631\u064a\u064b\u0627)"
        "</div></div>"
    )

    return _wrap_card(inner)


def build_satellite_image_popup_section(
    acquisition_date: str = None, image_available: bool = False
) -> str:
    if not image_available or acquisition_date is None:
        inner = (
            '<div class="hail-header" style="background:#5D4037;color:#fff;">'
            '<span class="hail-name">\U0001f4f7 \u0627\u0644\u0635\u0648\u0631\u0629 \u0627\u0644\u0641\u0636\u0627\u0626\u064a\u0629</span>'
            "</div>"
            '<div class="hail-body" style="padding:14px;font-size:13px;color:#888;text-align:center;">'
            "\u0635\u0648\u0631\u0629 \u0641\u0636\u0627\u0626\u064a\u0629: \u063a\u064a\u0631 \u0645\u062a\u0627\u062d\u0629"
            "</div>"
        )
        return _wrap_card(inner)

    try:
        img_date = datetime.strptime(acquisition_date[:10], "%Y-%m-%d")
        days_diff = (datetime.now() - img_date).days
        age = f"(\u0642\u062f\u0645\u0647\u0627 {days_diff} \u064a\u0648\u0645)"
    except (ValueError, TypeError):
        age = ""

    inner = (
        '<div class="hail-header" style="background:#5D4037;color:#fff;">'
        '<span class="hail-name">\U0001f4f7 \u0627\u0644\u0635\u0648\u0631\u0629 \u0627\u0644\u0641\u0636\u0627\u0626\u064a\u0629</span>'
        "</div>"
        '<div class="hail-body" style="padding:14px;font-size:13px;text-align:center;">'
        f"\u062a\u0627\u0631\u064a\u062e \u0627\u0644\u0627\u0644\u062a\u0642\u0627\u0637: {acquisition_date}<br>"
        f'<span style="color:#888;font-size:12px;">{age}</span>'
        "</div>"
    )

    return _wrap_card(inner)


def build_full_location_popup(
    risk_data: dict,
    weather_data: dict = None,
    water_data: dict = None,
    satellite_acquisition_date: str = None,
    street_name: str = None,
    latitude: float = None,
    longitude: float = None,
) -> str:
    parts = [build_risk_popup_html(risk_data, street_name, latitude, longitude)]

    if weather_data is not None:
        parts.append(build_weather_popup_section(weather_data))

    parts.append(build_water_detection_popup_section(water_data))
    parts.append(
        build_satellite_image_popup_section(
            satellite_acquisition_date,
            image_available=satellite_acquisition_date is not None,
        )
    )

    separator = '<hr style="margin:6px 0;border:0;border-top:1px solid #e0e0e0;">'
    return _CSS + '<div style="display:flex;flex-direction:column;gap:8px;max-width:350px;">' + separator.join(parts) + "</div>"
