"""One-time script to load confirmed city-wide flood event dates for Hail City
into the historical_events table, associating each date with the top 10
highest-risk low points."""

import sys
import os

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.db import insert_historical_event, get_low_points, init_db

CONFIRMED_FLOOD_DATES = [
    "2025-03-07",
    "2025-04-02",
    "2025-04-04",
    "2025-04-06",
    "2025-04-07",
    "2025-04-20",
    "2025-04-21",
    "2025-05-01",
    "2026-04-04",
    "2026-04-05",
    "2026-04-16",
    "2026-04-18",
    "2026-04-19",
    "2026-04-20",
    "2026-04-22",
    "2026-04-25",
    "2026-04-26",
    "2026-05-06",
    "2026-05-08",
    "2026-05-24",
]


def get_top_risk_low_points(low_points: list[dict], top_n: int = 10) -> list[dict]:
    sorted_points = sorted(low_points, key=lambda p: p["risk_weight"], reverse=True)
    return sorted_points[:top_n]


def main():
    init_db()

    all_low_points = get_low_points()
    if not all_low_points:
        print("Error: No low points found in the database.")
        print("Please run scripts/load_low_points.py first.")
        return

    top_points = get_top_risk_low_points(all_low_points)

    total_inserted = 0
    for date in CONFIRMED_FLOOD_DATES:
        for point in top_points:
            if point["risk_weight"] >= 0.85:
                severity = "critical"
            elif point["risk_weight"] >= 0.65:
                severity = "high"
            elif point["risk_weight"] >= 0.45:
                severity = "moderate"
            else:
                severity = "low"

            insert_historical_event(
                event_date=date,
                latitude=point["latitude"],
                longitude=point["longitude"],
                severity=severity,
                description=(
                    "City-wide flood event confirmed by client/meteorological reports. "
                    f"Associated with low-elevation point: {point['street_name']}"
                ),
                photo_filename=None,
                nearest_street_name=point["street_name"],
                source="client_confirmed_citywide",
            )
            total_inserted += 1

    print(f"Total historical events created: {total_inserted}")
    print(f"Unique dates: {len(CONFIRMED_FLOOD_DATES)}")
    print(f"Unique locations used: {len(top_points)}")


if __name__ == "__main__":
    main()
