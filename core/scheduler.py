"""Background scheduler for automated 30-minute data ingestion and risk assessment."""

import threading
import time
from datetime import datetime

from core.db import get_low_points
from core.weather_client import (
    get_weather_for_all_low_points,
    save_weather_readings_to_db,
)
from core.alert_engine import process_all_low_points_for_alerts
from core.satellite_client import fetch_latest_sentinel2_image
from core.water_detection import analyze_satellite_image_for_water

LAST_RUN_TIMESTAMP = None
_SCHEDULER_THREAD = None


def run_automatic_update_cycle() -> dict:
    timestamp = datetime.now().isoformat()
    print(f"[SCHEDULER] {timestamp} Starting automated 30-minute data ingestion and risk assessment cycle...")

    try:
        low_points = get_low_points()
        if not low_points:
            print("[SCHEDULER] Warning: No low points found in database. Skipping cycle.")
            return {
                "timestamp": timestamp,
                "low_points_monitored": 0,
                "execution_status": "failed",
            }

        weather_data = get_weather_for_all_low_points()
        saved_count = save_weather_readings_to_db(weather_data)
        print(f"[SCHEDULER] Saved {saved_count} weather readings to database.")

        weather_lookup = {w["id"]: w for w in weather_data}

        satellite_ok = 0
        satellite_fallback = 0
        for pt in low_points:
            w_entry = weather_lookup.get(pt["id"])
            if w_entry is None:
                continue
            w_entry.setdefault("water_detected", False)
            w_entry.setdefault("water_coverage_pct", 0.0)
            try:
                bbox = (
                    pt["longitude"] - 0.003,
                    pt["latitude"] - 0.003,
                    pt["longitude"] + 0.003,
                    pt["latitude"] + 0.003,
                )
                sat_result = fetch_latest_sentinel2_image(bbox)
                if sat_result.get("success") and sat_result.get("image_data") is not None:
                    water = analyze_satellite_image_for_water(sat_result["image_data"])
                    if water.get("success"):
                        w_entry["water_detected"] = water["water_detected"]
                        w_entry["water_coverage_pct"] = water["water_coverage_pct"]
                        satellite_ok += 1
                        continue
            except Exception:
                pass
            satellite_fallback += 1

        print(
            f"[SCHEDULER] Satellite water detection: {satellite_ok} ok, "
            f"{satellite_fallback} fallback to no-satellite"
        )

        results = process_all_low_points_for_alerts(low_points, weather_lookup)
        saved_alerts = sum(1 for r in results if r.get("saved"))
        print(f"[SCHEDULER] Generated {saved_alerts} new alerts from {len(results)} locations.")

        # Continuous ML retraining check — trigger after every cycle
        try:
            from core.ml_model import retrain_if_needed
            retrain_result = retrain_if_needed(min_new_records=30)
            if retrain_result is not None:
                acc = retrain_result.get("accuracy", "N/A")
                print(f"[SCHEDULER] Model retrained. Accuracy={acc}")
        except Exception as e:
            print(f"[SCHEDULER] ML retrain check failed (non-fatal): {e}")

        global LAST_RUN_TIMESTAMP
        LAST_RUN_TIMESTAMP = timestamp

        return {
            "timestamp": timestamp,
            "low_points_monitored": len(low_points),
            "execution_status": "success",
        }
    except Exception as e:
        print(f"[SCHEDULER] Error during update cycle: {e}")
        return {
            "timestamp": timestamp,
            "low_points_monitored": 0,
            "execution_status": "failed",
        }


def start_scheduler_thread(interval_seconds: int = 1800) -> None:
    global _SCHEDULER_THREAD

    if _SCHEDULER_THREAD is not None and _SCHEDULER_THREAD.is_alive():
        print("[SCHEDULER] Background thread already running. Skipping duplicate spawn.")
        return

    def _loop():
        while True:
            run_automatic_update_cycle()
            time.sleep(interval_seconds)

    _SCHEDULER_THREAD = threading.Thread(target=_loop, daemon=True, name="hail-scheduler")
    _SCHEDULER_THREAD.start()
    print(f"[SCHEDULER] Daemon thread started (interval={interval_seconds}s).")


if __name__ == "__main__":
    result = run_automatic_update_cycle()
    print(f"[SCHEDULER] Direct-run telemetry: {result}")
