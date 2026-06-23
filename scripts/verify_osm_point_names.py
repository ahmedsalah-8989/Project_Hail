"""Verify/correct osm_inferred point names via Nominatim reverse geocoding."""

import sys
import os
import time

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.db import get_connection, get_low_points
from core.osm_client import reverse_geocode_point

_UNNAMED_AR = "\u0645\u0646\u0637\u0642\u0629 \u063a\u064a\u0631 \u0645\u0633\u0645\u0651\u0627\u0629 (\u0635\u062d\u0631\u0627\u0621/\u0623\u0631\u0636 \u0641\u0636\u0627\u0621)"


def main():
    osm_points = get_low_points(source="osm_inferred")
    total = len(osm_points)
    print(
        f"Verifying {total} OSM-inferred points via reverse geocoding "
        f"(this will take ~{total} seconds due to rate limiting)..."
    )

    corrected_name = 0
    relabeled_desert = 0
    failed = 0

    conn = get_connection()
    try:
        for i, p in enumerate(osm_points, start=1):
            pid = p["id"]
            old_name = p["street_name"]
            lat = p["latitude"]
            lon = p["longitude"]

            result = reverse_geocode_point(lat, lon)
            time.sleep(1)

            if not result["success"]:
                print(
                    f"  [{i}/{total}] WARNING: Point {pid} ({lat:.5f}, {lon:.5f}) "
                    f"geocoding failed — keeping old name. Error: {result['error']}"
                )
                failed += 1
                continue

            if result["is_named_place"] and result["best_name"] is not None:
                new_name = result["best_name"]
                if new_name != old_name:
                    conn.execute(
                        "UPDATE low_points SET street_name = ? WHERE id = ?",
                        (new_name, pid),
                    )
                    print(
                        f"  [{i}/{total}] Point {pid}: \"{old_name}\" -> \"{new_name}\" "
                        f"(neighbourhood name)"
                    )
                    corrected_name += 1
                else:
                    print(
                        f"  [{i}/{total}] Point {pid}: unchanged (already \"{old_name}\")"
                    )
            else:
                if old_name != _UNNAMED_AR:
                    conn.execute(
                        "UPDATE low_points SET street_name = ? WHERE id = ?",
                        (_UNNAMED_AR, pid),
                    )
                    print(
                        f"  [{i}/{total}] Point {pid}: \"{old_name}\" -> \"{_UNNAMED_AR}\" "
                        f"(desert/empty area)"
                    )
                    relabeled_desert += 1
                else:
                    print(
                        f"  [{i}/{total}] Point {pid}: unchanged (already \"{_UNNAMED_AR}\")"
                    )

        conn.commit()
    finally:
        conn.close()

    print()
    print("=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"Total OSM-inferred points:         {total}")
    print(f"Corrected to real neighbourhood:   {corrected_name}")
    print(f"Relabeled as unnamed/desert:       {relabeled_desert}")
    print(f"Failed (kept original name):       {failed}")
    print("=" * 60)


if __name__ == "__main__":
    main()
