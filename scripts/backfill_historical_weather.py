"""Backfill actual historical rainfall data for all confirmed flood events."""

import os
import sys
import time

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config.settings import PROCESSED_DATA_DIR
from core.db import get_all_historical_events, get_connection
from core.weather_client import get_historical_rainfall


def add_actual_rainfall_column() -> None:
    conn = get_connection()
    try:
        cur = conn.execute("PRAGMA table_info(historical_events)")
        cols = [row["name"] for row in cur.fetchall()]
        if "actual_rainfall_mm" not in cols:
            conn.execute(
                "ALTER TABLE historical_events ADD COLUMN actual_rainfall_mm REAL"
            )
            conn.commit()
            print("Added column 'actual_rainfall_mm' to historical_events.")
        else:
            print("Column 'actual_rainfall_mm' already exists.")
    finally:
        conn.close()


def backfill_rainfall_for_events() -> dict:
    add_actual_rainfall_column()

    events = get_all_historical_events()
    print(f"Total historical events to process: {len(events)}")

    cache = {}
    for ev in events:
        key = (
            f"{ev['event_date']}_"
            f"{round(ev['latitude'], 4)}_{round(ev['longitude'], 4)}"
        )
        if key not in cache:
            cache[key] = {
                "event_date": ev["event_date"],
                "latitude": ev["latitude"],
                "longitude": ev["longitude"],
            }

    print(
        f"Unique (date, lat, lon) combinations: {len(cache)}. "
        f"Fetching from Open-Meteo archive..."
    )

    cache_results = {}
    for i, (key, info) in enumerate(cache.items()):
        result = get_historical_rainfall(
            info["latitude"], info["longitude"], info["event_date"]
        )
        cache_results[key] = result
        print(
            f"[{i + 1}/{len(cache)}] {info['event_date']} "
            f"({info['latitude']:.4f}, {info['longitude']:.4f}): "
            f"{result['precipitation_sum_mm']}mm"
        )
        time.sleep(0.5)

    conn = get_connection()
    updated = 0
    zero_count = 0
    positive_count = 0
    try:
        for ev in events:
            key = (
                f"{ev['event_date']}_"
                f"{round(ev['latitude'], 4)}_{round(ev['longitude'], 4)}"
            )
            result = cache_results.get(key, {})
            val = result.get("precipitation_sum_mm", 0.0)
            conn.execute(
                "UPDATE historical_events SET actual_rainfall_mm = ? WHERE id = ?",
                (val, ev["id"]),
            )
            updated += 1
            if val == 0.0:
                zero_count += 1
            else:
                positive_count += 1
        conn.commit()
    finally:
        conn.close()

    return {
        "total_events_updated": updated,
        "unique_api_calls_made": len(cache),
        "events_with_zero_rainfall": zero_count,
        "events_with_rainfall_data": positive_count,
    }


def main():
    summary = backfill_rainfall_for_events()

    print(f"\n{'=' * 60}")
    print(f"Total events updated: {summary['total_events_updated']}")
    print(f"Unique API calls made: {summary['unique_api_calls_made']}")
    print(f"Events with 0mm rainfall: {summary['events_with_zero_rainfall']}")
    print(f"Events with rainfall data: {summary['events_with_rainfall_data']}")

    if summary["events_with_zero_rainfall"] > summary["total_events_updated"] * 0.3:
        print(
            "\nWARNING: Many confirmed flood dates show 0mm in Open-Meteo's "
            "historical archive at these exact coordinates. This can happen "
            "because: (1) archive data has gaps for this region, (2) the rain "
            "occurred in a different sub-area of the point's surroundings than "
            "the exact coordinate, or (3) flooding resulted from accumulated "
            "runoff rather than same-day localized rain. Do not silently discard "
            "this — flag it for review against client's original reports."
        )


if __name__ == "__main__":
    main()
