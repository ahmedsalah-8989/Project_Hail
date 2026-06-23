from dotenv import load_dotenv
import os

load_dotenv()

HAIL_CITY_LAT = float(os.getenv("HAIL_CITY_LAT", "27.5114"))
HAIL_CITY_LON = float(os.getenv("HAIL_CITY_LON", "41.6885"))
HAIL_CITY_CENTER = (HAIL_CITY_LAT, HAIL_CITY_LON)
HAIL_CITY_RADIUS_KM = float(os.getenv("HAIL_CITY_RADIUS_KM", "50.0"))

OPENMETEO_BASE_URL = os.getenv("OPENMETEO_BASE_URL")
RAINVIEWER_BASE_URL = os.getenv("RAINVIEWER_BASE_URL")
SENTINEL_HUB_CLIENT_ID = os.getenv("SENTINEL_HUB_CLIENT_ID")
SENTINEL_HUB_CLIENT_SECRET = os.getenv("SENTINEL_HUB_CLIENT_SECRET")
OVERPASS_BASE_URL = os.getenv("OVERPASS_BASE_URL")

OPENMETEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

RISK_THRESHOLDS = {
    "low": (0, 25),
    "moderate": (26, 50),
    "high": (51, 75),
    "critical": (76, 100),
}

DB_PATH = "data/flood_system.db"
PROCESSED_DATA_DIR = "data/processed"
RAW_CLIENT_EVENTS_DIR = "data/raw/client_events"
