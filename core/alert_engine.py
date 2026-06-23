"""Alert engine with null-safe ingestion and ML feedback loop."""

from datetime import datetime

from config.settings import RISK_THRESHOLDS
from core.db import insert_alert, insert_ml_feedback
from core.ml_model import predict_risk_ml
from core.risk_engine import (
    calculate_risk_score,
    find_nearest_low_point,
    count_nearby_historical_events,
    predict_traffic_disruption,
)


def generate_alert_for_location(
    latitude,
    longitude,
    rainfall_mm,
    forecast_3h_mm,
    street_name=None,
    water_detected=False,
    water_coverage_pct=0.0,
    use_ml_enhancement=True,
) -> dict:
    rule_result = calculate_risk_score(
        latitude=latitude,
        longitude=longitude,
        rainfall_mm=rainfall_mm,
        forecast_3h_mm=forecast_3h_mm,
        water_detected=water_detected,
        water_coverage_pct=water_coverage_pct,
    )

    score = rule_result["total_score"]
    risk_level = rule_result["risk_level"]
    decision_source = "rule_based"
    ml_prediction = None

    if use_ml_enhancement:
        ml_result = predict_risk_ml(latitude, longitude, current_rainfall_mm=rainfall_mm)
        ml_prediction = ml_result
        if ml_result.get("ml_available"):
            severity_order = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
            ml_sev = ml_result.get("predicted_severity", "low")
            if severity_order.get(ml_sev, 0) > severity_order.get(risk_level, 0):
                risk_level = ml_sev
            decision_source = "ml_enhanced"

    traffic = predict_traffic_disruption(risk_level, street_name)

    return {
        "latitude": latitude,
        "longitude": longitude,
        "street_name": street_name,
        "total_score": score,
        "risk_level": risk_level,
        "rainfall_mm": rainfall_mm if rainfall_mm is not None else 0.0,
        "forecast_3h_mm": forecast_3h_mm if forecast_3h_mm is not None else 0.0,
        "water_detected": int(water_detected) if water_detected else 0,
        "water_coverage_pct": water_coverage_pct if water_coverage_pct is not None else 0.0,
        "decision_source": decision_source,
        "traffic_disruption_predicted": traffic["disruption_predicted"],
        "traffic_message": traffic["message"],
        "rule_based_score": rule_result,
        "ml_prediction": ml_prediction,
        "elevation_estimate": (rule_result.get("nearest_low_point") or {}).get("elevation_estimate"),
        "distance_to_low_point": (rule_result.get("nearest_low_point") or {}).get("distance_km"),
        "risk_weight": (rule_result.get("nearest_low_point") or {}).get("risk_weight", 0.3),
        "nearby_historical_count": rule_result.get("nearby_historical_count", 0),
    }


def should_trigger_alert(risk_level: str, minimum_level: str = "moderate") -> bool:
    severity_order = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
    return severity_order.get(risk_level, 0) >= severity_order.get(minimum_level, 1)


def process_and_save_alert(
    latitude,
    longitude,
    rainfall_mm,
    forecast_3h_mm,
    street_name=None,
    water_detected=False,
    water_coverage_pct=0.0,
    minimum_alert_level="moderate",
) -> dict:
    alert = generate_alert_for_location(
        latitude=latitude,
        longitude=longitude,
        rainfall_mm=rainfall_mm,
        forecast_3h_mm=forecast_3h_mm,
        street_name=street_name,
        water_detected=water_detected,
        water_coverage_pct=water_coverage_pct,
    )

    if should_trigger_alert(alert["risk_level"], minimum_alert_level):
        alert_id = insert_alert(
            latitude=alert["latitude"],
            longitude=alert["longitude"],
            street_name=alert["street_name"],
            risk_score=int(alert["total_score"]),
            risk_level=alert["risk_level"],
            rainfall_mm=alert["rainfall_mm"],
            forecast_3h_mm=alert["forecast_3h_mm"],
            water_detected=alert["water_detected"],
            water_coverage_pct=alert["water_coverage_pct"],
            elevation_estimate=alert["elevation_estimate"],
            distance_to_low_point=alert["distance_to_low_point"],
            risk_weight=alert["risk_weight"],
            nearby_historical_count=alert["nearby_historical_count"],
            decision_source=alert["decision_source"],
            traffic_disruption_predicted=int(alert["traffic_disruption_predicted"]),
        )
        alert["alert_id"] = alert_id
        alert["saved"] = True
    else:
        alert["alert_id"] = None
        alert["saved"] = False

    _record_ml_feedback(alert)

    return alert


def _record_ml_feedback(alert: dict) -> None:
    try:
        now = datetime.now()
        ml_sev = None
        if alert.get("ml_prediction") and alert["ml_prediction"].get("ml_available"):
            ml_sev = alert["ml_prediction"].get("predicted_severity")
        insert_ml_feedback(
            latitude=alert["latitude"],
            longitude=alert["longitude"],
            rainfall_mm=alert.get("rainfall_mm", 0.0),
            forecast_3h_mm=alert.get("forecast_3h_mm", 0.0),
            water_detected=alert.get("water_detected", 0),
            elevation_estimate=alert.get("elevation_estimate"),
            distance_to_low_point=alert.get("distance_to_low_point"),
            risk_weight=alert.get("risk_weight", 0.3),
            nearby_historical_count=alert.get("nearby_historical_count", 0),
            month=now.month,
            hour=now.hour,
            predicted_severity=ml_sev,
            actual_severity=alert["risk_level"],
        )
    except Exception as e:
        print(f"[FEEDBACK] Error recording ML feedback: {e}")


def process_all_low_points_for_alerts(
    low_points,
    weather_data_by_point,
    minimum_alert_level="moderate",
) -> list[dict]:
    results = []
    for pt in low_points:
        pt_id = pt["id"]
        wd = weather_data_by_point.get(pt_id)
        if wd is None:
            print(f"[ALERTS] No weather data for low point id={pt_id}, skipping.")
            continue
        result = process_and_save_alert(
            latitude=pt["latitude"],
            longitude=pt["longitude"],
            rainfall_mm=wd.get("rainfall_mm", 0.0),
            forecast_3h_mm=wd.get("forecast_3h", 0.0),
            street_name=pt.get("street_name"),
            water_detected=wd.get("water_detected", False),
            water_coverage_pct=wd.get("water_coverage_pct", 0.0),
            minimum_alert_level=minimum_alert_level,
        )
        results.append(result)

    saved = sum(1 for r in results if r.get("saved"))
    unsaved = len(results) - saved
    risk_counts = {}
    for r in results:
        lvl = r["risk_level"]
        risk_counts[lvl] = risk_counts.get(lvl, 0) + 1

    print(
        f"[ALERTS] Generated: {len(results)} total, "
        f"{saved} saved (>= {minimum_alert_level}), {unsaved} below threshold. "
        f"By level: {risk_counts}"
    )
    return results
