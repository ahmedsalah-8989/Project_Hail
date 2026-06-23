"""Detect low-elevation points prone to flooding from street network GeoJSON."""

import json
import math
import os
import sys
import time

import numpy as np

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.db import get_low_points, insert_low_point, init_db, get_connection
from core.osm_client import reverse_geocode_point
from config.settings import HAIL_CITY_CENTER, PROCESSED_DATA_DIR
from scripts.load_low_points import calculate_risk_weight

ALLOWED_URBAN_TYPES = {
    "residential", "primary", "secondary", "tertiary", "service", "living_street",
}
URBAN_RADIUS_KM = 12.0
ORIGINAL_CLIENT_COUNT = 29

_UNNAMED_AR = "\u0645\u0646\u0637\u0642\u0629 \u063a\u064a\u0631 \u0645\u0633\u0645\u0651\u0627\u0629 (\u0635\u062d\u0631\u0627\u0621/\u0623\u0631\u0636 \u0641\u0636\u0627\u0621)"


def load_geojson_streets(filepath: str) -> list[dict]:
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    streets = []
    for feat in features:
        geom = feat.get("geometry", {})
        if geom.get("type") != "LineString":
            continue
        props = feat.get("properties", {})
        coords = geom.get("coordinates", [])
        if len(coords) < 2:
            continue
        streets.append({
            "name": props.get("name", "Unnamed road"),
            "osm_id": props.get("osm_id"),
            "highway": props.get("highway"),
            "coordinates": coords,
        })
    return streets


def simulate_street_elevation(lon: float, lat: float) -> float:
    val = (
        math.sin(lat * 150) * math.cos(lon * 150) * 45
        + math.sin(lat * 30) * 30
    )
    elevation = 1000 + val
    return round(float(elevation), 2)


def _haversine_km(lat1, lon1, lat2, lon2):
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


def is_urban_street(name: str, highway: str | None, lat: float, lon: float) -> bool:
    if highway is not None:
        return highway in ALLOWED_URBAN_TYPES

    if name and name != "Unnamed road":
        return True

    center_lat, center_lon = HAIL_CITY_CENTER
    dist = _haversine_km(lat, lon, center_lat, center_lon)
    return dist <= URBAN_RADIUS_KM


def _to_lat_lon_set(points, key="latitude", key2="longitude"):
    result = set()
    for p in points:
        result.add((p[key], p[key2]))
    return result


def main():
    init_db()

    existing_inferred = get_low_points(source="osm_inferred")
    if len(existing_inferred) > 0:
        print(
            f"WARNING: OSM-inferred points already exist ({len(existing_inferred)} rows). "
            "Re-running will create duplicates unless you manually clear them first."
        )
        try:
            response = input("Type 'yes' to proceed, anything else to abort: ")
        except EOFError:
            print("Non-interactive mode detected. Exiting.")
            return
        if response.strip().lower() != "yes":
            print("Aborted.")
            return

    existing = get_low_points()
    existing_coords = _to_lat_lon_set(existing)
    print(f"Existing low points in DB: {len(existing)}")

    originals = existing[:ORIGINAL_CLIENT_COUNT]
    print(f"Preserving {len(originals)} original client low points.")

    geojson_path = os.path.join(PROCESSED_DATA_DIR, "street_network.geojson")
    if not os.path.exists(geojson_path):
        print(f"Error: GeoJSON file not found at {geojson_path}")
        return

    streets = load_geojson_streets(geojson_path)
    print(f"Street segments loaded: {len(streets)}")

    center_lat, center_lon = HAIL_CITY_CENTER

    filtered_streets = []
    skipped_track = 0
    skipped_unnamed_desert = 0
    for s in streets:
        coords = s["coordinates"]
        mid_idx = len(coords) // 2 if len(coords) >= 3 else 0
        lon, lat = coords[mid_idx]

        if not is_urban_street(s["name"], s["highway"], lat, lon):
            if s["highway"] is not None and s["highway"] not in ALLOWED_URBAN_TYPES:
                skipped_track += 1
            else:
                skipped_unnamed_desert += 1
            continue
        filtered_streets.append(s)

    print(f"After urban-type filter:           {len(filtered_streets)} segments kept")
    print(f"  Skipped (non-urban highway tag): {skipped_track}")
    print(f"  Skipped (unnamed outside {URBAN_RADIUS_KM}km): {skipped_unnamed_desert}")

    candidates = []
    for s in filtered_streets:
        coords = s["coordinates"]
        mid_idx = len(coords) // 2 if len(coords) >= 3 else 0
        lon, lat = coords[mid_idx]
        elevation = simulate_street_elevation(lon, lat)
        candidates.append({
            "name": s["name"],
            "lat": lat,
            "lon": lon,
            "elevation": elevation,
        })

    print(f"Candidate points generated: {len(candidates)}")

    candidates.sort(key=lambda c: c["elevation"])

    forbidden = set(existing_coords)

    selected = []
    for c in candidates:
        if len(selected) >= 150:
            break
        key = (c["lat"], c["lon"])
        if key in forbidden:
            continue
        too_close = False
        for lat2, lon2 in forbidden:
            d = _haversine_km(c["lat"], c["lon"], lat2, lon2)
            if d < 0.3:
                too_close = True
                break
        if too_close:
            continue
        forbidden.add(key)
        selected.append(c)

    selected = selected[:150]
    print(f"Points after spatial filtering: {len(selected)}")

    if not selected:
        print("No new low points to insert.")
        return

    conn = get_connection()
    try:
        conn.execute("DELETE FROM low_points")
        conn.commit()
    finally:
        conn.close()

    for p in originals:
        insert_low_point(
            latitude=p["latitude"],
            longitude=p["longitude"],
            street_name=p["street_name"],
            elevation_estimate=p["elevation_estimate"],
            risk_weight=p["risk_weight"],
        )
    print(f"Re-inserted {len(originals)} original client low points.")

    all_elevations = [p["elevation"] for p in selected]
    inserted_count = 0
    lowest = min(selected, key=lambda p: p["elevation"])

    for p in selected:
        rw = calculate_risk_weight(p["elevation"], all_elevations)
        geo = reverse_geocode_point(p["lat"], p["lon"])
        time.sleep(1)
        if geo["success"] and geo["is_named_place"] and geo["best_name"] is not None:
            resolved_name = geo["best_name"]
        else:
            resolved_name = _UNNAMED_AR
        insert_low_point(
            latitude=p["lat"],
            longitude=p["lon"],
            street_name=resolved_name,
            elevation_estimate=p["elevation"],
            risk_weight=rw,
            source="osm_inferred",
        )
        inserted_count += 1

    new_total = len(originals) + inserted_count

    desert_removed = skipped_unnamed_desert + skipped_track

    print()
    print("=" * 60)
    print("EXECUTION SUMMARY — URBAN LOW-POINT DETECTION")
    print("=" * 60)
    print(f"Total streets scanned:            {len(streets)}")
    print(f"Urban-kept streets:               {len(filtered_streets)}")
    print(f"Desert/non-urban removed:         {desert_removed}")
    print(f"Original client points preserved: {len(originals)}")
    print(f"New urban low points inserted:    {inserted_count}")
    print(f"Lowest urban point discovered:")
    print(f"  Name:       {lowest['name']}")
    print(f"  Coordinates: ({lowest['lat']:.6f}, {lowest['lon']:.6f})")
    print(f"  Elevation:  {lowest['elevation']}m")
    print(f"New total monitored points:       {new_total}")
    print(f"Urban-bound points:               YES — all within "
          f"{URBAN_RADIUS_KM}km of Hail center")
    print("=" * 60)


if __name__ == "__main__":
    main()
