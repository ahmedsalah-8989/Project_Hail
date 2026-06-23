"""Water detection module using satellite imagery analysis."""

import numpy as np


def calculate_ndwi(green_band: np.ndarray, nir_band: np.ndarray) -> np.ndarray:
    if green_band.shape != nir_band.shape:
        raise ValueError(
            f"green_band shape {green_band.shape} does not match "
            f"nir_band shape {nir_band.shape}"
        )
    ndwi = (green_band - nir_band) / (green_band + nir_band + 1e-10)
    ndwi = np.clip(ndwi, -1.0, 1.0)
    return ndwi


def classify_water_pixels(
    ndwi_array: np.ndarray, threshold: float = 0.0
) -> np.ndarray:
    return ndwi_array > threshold


def calculate_water_coverage_percentage(
    water_mask: np.ndarray, valid_data_mask: np.ndarray = None
) -> float:
    if water_mask.size == 0:
        return 0.0

    if valid_data_mask is not None:
        valid_count = valid_data_mask.sum()
        if valid_count == 0:
            return 0.0
        percentage = (water_mask & valid_data_mask).sum() / valid_count * 100
    else:
        percentage = water_mask.sum() / water_mask.size * 100

    return round(float(percentage), 2)


def analyze_satellite_image_for_water(image_data: np.ndarray) -> dict:
    try:
        green_band = image_data[:, :, 0]
        nir_band = image_data[:, :, 1]
        valid_mask = image_data[:, :, 2].astype(bool)

        ndwi_array = calculate_ndwi(green_band, nir_band)
        water_mask = classify_water_pixels(ndwi_array)
        water_coverage_pct = calculate_water_coverage_percentage(
            water_mask, valid_mask
        )
        water_detected = water_coverage_pct > 5.0

        if valid_mask.sum() > 0:
            ndwi_mean = float(np.mean(ndwi_array[valid_mask]))
            ndwi_mean = round(ndwi_mean, 4)
        else:
            ndwi_mean = None

        return {
            "success": True,
            "error": None,
            "water_detected": water_detected,
            "water_coverage_pct": water_coverage_pct,
            "ndwi_mean": ndwi_mean,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "water_detected": False,
            "water_coverage_pct": 0.0,
            "ndwi_mean": None,
        }
