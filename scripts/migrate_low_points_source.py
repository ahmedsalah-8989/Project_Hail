"""Migration: add source column to low_points and label existing rows.

Labels 29 client-verified rows by coordinate matching against
CLIENT_LOW_POINTS (±0.0001° tolerance), and 150 osm_inferred rows
for everything else. Exits with error if client_verified count != 29.
"""

import sys
import os

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from core.db import get_connection, get_low_points
from scripts.load_low_points import CLIENT_LOW_POINTS


def _source_column_exists(conn) -> bool:
    cursor = conn.execute("PRAGMA table_info(low_points)")
    cols = {row["name"] for row in cursor.fetchall()}
    return "source" in cols


def _add_source_column(conn) -> None:
    conn.execute(
        "ALTER TABLE low_points ADD COLUMN source TEXT NOT NULL DEFAULT 'client_verified'"
    )
    conn.commit()
    print("Added 'source' column to low_points table.")


def _build_client_coords(client_points: list[dict]) -> set:
    return {(round(p["latitude"], 4), round(p["longitude"], 4)) for p in client_points}


def main():
    conn = get_connection()
    try:
        if not _source_column_exists(conn):
            _add_source_column(conn)
        else:
            print("'source' column already exists in low_points table.")
    finally:
        conn.close()

    client_coords = _build_client_coords(CLIENT_LOW_POINTS)
    tolerance = 0.0001

    all_points = get_low_points()
    print(f"\nTotal rows in low_points: {len(all_points)}")

    client_count = 0
    osm_count = 0
    client_ids = []
    osm_ids = []

    for p in all_points:
        matched = False
        for cc_lat, cc_lon in client_coords:
            if abs(p["latitude"] - cc_lat) <= tolerance and abs(p["longitude"] - cc_lon) <= tolerance:
                matched = True
                break
        if matched:
            client_ids.append(p["id"])
            client_count += 1
        else:
            osm_ids.append(p["id"])
            osm_count += 1

    print(f"Identified by coordinate matching: {client_count} client_verified, {osm_count} osm_inferred")

    if client_count != 29:
        print(
            f"\nERROR: Expected exactly 29 client_verified rows, found {client_count}. "
            "Do NOT proceed with guessing. Manual review required.",
            file=sys.stderr,
        )
        sys.exit(1)

    conn = get_connection()
    try:
        if client_ids:
            placeholders = ",".join("?" for _ in client_ids)
            conn.execute(
                f"UPDATE low_points SET source = 'client_verified' WHERE id IN ({placeholders})",
                client_ids,
            )
        if osm_ids:
            placeholders = ",".join("?" for _ in osm_ids)
            conn.execute(
                f"UPDATE low_points SET source = 'osm_inferred' WHERE id IN ({placeholders})",
                osm_ids,
            )
        conn.commit()
    finally:
        conn.close()

    print(f"Labels written: {client_count} = 'client_verified', {osm_count} = 'osm_inferred'")

    verify_client = get_low_points(source="client_verified")
    verify_all = get_low_points()
    print(f"Verification: get_low_points(source='client_verified') = {len(verify_client)} rows")
    print(f"Verification: get_low_points() (no filter) = {len(verify_all)} rows")

    if len(verify_client) != 29:
        print(f"\nERROR: Post-migration verification failed. "
              f"Expected 29 client_verified, got {len(verify_client)}.",
              file=sys.stderr)
        sys.exit(1)

    print("\nMigration completed successfully.")


if __name__ == "__main__":
    main()
