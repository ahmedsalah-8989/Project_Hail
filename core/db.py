"""Database module for SQLite operations with null-safe ingestion and ML feature extraction."""

import sqlite3
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config.settings import DB_PATH


def get_connection() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _coalesce(value, default=0.0):
    """Replace None/NaN with a safe default — never blank/null enters the DB."""
    if value is None:
        return default
    if isinstance(value, float) and (value != value):  # NaN check
        return default
    return value


def _safe_str(value, default="\u2014"):
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return default
    return value


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS historical_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_date TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                severity TEXT NOT NULL,
                description TEXT,
                photo_filename TEXT,
                nearest_street_name TEXT,
                actual_rainfall_mm REAL DEFAULT 0.0,
                source TEXT NOT NULL DEFAULT 'client_confirmed',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                street_name TEXT,
                risk_score INTEGER NOT NULL,
                risk_level TEXT NOT NULL,
                rainfall_mm REAL DEFAULT 0.0,
                forecast_3h_mm REAL DEFAULT 0.0,
                water_detected INTEGER NOT NULL DEFAULT 0,
                water_coverage_pct REAL DEFAULT 0.0,
                elevation_estimate REAL,
                distance_to_low_point REAL,
                risk_weight REAL,
                nearby_historical_count INTEGER DEFAULT 0,
                decision_source TEXT NOT NULL,
                traffic_disruption_predicted INTEGER NOT NULL DEFAULT 0,
                resolved INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS weather_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reading_timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                rainfall_mm REAL DEFAULT 0.0,
                rainfall_forecast_1h REAL DEFAULT 0.0,
                rainfall_forecast_3h REAL DEFAULT 0.0,
                source TEXT NOT NULL DEFAULT 'open_meteo'
            );

            CREATE TABLE IF NOT EXISTS low_points (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                street_name TEXT,
                elevation_estimate REAL,
                risk_weight REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT 'client_verified'
            );

            CREATE TABLE IF NOT EXISTS model_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trained_at TEXT NOT NULL DEFAULT (datetime('now')),
                n_train_samples INTEGER NOT NULL,
                n_test_samples INTEGER NOT NULL,
                accuracy REAL NOT NULL,
                feature_importance TEXT,
                n_historical_labels INTEGER DEFAULT 0,
                n_operational_labels INTEGER DEFAULT 0,
                model_version INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS ml_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                rainfall_mm REAL DEFAULT 0.0,
                forecast_3h_mm REAL DEFAULT 0.0,
                water_detected INTEGER DEFAULT 0,
                elevation_estimate REAL,
                distance_to_low_point REAL,
                risk_weight REAL,
                nearby_historical_count INTEGER DEFAULT 0,
                month INTEGER,
                hour INTEGER,
                predicted_severity TEXT,
                actual_severity TEXT,
                used_for_training INTEGER DEFAULT 0
            );
        """)
        conn.commit()
    finally:
        conn.close()


def insert_historical_event(
    event_date, latitude, longitude, severity,
    description, photo_filename, nearest_street_name,
    actual_rainfall_mm=None, source='client_confirmed'
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO historical_events
               (event_date, latitude, longitude, severity, description,
                photo_filename, nearest_street_name, actual_rainfall_mm, source)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _safe_str(event_date),
                _coalesce(latitude, 0.0),
                _coalesce(longitude, 0.0),
                _safe_str(severity, "moderate"),
                _safe_str(description, ""),
                _safe_str(photo_filename, ""),
                _safe_str(nearest_street_name, ""),
                _coalesce(actual_rainfall_mm, 0.0),
                _safe_str(source, "client_confirmed"),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_alert(
    latitude, longitude, street_name, risk_score, risk_level,
    rainfall_mm, water_detected, decision_source,
    traffic_disruption_predicted,
    forecast_3h_mm=0.0, water_coverage_pct=0.0,
    elevation_estimate=None, distance_to_low_point=None,
    risk_weight=None, nearby_historical_count=0,
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO alerts
               (latitude, longitude, street_name, risk_score, risk_level,
                rainfall_mm, forecast_3h_mm, water_detected, water_coverage_pct,
                elevation_estimate, distance_to_low_point, risk_weight,
                nearby_historical_count, decision_source,
                traffic_disruption_predicted)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _coalesce(latitude, 0.0),
                _coalesce(longitude, 0.0),
                _safe_str(street_name),
                int(_coalesce(risk_score, 0)),
                _safe_str(risk_level, "low"),
                _coalesce(rainfall_mm, 0.0),
                _coalesce(forecast_3h_mm, 0.0),
                int(_coalesce(water_detected, 0)),
                _coalesce(water_coverage_pct, 0.0),
                _coalesce(elevation_estimate),
                _coalesce(distance_to_low_point),
                _coalesce(risk_weight, 0.3),
                int(_coalesce(nearby_historical_count, 0)),
                _safe_str(decision_source, "rule_based"),
                int(_coalesce(traffic_disruption_predicted, 0)),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_weather_reading(
    latitude, longitude, rainfall_mm,
    rainfall_forecast_1h, rainfall_forecast_3h,
    source='open_meteo'
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO weather_readings
               (latitude, longitude, rainfall_mm, rainfall_forecast_1h,
                rainfall_forecast_3h, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                _coalesce(latitude, 0.0),
                _coalesce(longitude, 0.0),
                _coalesce(rainfall_mm, 0.0),
                _coalesce(rainfall_forecast_1h, 0.0),
                _coalesce(rainfall_forecast_3h, 0.0),
                _safe_str(source, "open_meteo"),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_low_point(
    latitude, longitude, street_name,
    elevation_estimate, risk_weight=1.0,
    source="client_verified"
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO low_points
               (latitude, longitude, street_name, elevation_estimate, risk_weight, source)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                _coalesce(latitude, 0.0),
                _coalesce(longitude, 0.0),
                _safe_str(street_name),
                _coalesce(elevation_estimate, 0.0),
                _coalesce(risk_weight, 1.0),
                _safe_str(source, "client_verified"),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def insert_ml_feedback(
    latitude, longitude, rainfall_mm, forecast_3h_mm,
    water_detected, elevation_estimate, distance_to_low_point,
    risk_weight, nearby_historical_count, month, hour,
    predicted_severity, actual_severity,
) -> int:
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO ml_feedback
               (latitude, longitude, rainfall_mm, forecast_3h_mm,
                water_detected, elevation_estimate, distance_to_low_point,
                risk_weight, nearby_historical_count, month, hour,
                predicted_severity, actual_severity)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                _coalesce(latitude),
                _coalesce(longitude),
                _coalesce(rainfall_mm, 0.0),
                _coalesce(forecast_3h_mm, 0.0),
                int(_coalesce(water_detected, 0)),
                _coalesce(elevation_estimate),
                _coalesce(distance_to_low_point),
                _coalesce(risk_weight, 0.3),
                int(_coalesce(nearby_historical_count, 0)),
                int(_coalesce(month, 1)),
                int(_coalesce(hour, 12)),
                _safe_str(predicted_severity),
                _safe_str(actual_severity),
            ),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def record_training_run(n_train, n_test, accuracy, feature_importance,
                        n_historical_labels, n_operational_labels):
    conn = get_connection()
    try:
        last = conn.execute(
            "SELECT COALESCE(MAX(model_version), 0) AS v FROM model_metrics"
        ).fetchone()
        next_ver = (last["v"] if last else 0) + 1
        cur = conn.execute(
            """INSERT INTO model_metrics
               (n_train_samples, n_test_samples, accuracy, feature_importance,
                n_historical_labels, n_operational_labels, model_version)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                int(n_train), int(n_test), float(accuracy),
                str(feature_importance),
                int(n_historical_labels), int(n_operational_labels),
                next_ver,
            ),
        )
        conn.commit()
        return cur.lastrowid, next_ver
    finally:
        conn.close()


def get_last_training_run() -> dict | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM model_metrics ORDER BY trained_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_total_feedback_count() -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM ml_feedback WHERE used_for_training = 0"
        ).fetchone()
        return row["cnt"] if row else 0
    finally:
        conn.close()


def mark_feedback_as_used(limit=500):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE ml_feedback SET used_for_training = 1 "
            "WHERE used_for_training = 0 AND id IN "
            "(SELECT id FROM ml_feedback WHERE used_for_training = 0 LIMIT ?)",
            (limit,),
        )
        conn.commit()
    finally:
        conn.close()


def get_ml_training_features() -> list[dict]:
    """Extract feature vectors from all tables for ML training.

    Sources:
      a) historical_events (client-confirmed incidents) → labels 0-3
      b) ml_feedback (operational alerts with actual outcomes) → labels
      c) low_points with no rain → negative samples (label=0)
    """
    conn = get_connection()
    results = []
    try:
        severity_map = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
        low_pts = conn.execute("SELECT * FROM low_points").fetchall()
        pt_index = {}
        for p in low_pts:
            pt_index[(round(p["latitude"], 5), round(p["longitude"], 5))] = dict(p)

        # Source 1: historical_events
        events = conn.execute(
            "SELECT * FROM historical_events"
        ).fetchall()
        for ev in events:
            d = dict(ev)
            dt = _safe_str(d.get("event_date", "2025-01-01"))
            month = int(dt.split("-")[1]) if "-" in dt else 1
            key = (round(d["latitude"], 5), round(d["longitude"], 5))
            lp = pt_index.get(key, {})
            results.append({
                "elevation_estimate": _coalesce(lp.get("elevation_estimate"), 0),
                "risk_weight": _coalesce(lp.get("risk_weight"), 0.3),
                "rainfall_mm": _coalesce(d.get("actual_rainfall_mm"), 0.0),
                "forecast_3h_mm": 0.0,
                "water_detected": 0,
                "nearby_historical_count": 0,
                "month": month,
                "hour": 12,
                "has_rainfall_data": 1 if _coalesce(d.get("actual_rainfall_mm"), 0) > 0 else 0,
                "label": severity_map.get(d.get("severity", "low"), 0),
                "source": "historical_event",
            })

        # Source 2: ml_feedback (operational)
        fb_rows = conn.execute(
            "SELECT * FROM ml_feedback WHERE used_for_training = 0"
        ).fetchall()
        for fb in fb_rows:
            d = dict(fb)
            results.append({
                "elevation_estimate": _coalesce(d.get("elevation_estimate"), 0),
                "risk_weight": _coalesce(d.get("risk_weight"), 0.3),
                "rainfall_mm": _coalesce(d.get("rainfall_mm"), 0.0),
                "forecast_3h_mm": _coalesce(d.get("forecast_3h_mm"), 0.0),
                "water_detected": int(_coalesce(d.get("water_detected"), 0)),
                "nearby_historical_count": int(_coalesce(d.get("nearby_historical_count"), 0)),
                "month": int(_coalesce(d.get("month"), 1)),
                "hour": int(_coalesce(d.get("hour"), 12)),
                "has_rainfall_data": 1 if _coalesce(d.get("rainfall_mm"), 0) > 0 else 0,
                "label": severity_map.get(d.get("actual_severity", "low"), 0),
                "source": "operational_feedback",
            })

        # Source 3: alerts that were saved (already moderate+) as feedback
        alerts = conn.execute(
            "SELECT * FROM alerts WHERE resolved = 0"
        ).fetchall()
        for a in alerts:
            d = dict(a)
            dt = _safe_str(d.get("alert_timestamp", ""))
            month = 1
            hour = 12
            if dt and len(dt) >= 16:
                try:
                    month = int(dt[5:7])
                    hour = int(dt[11:13])
                except (ValueError, IndexError):
                    pass
            key = (round(d["latitude"], 5), round(d["longitude"], 5))
            lp = pt_index.get(key, {})
            results.append({
                "elevation_estimate": _coalesce(d.get("elevation_estimate") or lp.get("elevation_estimate"), 0),
                "risk_weight": _coalesce(d.get("risk_weight") or lp.get("risk_weight"), 0.3),
                "rainfall_mm": _coalesce(d.get("rainfall_mm"), 0.0),
                "forecast_3h_mm": _coalesce(d.get("forecast_3h_mm"), 0.0),
                "water_detected": int(_coalesce(d.get("water_detected"), 0)),
                "nearby_historical_count": int(_coalesce(d.get("nearby_historical_count"), 0)),
                "month": month,
                "hour": hour,
                "has_rainfall_data": 1 if _coalesce(d.get("rainfall_mm"), 0) > 0 else 0,
                "label": severity_map.get(d.get("risk_level", "low"), 0),
                "source": "operational_alert",
            })

    finally:
        conn.close()
    return results


def get_all_historical_events() -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM historical_events ORDER BY event_date DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_alerts(start_date=None, end_date=None, risk_level=None) -> list[dict]:
    conditions = []
    params = []
    if start_date is not None:
        conditions.append("alert_timestamp >= ?")
        params.append(start_date)
    if end_date is not None:
        conditions.append("alert_timestamp <= ?")
        params.append(end_date)
    if risk_level is not None:
        conditions.append("risk_level = ?")
        params.append(risk_level)
    where_clause = ""
    if conditions:
        where_clause = " WHERE " + " AND ".join(conditions)
    sql = "SELECT * FROM alerts" + where_clause + " ORDER BY alert_timestamp DESC"
    conn = get_connection()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_low_points(source: str = None) -> list[dict]:
    conn = get_connection()
    try:
        if source is not None:
            rows = conn.execute("SELECT * FROM low_points WHERE source = ?", (source,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM low_points").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_alert_count_since(timestamp: str) -> int:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM alerts WHERE alert_timestamp > ?",
            (timestamp,),
        ).fetchone()
        return row["cnt"]
    finally:
        conn.close()


def get_active_alerts_capped(limit: int = 30) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE resolved = 0 ORDER BY alert_timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_alerts_by_date(target_date: str) -> list[dict]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE alert_timestamp LIKE ? ORDER BY alert_timestamp DESC",
            (target_date + "%",)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_latest_weather_by_point() -> dict:
    conn = get_connection()
    try:
        latest = conn.execute("""
            SELECT wr.* FROM weather_readings wr
            INNER JOIN (
                SELECT latitude, longitude, MAX(reading_timestamp) AS max_ts
                FROM weather_readings
                GROUP BY latitude, longitude
            ) lr ON wr.latitude = lr.latitude
                 AND wr.longitude = lr.longitude
                 AND wr.reading_timestamp = lr.max_ts
        """).fetchall()
        pts = conn.execute(
            "SELECT id, latitude, longitude FROM low_points"
        ).fetchall()
        coord2id = {}
        for p in pts:
            coord2id[(round(p["latitude"], 5), round(p["longitude"], 5))] = p["id"]
        result = {}
        for r in latest:
            pt_id = coord2id.get((round(r["latitude"], 5), round(r["longitude"], 5)))
            if pt_id is not None:
                result[pt_id] = {
                    "rainfall_mm": _coalesce(r["rainfall_mm"], 0.0),
                    "forecast_1h": _coalesce(r["rainfall_forecast_1h"], 0.0),
                    "forecast_3h": _coalesce(r["rainfall_forecast_3h"], 0.0),
                }
        return result
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_PATH)
