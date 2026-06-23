"""Risk scoring engine combining weather, radar, satellite, and OSM data."""

import math

from config.settings import RISK_THRESHOLDS
from core.db import get_all_historical_events, get_low_points


def calculate_distance_km(lat1, lon1, lat2, lon2) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def find_nearest_low_point(latitude, longitude, low_points):
    if not low_points:
        return None
    best = None
    best_dist = float("inf")
    for pt in low_points:
        d = calculate_distance_km(latitude, longitude, pt["latitude"], pt["longitude"])
        if d < best_dist:
            best_dist = d
            best = pt
    result = dict(best)
    result["distance_km"] = round(best_dist, 4)
    return result


def count_nearby_historical_events(
    latitude, longitude, historical_events, radius_km=2.0
):
    count = 0
    for ev in historical_events:
        d = calculate_distance_km(latitude, longitude, ev["latitude"], ev["longitude"])
        if d <= radius_km:
            count += 1
    return count


def calculate_rainfall_score(rainfall_mm, forecast_3h_mm) -> float:
    total = rainfall_mm + (forecast_3h_mm * 0.5)
    if total <= 0:
        return 0.0
    if total < 5:
        return 10.0
    if total < 15:
        return 20.0
    if total < 30:
        return 30.0
    return 40.0


def calculate_elevation_score(nearest_low_point) -> float:
    if nearest_low_point is None:
        return 0.0
    distance_km = nearest_low_point.get("distance_km", 999)
    risk_weight = nearest_low_point.get("risk_weight", 0.3)

    if distance_km > 5:
        proximity_factor = 0.0
    elif distance_km > 2:
        proximity_factor = 0.4
    elif distance_km > 0.5:
        proximity_factor = 0.7
    else:
        proximity_factor = 1.0

    return round(risk_weight * proximity_factor * 30, 2)


def calculate_historical_score(nearby_event_count) -> float:
    if nearby_event_count == 0:
        return 0.0
    if nearby_event_count <= 2:
        return 8.0
    if nearby_event_count <= 5:
        return 14.0
    return 20.0


def calculate_satellite_score(water_detected, water_coverage_pct) -> float:
    if not water_detected:
        return 0.0
    if water_coverage_pct < 15:
        return 5.0
    return 10.0


def calculate_risk_score(
    latitude,
    longitude,
    rainfall_mm,
    forecast_3h_mm,
    water_detected=False,
    water_coverage_pct=0.0,
    low_points=None,
    historical_events=None,
) -> dict:
    if low_points is None:
        low_points = get_low_points()
    if historical_events is None:
        historical_events = get_all_historical_events()

    nearest_low_point = find_nearest_low_point(latitude, longitude, low_points)
    nearby_event_count = count_nearby_historical_events(
        latitude, longitude, historical_events
    )

    rainfall_score = calculate_rainfall_score(rainfall_mm, forecast_3h_mm)
    elevation_score = calculate_elevation_score(nearest_low_point)
    historical_score = calculate_historical_score(nearby_event_count)
    satellite_score = calculate_satellite_score(water_detected, water_coverage_pct)

    total_score = rainfall_score + elevation_score + historical_score + satellite_score
    total_score = max(0, min(100, total_score))

    risk_level = "low"
    for level, (lo, hi) in RISK_THRESHOLDS.items():
        if lo <= total_score <= hi:
            risk_level = level
            break

    nlp_source = None
    if nearest_low_point is not None:
        nlp_source = nearest_low_point.get("source", "unknown")

    return {
        "total_score": round(total_score, 2),
        "risk_level": risk_level,
        "rainfall_score": rainfall_score,
        "elevation_score": elevation_score,
        "historical_score": historical_score,
        "satellite_score": satellite_score,
        "nearest_low_point": nearest_low_point,
        "nearest_low_point_source": nlp_source,
        "nearby_historical_count": nearby_event_count,
        "decision_source": "rule_based",
    }


def compute_historical_risk_snapshot(event_date, low_points=None, historical_events=None):
    """Reusable: compute risk scores for all low_points using a historical date's rainfall."""
    if low_points is None:
        low_points = get_low_points()
    if historical_events is None:
        historical_events = get_all_historical_events()

    events_on_date = [e for e in historical_events if e["event_date"] == event_date]
    date_rainfall = 0.0
    if events_on_date:
        rainfall_values = [
            ev.get("actual_rainfall_mm", 0.0)
            for ev in events_on_date
            if ev.get("actual_rainfall_mm") is not None
        ]
        if rainfall_values:
            date_rainfall = max(rainfall_values)

    per_point_results = []
    critical = high = moderate = low = 0
    highest = {"street_name": "", "score": -1}

    for p in low_points:
        rs = calculate_risk_score(
            p["latitude"],
            p["longitude"],
            rainfall_mm=date_rainfall,
            forecast_3h_mm=0.0,
            low_points=low_points,
            historical_events=historical_events,
        )
        raw_total = round(rs["total_score"], 2)
        adjusted_risk_level = "low"
        for level, (lo, hi) in RISK_THRESHOLDS.items():
            if lo <= raw_total <= hi:
                adjusted_risk_level = level
                break
        per_point_results.append({
            "latitude": p["latitude"],
            "longitude": p["longitude"],
            "street_name": p.get("street_name", "\u0645\u0648\u0642\u0639 \u0628\u062f\u0648\u0646 \u0627\u0633\u0645"),
            "source": p.get("source", "unknown"),
            "total_score": raw_total,
            "rainfall_score": rs["rainfall_score"],
            "elevation_score": rs["elevation_score"],
            "historical_score": rs["historical_score"],
            "satellite_score": rs["satellite_score"],
            "risk_level": adjusted_risk_level,
            "decision_source": "\u062A\u0642\u064A\u064A\u0645 \u062A\u0627\u0631\u064A\u062E\u064A \u0628\u062F\u0648\u0646 \u0628\u064A\u0627\u0646\u0627\u062A \u0642\u0645\u0631 \u0635\u0646\u0627\u0639\u064A",
        })
        if adjusted_risk_level == "critical":
            critical += 1
        elif adjusted_risk_level == "high":
            high += 1
        elif adjusted_risk_level == "moderate":
            moderate += 1
        else:
            low += 1
        if raw_total > highest["score"]:
            highest = {"street_name": per_point_results[-1]["street_name"], "score": raw_total}

    return {
        "event_date": event_date,
        "date_rainfall": date_rainfall,
        "per_point_results": per_point_results,
        "summary": {
            "critical_count": critical,
            "high_count": high,
            "moderate_count": moderate,
            "low_count": low,
            "highest_risk_point": highest,
        },
    }


def predict_traffic_disruption(risk_level, street_name=None) -> dict:
    disrupted = risk_level in ("high", "critical")
    if disrupted:
        return {
            "disruption_predicted": True,
            "message": (
                f"Potential traffic disruption expected near "
                f"{street_name or 'this location'} due to water "
                f"accumulation risk."
            ),
        }
    return {
        "disruption_predicted": False,
        "message": "No significant traffic disruption expected at this time.",
    }
