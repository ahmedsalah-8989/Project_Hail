"""Fetch OSM street network data for Hail City."""

import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from config.settings import PROCESSED_DATA_DIR
from core.osm_client import fetch_street_network, extract_street_segments, save_street_network


def main():
    print("Fetching street network from OpenStreetMap Overpass API...")
    raw = fetch_street_network()

    if not raw.get("elements"):
        print(
            "Failed to fetch OSM data. Check internet connection or Overpass API availability. "
            "You can retry or use overpass-api.de mirrors (overpass.kumi.systems) if the main server is down."
        )
        return

    segments = extract_street_segments(raw)
    print(f"Extracted {len(segments)} street segments.")

    output_path = os.path.join(PROCESSED_DATA_DIR, "street_network.geojson")
    save_street_network(segments, output_path)
    print(f"Saved street network to {output_path} ({len(segments)} segments)")


if __name__ == "__main__":
    main()
