"""Radar client for fetching rainfall radar data from RainViewer API."""

import requests

from config.settings import RAINVIEWER_BASE_URL


def get_radar_timestamps() -> dict:
    try:
        resp = requests.get(
            f"{RAINVIEWER_BASE_URL}/weather-maps.json", timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        return {
            "success": False,
            "error": str(e),
            "radar_frames": [],
            "host": None,
        }

    past_frames = data.get("radar", {}).get("past", [])
    host = data.get("host", "https://tilecache.rainviewer.com")

    return {
        "success": True,
        "error": None,
        "radar_frames": past_frames,
        "host": host,
    }


def get_latest_radar_tile_url(zoom: int = 8) -> dict:
    result = get_radar_timestamps()

    if not result["success"] or not result["radar_frames"]:
        return {
            "success": False,
            "tile_url_template": None,
            "timestamp": None,
            "error": (
                "No radar frames available - RainViewer coverage "
                "may be limited in this region"
            ),
        }

    frame = result["radar_frames"][-1]
    tile_url_template = (
        f"{result['host']}{frame['path']}/256/" "{z}/{x}/{y}/2/1_1.png"
    )

    return {
        "success": True,
        "tile_url_template": tile_url_template,
        "timestamp": frame["time"],
        "error": None,
    }


def check_radar_coverage_for_hail() -> dict:
    result = get_latest_radar_tile_url()

    return {
        "radar_available": result["success"],
        "coverage_note": (
            "RainViewer radar coverage in the Hail/Saudi Arabia region is "
            "limited due to sparse ground radar station density. Treat radar "
            "data as supplementary, not authoritative. Cross-reference with "
            "Open-Meteo rainfall data for verification."
        ),
        "tile_info": result,
    }
