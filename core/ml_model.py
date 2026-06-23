"""ML model with feature selection, continuous retraining, and operational feedback loop."""

import os
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import train_test_split

from config.settings import PROCESSED_DATA_DIR
from core.db import (
    get_all_historical_events,
    get_low_points,
    get_ml_training_features,
    get_last_training_run,
    get_total_feedback_count,
    mark_feedback_as_used,
    record_training_run,
)
from core.risk_engine import (
    count_nearby_historical_events,
    find_nearest_low_point,
)

MODEL_PATH = os.path.join(PROCESSED_DATA_DIR, "risk_model.joblib")

FEATURE_COLUMNS = [
    "elevation_estimate",
    "risk_weight",
    "rainfall_mm",
    "forecast_3h_mm",
    "water_detected",
    "nearby_historical_count",
    "month",
    "hour",
    "has_rainfall_data",
]

SEVERITY_MAP = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
LABEL_COL = "label"


def _build_feature_dataframe(labeled_rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(labeled_rows)
    if df.empty:
        return df
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = 0.0
    if LABEL_COL not in df.columns:
        df[LABEL_COL] = 0
    df[FEATURE_COLUMNS] = df[FEATURE_COLUMNS].fillna(0.0)
    df[LABEL_COL] = df[LABEL_COL].fillna(0).astype(int)
    return df


def build_training_dataset() -> pd.DataFrame:
    labeled_rows = get_ml_training_features()
    df = _build_feature_dataframe(labeled_rows)
    if df.empty:
        print("[ML] No labeled data found. Falling back to original historical+low-point method.")
        return _legacy_build_training_dataset()

    hist_count = sum(1 for r in labeled_rows if r.get("source") == "historical_event")
    op_count = sum(1 for r in labeled_rows if r.get("source", "").startswith("operational"))
    print(f"[ML] Training dataset: {len(df)} rows ({hist_count} historical, {op_count} operational)")

    n_low = len(df[df[LABEL_COL] == 0])
    n_pos = len(df[df[LABEL_COL] > 0])
    if n_pos > n_low * 3:
        neg_needed = n_pos - n_low
        low_pts = get_low_points()
        rng = np.random.default_rng(42)
        neg_rows = []
        for p in low_pts:
            if len(neg_rows) >= neg_needed:
                break
            if rng.random() > 0.3:
                continue
            key = (round(p["latitude"], 5), round(p["longitude"], 5))
            already_in = any(
                (round(r.get("latitude", 0), 5), round(r.get("longitude", 0), 5)) == key
                for r in labeled_rows
            )
            if already_in:
                continue
            neg_rows.append({
                "elevation_estimate": p.get("elevation_estimate", 0) or 0,
                "risk_weight": p.get("risk_weight", 0.3) or 0.3,
                "rainfall_mm": 0.0,
                "forecast_3h_mm": 0.0,
                "water_detected": 0,
                "nearby_historical_count": 0,
                "month": datetime.now().month,
                "hour": datetime.now().hour,
                "has_rainfall_data": 0,
                LABEL_COL: 0,
                "source": "negative_augment",
            })
        if neg_rows:
            neg_df = _build_feature_dataframe(neg_rows)
            df = pd.concat([df, neg_df], ignore_index=True)
            print(f"[ML] Added {len(neg_rows)} augmented negative samples for balance.")

    print(f"[ML] Final label distribution:\n{df[LABEL_COL].value_counts().sort_index()}")
    try:
        corr = df[FEATURE_COLUMNS].corrwith(df[LABEL_COL]).sort_values(ascending=False)
        print(f"[ML] Feature correlation with label:\n{corr.fillna(0)}")
    except Exception:
        pass
    return df


def _legacy_build_training_dataset() -> pd.DataFrame:
    print("[ML] Using legacy dataset builder (historical_events + synthetic).")
    historical_events = get_all_historical_events()
    low_points = get_low_points()
    real_rows = []
    for ev in historical_events:
        nearest = find_nearest_low_point(ev["latitude"], ev["longitude"], low_points)
        if nearest is None:
            continue
        nearby_count = count_nearby_historical_events(
            ev["latitude"], ev["longitude"], historical_events
        )
        month = int(ev["event_date"].split("-")[1]) if "-" in ev.get("event_date", "") else 1
        actual_rain = ev.get("actual_rainfall_mm") or 0.0
        real_rows.append({
            "elevation_estimate": nearest.get("elevation_estimate", 0) or 0,
            "risk_weight": nearest.get("risk_weight", 0.3) or 0.3,
            "rainfall_mm": actual_rain,
            "forecast_3h_mm": 0.0,
            "water_detected": 0,
            "nearby_historical_count": nearby_count,
            "month": month,
            "hour": 12,
            "has_rainfall_data": 1 if actual_rain > 0 else 0,
            LABEL_COL: SEVERITY_MAP.get(ev["severity"], 0),
        })
    n_synthetic = max(1, len(real_rows) // 2)
    from config.settings import HAIL_CITY_CENTER, HAIL_CITY_RADIUS_KM
    center_lat, center_lon = HAIL_CITY_CENTER
    radius_deg = HAIL_CITY_RADIUS_KM / 111.0
    rng = np.random.default_rng(42)
    synthetic_rows = []
    attempts = 0
    while len(synthetic_rows) < n_synthetic and attempts < n_synthetic * 10:
        lat = center_lat + rng.uniform(-radius_deg, radius_deg)
        lon = center_lon + rng.uniform(-radius_deg, radius_deg)
        near_any_event = False
        for ev in historical_events:
            from core.risk_engine import calculate_distance_km
            if calculate_distance_km(lat, lon, ev["latitude"], ev["longitude"]) < 5:
                near_any_event = True
                break
        if near_any_event:
            attempts += 1
            continue
        nearest = find_nearest_low_point(lat, lon, low_points)
        if nearest and nearest.get("risk_weight", 0) > 0.85:
            attempts += 1
            continue
        month = int(rng.integers(1, 13))
        synthetic_rows.append({
            "elevation_estimate": nearest["elevation_estimate"] if nearest else 1000,
            "risk_weight": nearest.get("risk_weight", 0.3) if nearest else 0.3,
            "rainfall_mm": 0.0,
            "forecast_3h_mm": 0.0,
            "water_detected": 0,
            "nearby_historical_count": 0,
            "month": month,
            "hour": 12,
            "has_rainfall_data": 0,
            LABEL_COL: 0,
        })
    df = pd.DataFrame(real_rows + synthetic_rows)
    print(f"[ML] Legacy dataset: {len(real_rows)} real, {len(synthetic_rows)} synthetic")
    return df


def _evaluate_and_persist(model, feature_importance, df, X_train, y_train, X_test, y_test):
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    report = classification_report(y_test, y_pred, zero_division=0, output_dict=False)
    joblib.dump(model, MODEL_PATH)

    if "source" in df.columns:
        src = df["source"].astype(str)
        n_hist = int((src == "historical_event").sum())
        n_op = int((src.str.startswith("operational")).sum())
    else:
        n_hist = n_op = 0
    run_id, version = record_training_run(
        n_train=len(X_train), n_test=len(X_test), accuracy=accuracy,
        feature_importance=str(feature_importance),
        n_historical_labels=n_hist, n_operational_labels=n_op,
    )

    print(f"[ML] Model v{version} trained (id={run_id}): accuracy={accuracy:.3f}, "
          f"train={len(X_train)}, test={len(X_test)}, historical={n_hist}, op-feedback={n_op}")
    print(f"[ML] Feature importance: {feature_importance}")
    if report:
        print(f"[ML] Classification report:\n{report}")

    return {
        "accuracy": accuracy,
        "classification_report": report,
        "n_train_samples": len(X_train),
        "n_test_samples": len(X_test),
        "feature_importance": feature_importance,
        "model_version": version,
        "n_historical_labels": n_hist,
        "n_operational_labels": n_op,
    }


def train_risk_model() -> dict:
    df = build_training_dataset()
    if len(df) < 10:
        print("[ML] Insufficient data (<10 rows). Skipping training.")
        return {"accuracy": None, "error": "insufficient_data"}

    X = df[FEATURE_COLUMNS]
    y = df[LABEL_COL]
    class_counts = y.value_counts()
    can_stratify = all(class_counts >= 2)

    if len(df) >= 20 and can_stratify:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
    else:
        print("[ML] Limited data — training on all available (no held-out test).")
        X_train, y_train = X, y
        X_test, y_test = X.iloc[:1] if len(X) > 1 else X, y.iloc[:1] if len(y) > 1 else y

    model = RandomForestClassifier(
        n_estimators=120, max_depth=8, random_state=42,
        class_weight="balanced", min_samples_leaf=2,
    )
    model.fit(X_train, y_train)
    importance = dict(sorted(
        zip(FEATURE_COLUMNS, model.feature_importances_),
        key=lambda x: x[1], reverse=True,
    ))

    if X_test is not None and len(X_test) > 0 and y_test is not None and len(y_test) > 0:
        result = _evaluate_and_persist(model, importance, df, X_train, y_train, X_test, y_test)
        mark_feedback_as_used(limit=500)
        print("[ML] Marked up to 500 feedback records as used_for_training.")
        return result

    joblib.dump(model, MODEL_PATH)
    return {
        "accuracy": None,
        "n_train_samples": len(X_train),
        "feature_importance": importance,
        "note": "trained on full dataset without test split",
    }


def retrain_if_needed(min_new_records: int = 30) -> dict | None:
    last_run = get_last_training_run()
    pending = get_total_feedback_count()
    print(f"[ML] Retrain check: {pending} new feedback records pending (threshold={min_new_records}).")

    if last_run is None:
        print("[ML] No prior model found. Running initial training.")
        return train_risk_model()

    if pending >= min_new_records:
        print(f"[ML] Sufficient new data ({pending} >= {min_new_records}). Triggering retrain.")
        return train_risk_model()

    print(f"[ML] Only {pending} new records; {min_new_records - pending} more needed. Skipping retrain.")
    return None


def load_risk_model():
    if os.path.exists(MODEL_PATH):
        return joblib.load(MODEL_PATH)
    print(f"[ML] No trained model at {MODEL_PATH}. Running initial training.")
    train_risk_model()
    if os.path.exists(MODEL_PATH):
        return joblib.load(MODEL_PATH)
    print("[ML] Training returned no model; falling back to rule-based.")
    return None


def predict_risk_ml(
    latitude,
    longitude,
    current_rainfall_mm=0.0,
    low_points=None,
    historical_events=None,
) -> dict:
    if low_points is None:
        low_points = get_low_points()
    if historical_events is None:
        historical_events = get_all_historical_events()

    model = load_risk_model()
    if model is None:
        return {
            "success": False,
            "ml_available": False,
            "predicted_severity": None,
            "confidence": None,
            "error": "No trained model available",
        }

    try:
        nearest = find_nearest_low_point(latitude, longitude, low_points)
        nearby_count = count_nearby_historical_events(
            latitude, longitude, historical_events
        )
        now = datetime.now()
        features = pd.DataFrame([{
            "elevation_estimate": nearest["elevation_estimate"] if nearest else 0,
            "risk_weight": nearest.get("risk_weight", 0.3) if nearest else 0.3,
            "rainfall_mm": current_rainfall_mm,
            "forecast_3h_mm": 0.0,
            "water_detected": 0,
            "nearby_historical_count": nearby_count,
            "month": now.month,
            "hour": now.hour,
            "has_rainfall_data": 1 if current_rainfall_mm > 0 else 0,
        }])

        pred = model.predict(features)[0]
        proba = model.predict_proba(features)[0]
        severity = SEVERITY_MAP.get(int(pred), "unknown")
        confidence = float(max(proba))

        return {
            "success": True,
            "ml_available": True,
            "predicted_severity": severity,
            "confidence": round(confidence, 3),
            "error": None,
            "decision_source": "ml_enhanced",
            "interpretation": "pattern_confirmation",
            "_features": {
                "elevation_estimate": features.iloc[0]["elevation_estimate"],
                "risk_weight": features.iloc[0]["risk_weight"],
                "rainfall_mm": features.iloc[0]["rainfall_mm"],
                "forecast_3h_mm": features.iloc[0]["forecast_3h_mm"],
                "water_detected": features.iloc[0]["water_detected"],
                "nearby_historical_count": features.iloc[0]["nearby_historical_count"],
                "month": features.iloc[0]["month"],
                "hour": features.iloc[0]["hour"],
                "has_rainfall_data": features.iloc[0]["has_rainfall_data"],
            },
        }
    except Exception as e:
        return {
            "success": False,
            "ml_available": False,
            "predicted_severity": None,
            "confidence": None,
            "error": str(e),
        }
