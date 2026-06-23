"""OSM client for fetching street network data via Overpass API and reverse geocoding."""

import json
import os
import time

import requests

from config.settings import HAIL_CITY_CENTER, HAIL_CITY_RADIUS_KM, OVERPASS_BASE_URL

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_GEO_USER_AGENT = "HailFloodWarningSystem/1.0"


def fetch_street_network(center_lat=None, center_lon=None, radius_km=None) -> dict:
    if center_lat is None or center_lon is None:
        center_lat, center_lon = HAIL_CITY_CENTER
    if radius_km is None:
        radius_km = HAIL_CITY_RADIUS_KM

    radius_m = int(radius_km * 1000)
    query = f"""
    [out:json][timeout:60];
    (
      way["highway"](around:{radius_m},{center_lat},{center_lon});
    );
    out body geom;
    """

    headers = {"User-Agent": "HailFloodSystem/1.0"}
    try:
        resp = requests.post(OVERPASS_BASE_URL, data={"data": query}, headers=headers, timeout=90)
    except requests.RequestException as e:
        print(f"Error fetching OSM data: {e}")
        return {"elements": []}

    if resp.status_code != 200:
        print(f"Warning: Overpass API returned status {resp.status_code}")
        return {"elements": []}

    return resp.json()


def extract_street_segments(osm_data: dict) -> list[dict]:
    segments = []
    for element in osm_data.get("elements", []):
        if element.get("type") != "way":
            continue
        geometry = element.get("geometry", [])
        if len(geometry) < 2:
            continue
        osm_id = element["id"]
        name = element.get("tags", {}).get("name", "Unnamed road")
        points = [(pt["lat"], pt["lon"]) for pt in geometry]
        segments.append({"osm_id": osm_id, "name": name, "points": points})
    return segments


def save_street_network(segments: list[dict], output_path: str) -> None:
    features = []
    for seg in segments:
        coords = [[lon, lat] for lat, lon in seg["points"]]
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords,
            },
            "properties": {
                "osm_id": seg["osm_id"],
                "name": seg["name"],
            },
        })

    geojson = {
        "type": "FeatureCollection",
        "features": features,
    }

    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)


def reverse_geocode_point(latitude: float, longitude: float) -> dict:
    """Reverse-geocode coordinates via Nominatim.

    Rate limit: callers MUST sleep 1 second between calls in a loop
    (Nominatim usage policy: max 1 request/second).
    """
    params = {
        "lat": latitude,
        "lon": longitude,
        "format": "json",
        "zoom": 16,
        "addressdetails": 1,
    }
    headers = {"User-Agent": _GEO_USER_AGENT}

    try:
        resp = requests.get(
            _NOMINATIM_URL, params=params, headers=headers, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {
            "success": False,
            "display_name": None,
            "is_named_place": False,
            "error": str(e),
        }

    display_name = data.get("display_name")
    address = data.get("address", {}) or {}

    named_keys = ("suburb", "neighbourhood", "residential", "quarter", "city_district")
    is_named_place = any(
        address.get(k) for k in named_keys
    )

    best_name = None
    for key in ("suburb", "neighbourhood", "residential", "quarter"):
        val = address.get(key)
        if val:
            best_name = val
            break

    return {
        "success": True,
        "display_name": display_name,
        "is_named_place": is_named_place,
        "best_name": best_name,
        "error": None,
    }
