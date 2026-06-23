"""Satellite client for fetching Sentinel Hub imagery."""

import base64
import io
from datetime import datetime, timedelta

import numpy as np
from PIL import Image

from config.settings import SENTINEL_HUB_CLIENT_ID, SENTINEL_HUB_CLIENT_SECRET


def get_sentinel_config():
    from sentinelhub import SHConfig

    config = SHConfig()
    config.sh_client_id = SENTINEL_HUB_CLIENT_ID
    config.sh_client_secret = SENTINEL_HUB_CLIENT_SECRET

    if (
        not SENTINEL_HUB_CLIENT_ID
        or not SENTINEL_HUB_CLIENT_SECRET
        or SENTINEL_HUB_CLIENT_ID == "your_client_id_here"
        or SENTINEL_HUB_CLIENT_SECRET == "your_client_secret_here"
    ):
        print(
            "Sentinel Hub credentials not configured. Satellite features will be "
            "unavailable. Register at https://dataspace.copernicus.eu to get "
            "credentials."
        )

    return config


def fetch_latest_sentinel2_image(bbox_coords: tuple, resolution: int = 10) -> dict:
    from sentinelhub import (
        BBox,
        CRS,
        DataCollection,
        MimeType,
        SentinelHubRequest,
        bbox_to_dimensions,
    )

    today = datetime.now()

    try:
        config = get_sentinel_config()
        bbox = BBox(bbox_coords, crs=CRS.WGS84)
        size = bbox_to_dimensions(bbox, resolution=resolution)
        time_interval = (today - timedelta(days=10), today)

        evalscript = """
        //VERSION=3
        function setup() {
          return {
            input: ["B03", "B08", "dataMask"],
            output: { bands: 3, sampleType: "FLOAT32" }
          };
        }
        function evaluatePixel(sample) {
          return [sample.B03, sample.B08, sample.dataMask];
        }
        """

        request = SentinelHubRequest(
            evalscript=evalscript,
            input_data=[
                SentinelHubRequest.input_data(
                    data_collection=DataCollection.SENTINEL2_L2A,
                    time_interval=time_interval,
                )
            ],
            responses=[
                SentinelHubRequest.output_response(
                    identifier="default",
                    response_format=MimeType.TIFF,
                )
            ],
            bbox=bbox,
            size=size,
            config=config,
        )

        image_data = request.get_data()
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "image_data": None,
            "acquisition_date": None,
            "bands": None,
        }

    return {
        "success": True,
        "error": None,
        "image_data": image_data,
        "acquisition_date": str(today.date()),
        "bands": ["B03_green", "B08_nir", "dataMask"],
    }


def fetch_sentinel2_truecolor_overlay(bbox_coords: tuple, resolution: int = 10) -> dict:
    from sentinelhub import (
        BBox,
        CRS,
        DataCollection,
        MimeType,
        SentinelHubRequest,
        bbox_to_dimensions,
    )

    today = datetime.now()

    try:
        config = get_sentinel_config()
        bbox = BBox(bbox_coords, crs=CRS.WGS84)
        size = bbox_to_dimensions(bbox, resolution=resolution)
        time_interval = (today - timedelta(days=10), today)

        evalscript = """
        //VERSION=3
        function setup() {
          return {
            input: ["B04", "B03", "B02"],
            output: { bands: 3, sampleType: "AUTO" }
          };
        }
        function evaluatePixel(sample) {
          return [2.5*sample.B04, 2.5*sample.B03, 2.5*sample.B02];
        }
        """

        request = SentinelHubRequest(
            evalscript=evalscript,
            input_data=[
                SentinelHubRequest.input_data(
                    data_collection=DataCollection.SENTINEL2_L2A,
                    time_interval=time_interval,
                )
            ],
            responses=[
                SentinelHubRequest.output_response(
                    identifier="default",
                    response_format=MimeType.PNG,
                )
            ],
            bbox=bbox,
            size=size,
            config=config,
        )

        image_array = request.get_data()[0]
        image_array = np.clip(image_array, 0, 255).astype("uint8")
        img = Image.fromarray(image_array)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        min_lon, min_lat, max_lon, max_lat = bbox_coords
        bounds = [[min_lat, min_lon], [max_lat, max_lon]]

        return {
            "success": True,
            "error": None,
            "image_base64": image_base64,
            "bounds": bounds,
            "acquisition_date": str(time_interval[1]),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "image_base64": None,
            "bounds": None,
            "acquisition_date": None,
        }


def get_satellite_tile_layer_url(bbox_coords: tuple = None) -> dict:
    return {
        "recommended_approach": (
            "use Esri World Imagery tile layer for basemap toggle: "
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x} - this is free, fast, "
            "and suitable for basemap display. Reserve Sentinel Hub calls "
            "specifically for the NDWI water-detection analysis on focused "
            "areas, not general map tiles."
        ),
        "esri_tile_url": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
    }
