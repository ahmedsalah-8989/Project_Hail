"""One-time script to load known low-elevation points in Hail City into the database."""

import sys
import os

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.db import init_db, insert_low_point

CLIENT_LOW_POINTS = [
    {"name": "شارع الملك عبدالله", "elevation_m": 985, "latitude": 27.52500, "longitude": 41.69500},
    {"name": "حي الجامعيين", "elevation_m": 995, "latitude": 27.54000, "longitude": 41.68000},
    {"name": "حي المطار", "elevation_m": 1005, "latitude": 27.49000, "longitude": 41.72000},
    {"name": "طريق الملك عبدالعزيز", "elevation_m": 975, "latitude": 27.51000, "longitude": 41.70000},
    {"name": "حي المنتزه", "elevation_m": 990, "latitude": 27.53000, "longitude": 41.68500},
    {"name": "حي النقرة", "elevation_m": 982, "latitude": 27.48000, "longitude": 41.67000},
    {"name": "نفق الساعة", "elevation_m": 987, "latitude": 27.49582, "longitude": 41.69785},
    {"name": "تقاطع stc", "elevation_m": 986, "latitude": 27.48971, "longitude": 41.69670},
    {"name": "دوار وقت اللياقة", "elevation_m": 999, "latitude": 27.46583, "longitude": 41.66486},
    {"name": "النقرة", "elevation_m": 1003, "latitude": 27.46464, "longitude": 41.65681},
    {"name": "النقرة", "elevation_m": 1001, "latitude": 27.46559, "longitude": 41.65758},
    {"name": "نقطة - وسط المدينة", "elevation_m": 995, "latitude": 27.50517, "longitude": 41.69502},
    {"name": "نقطة - وسط المدينة", "elevation_m": 992, "latitude": 27.50213, "longitude": 41.69771},
    {"name": "نقطة - وسط المدينة", "elevation_m": 990, "latitude": 27.50342, "longitude": 41.69822},
    {"name": "نقطة جنوبية", "elevation_m": 1002, "latitude": 27.43759, "longitude": 41.69456},
    {"name": "نقطة شمالية", "elevation_m": 967, "latitude": 27.56500, "longitude": 41.70733},
    {"name": "نقطة شمالية", "elevation_m": 975, "latitude": 27.55443, "longitude": 41.69883},
    {"name": "نقطة شمالية", "elevation_m": 980, "latitude": 27.55055, "longitude": 41.69687},
    {"name": "نقطة شمالية", "elevation_m": 992, "latitude": 27.57030, "longitude": 41.68097},
    {"name": "نقطة غربية", "elevation_m": 1029, "latitude": 27.44783, "longitude": 41.62859},
    {"name": "نقطة غربية", "elevation_m": 1035, "latitude": 27.46023, "longitude": 41.62143},
    {"name": "نقطة غربية", "elevation_m": 1060, "latitude": 27.42363, "longitude": 41.58989},
    {"name": "نقطة غربية", "elevation_m": 1083, "latitude": 27.40740, "longitude": 41.57255},
    {"name": "نقطة وسط", "elevation_m": 1018, "latitude": 27.51187, "longitude": 41.67135},
    {"name": "نقطة وسط", "elevation_m": 1006, "latitude": 27.52955, "longitude": 41.67724},
    {"name": "نقطة شمالية شرقية", "elevation_m": 959, "latitude": 27.56971, "longitude": 41.72307},
    {"name": "نقطة وسط", "elevation_m": 993, "latitude": 27.52439, "longitude": 41.69699},
    {"name": "نقطة وسط", "elevation_m": 989, "latitude": 27.52258, "longitude": 41.70263},
    {"name": "نقطة وسط", "elevation_m": 984, "latitude": 27.48761, "longitude": 41.69962},
]


def calculate_risk_weight(elevation_m: float, all_elevations: list[float]) -> float:
    min_elev = min(all_elevations)
    max_elev = max(all_elevations)
    if max_elev == min_elev:
        return 0.65
    normalized = (max_elev - elevation_m) / (max_elev - min_elev)
    risk_weight = 0.3 + (normalized * 0.7)
    return round(risk_weight, 3)


def main():
    init_db()

    all_elevations = [p["elevation_m"] for p in CLIENT_LOW_POINTS]

    highest_risk = None
    lowest_risk = None

    for point in CLIENT_LOW_POINTS:
        risk_weight = calculate_risk_weight(point["elevation_m"], all_elevations)
        insert_low_point(
            latitude=point["latitude"],
            longitude=point["longitude"],
            street_name=point["name"],
            elevation_estimate=point["elevation_m"],
            risk_weight=risk_weight,
        )

        if highest_risk is None or risk_weight > highest_risk[1]:
            highest_risk = (point["name"], risk_weight)
        if lowest_risk is None or risk_weight < lowest_risk[1]:
            lowest_risk = (point["name"], risk_weight)

    min_pt = min(CLIENT_LOW_POINTS, key=lambda p: p["elevation_m"])
    max_pt = max(CLIENT_LOW_POINTS, key=lambda p: p["elevation_m"])
    print(f"Inserted {len(CLIENT_LOW_POINTS)} low points.")
    print(f"Most flood-prone: elevation={min_pt['elevation_m']}m, weight={highest_risk[1]}")
    print(f"Least flood-prone: elevation={max_pt['elevation_m']}m, weight={lowest_risk[1]}")


if __name__ == "__main__":
    main()
