"""
IMD Binary Data Parser & Preprocessing Utilities
Handles:
  - IMD 0.25° gridded rainfall (.bin)
  - IMD 1.0° gridded max/min temperature (.bin)
  - Synthetic data generation for demo
  - Humidity, wind, cloud cover enrichment
"""

import numpy as np
import pandas as pd
import struct
from pathlib import Path
from typing import Tuple, Dict, List, Optional
import json

# ─────────────────────────────────────────────────────────────
# IMD Grid Specifications
# ─────────────────────────────────────────────────────────────
RAIN_GRID = {
    "lat_start": 6.5, "lat_end": 38.5, "lat_step": 0.25,
    "lon_start": 66.5, "lon_end": 100.0, "lon_step": 0.25,
    "nlat": 129, "nlon": 135
}

TEMP_GRID = {
    "lat_start": 7.5, "lat_end": 37.5, "lat_step": 1.0,
    "lon_start": 67.5, "lon_end": 97.5, "lon_step": 1.0,
    "nlat": 31, "nlon": 31
}

# Maharashtra bounding box (approx)
MAHARASHTRA_BBOX = {
    "lat_min": 15.6, "lat_max": 22.1,
    "lon_min": 72.6, "lon_max": 80.9
}

# Major cities in Maharashtra for point forecasts
MAHARASHTRA_CITIES = {
    "Mumbai":    {"lat": 19.07, "lon": 72.87, "population": 20.4, "elevation": 14, "district": "Mumbai Suburban", "river": "Mithi"},
    "Pune":      {"lat": 18.52, "lon": 73.86, "population": 7.4,  "elevation": 560, "district": "Pune", "river": "Mula-Mutha"},
    "Nagpur":    {"lat": 21.15, "lon": 79.09, "population": 3.5,  "elevation": 310, "district": "Nagpur", "river": "Nag"},
    "Nashik":    {"lat": 20.00, "lon": 73.79, "population": 2.1,  "elevation": 584, "district": "Nashik", "river": "Godavari"},
    "Aurangabad":{"lat": 19.88, "lon": 75.34, "population": 1.6,  "elevation": 513, "district": "Aurangabad", "river": "Kham"},
    "Solapur":   {"lat": 17.68, "lon": 75.90, "population": 1.2,  "elevation": 458, "district": "Solapur", "river": "Bhima"},
    "Kolhapur":  {"lat": 16.70, "lon": 74.23, "population": 0.7,  "elevation": 569, "district": "Kolhapur", "river": "Panchaganga"},
}

# Major rivers in Maharashtra for flood modeling
MAHARASHTRA_RIVERS = {
    "Godavari": {"cities": ["Nashik"], "basin_area_km2": 312812, "avg_discharge_m3s": 3508},
    "Krishna":  {"cities": ["Solapur", "Kolhapur"], "basin_area_km2": 258948, "avg_discharge_m3s": 2091},
    "Bhima":    {"cities": ["Pune", "Solapur"], "basin_area_km2": 70614, "avg_discharge_m3s": 446},
    "Tapi":     {"cities": [], "basin_area_km2": 65145, "avg_discharge_m3s": 508},
}

# Major reservoirs
MAHARASHTRA_RESERVOIRS = {
    "Koyna":     {"capacity_mcm": 2797, "city": "Kolhapur", "river": "Krishna"},
    "Jayakwadi": {"capacity_mcm": 2909, "city": "Aurangabad", "river": "Godavari"},
    "Ujani":     {"capacity_mcm": 3320, "city": "Solapur", "river": "Bhima"},
    "Gangapur":  {"capacity_mcm": 215,  "city": "Nashik", "river": "Godavari"},
}


def imd_bin_to_array(filepath: str, grid: dict, missing_val: float = -999.0) -> np.ndarray:
    """Read IMD binary (.bin) gridded file into numpy array."""
    nlat, nlon = grid["nlat"], grid["nlon"]
    data = np.fromfile(filepath, dtype=np.float32)
    data = data.reshape((nlat, nlon))
    data[data == missing_val] = np.nan
    return np.flipud(data)  # Flip to get lat increasing upward


def make_lat_lon_grids(grid: dict) -> Tuple[np.ndarray, np.ndarray]:
    lats = np.arange(grid["lat_start"], grid["lat_end"] + grid["lat_step"] / 2, grid["lat_step"])
    lons = np.arange(grid["lon_start"], grid["lon_end"] + grid["lon_step"] / 2, grid["lon_step"])
    return lats[:grid["nlat"]], lons[:grid["nlon"]]


# ─────────────────────────────────────────────────────────────
# Synthetic Realistic Data Generator
# ─────────────────────────────────────────────────────────────

def _monsoon_signal(doy: np.ndarray) -> np.ndarray:
    """Approximate seasonal monsoon rainfall cycle (day-of-year)."""
    # Peak around Aug 1 (doy≈213), onset Jun 1 (doy≈152)
    signal = np.exp(-0.5 * ((doy - 213) / 45) ** 2)
    signal[doy < 120] = 0
    signal[doy > 300] = 0
    return signal


def generate_synthetic_climate_data(
    years: int = 35,
    seed: int = 42
) -> Dict[str, pd.DataFrame]:
    """
    Generate synthetic but statistically realistic IMD-like data
    for Maharashtra's major cities (1990–2024).
    Returns dict with 'rainfall', 'max_temp', 'min_temp',
    'humidity', 'wind_speed', 'cloud_cover' DataFrames.
    """
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("1990-01-01")
    end = pd.Timestamp("2024-12-31")
    dates = pd.date_range(start, end, freq="D")
    n = len(dates)

    city_rainfall = {}
    city_max_temp = {}
    city_min_temp = {}
    city_humidity = {}
    city_wind = {}
    city_cloud = {}

    doy = np.array([d.dayofyear for d in dates])
    year_arr = np.array([d.year for d in dates])

    # ── Climate change trend: +0.04°C/year from 1990
    warming_trend = (year_arr - 1990) * 0.04

    for city, coords in MAHARASHTRA_CITIES.items():
        lat = coords["lat"]
        elev = coords.get("elevation", 100)

        # ── RAINFALL ─────────────────────────────────────────
        mon_signal = _monsoon_signal(doy.copy())
        # Base daily rain: ~5 mm peak, gamma distributed
        shape_param = 0.7
        scale_param = 8.0
        raw = rng.gamma(shape_param, scale_param, n)
        rain = raw * mon_signal * 2.5
        # ENSO-like interannual variability (quasi-6yr cycle)
        enso = 0.3 * np.sin(2 * np.pi * year_arr / 6.1)
        rain = rain * (1 + enso)
        rain = np.maximum(rain, 0)
        city_rainfall[city] = rain

        # ── MAX TEMP ─────────────────────────────────────────
        # Seasonal: peak ~May (doy 135), cool ~Jan
        seasonal_max = 32 + 8 * np.sin(2 * np.pi * (doy - 60) / 365)
        # Lat adjustment: Nagpur hotter than Mumbai
        lat_adj = (19.5 - lat) * 0.4
        # Elevation adjustment: ~6.5°C per 1000m
        elev_adj = -elev * 0.0065
        noise = rng.normal(0, 1.2, n)
        max_t = seasonal_max + lat_adj + elev_adj + warming_trend + noise
        # Monsoon cooling effect
        max_t -= mon_signal * 4
        city_max_temp[city] = max_t

        # ── MIN TEMP ─────────────────────────────────────────
        seasonal_min = 20 + 6 * np.sin(2 * np.pi * (doy - 75) / 365)
        lat_adj_min = (19.5 - lat) * 0.35
        noise_min = rng.normal(0, 0.9, n)
        min_t = seasonal_min + lat_adj_min + elev_adj + warming_trend + noise_min
        city_min_temp[city] = min_t

        # ── HUMIDITY (%) ─────────────────────────────────────
        # High during monsoon, low in winter/summer
        base_humidity = 55 + 30 * mon_signal + rng.normal(0, 5, n)
        # Coastal cities have higher baseline
        if city in ["Mumbai", "Kolhapur"]:
            base_humidity += 10
        base_humidity = np.clip(base_humidity, 15, 99)
        city_humidity[city] = base_humidity

        # ── WIND SPEED (km/h) ────────────────────────────────
        # Higher during monsoon onset, coastal cities windier
        base_wind = 8 + 6 * mon_signal + rng.normal(0, 2, n)
        if city == "Mumbai":
            base_wind += 5  # Coastal
        base_wind = np.clip(base_wind, 1, 45)
        city_wind[city] = base_wind

        # ── CLOUD COVER (okta 0-8) ───────────────────────────
        base_cloud = 2 + 5.5 * mon_signal + rng.normal(0, 0.8, n)
        base_cloud = np.clip(base_cloud, 0, 8)
        city_cloud[city] = base_cloud

    df_rain = pd.DataFrame(city_rainfall, index=dates)
    df_max = pd.DataFrame(city_max_temp, index=dates)
    df_min = pd.DataFrame(city_min_temp, index=dates)
    df_humidity = pd.DataFrame(city_humidity, index=dates)
    df_wind = pd.DataFrame(city_wind, index=dates)
    df_cloud = pd.DataFrame(city_cloud, index=dates)

    return {
        "rainfall": df_rain,
        "max_temp": df_max,
        "min_temp": df_min,
        "humidity": df_humidity,
        "wind_speed": df_wind,
        "cloud_cover": df_cloud,
    }


def generate_spatial_grid_snapshot(
    variable: str = "rainfall",
    date: str = "2024-07-15",
    scenario_delta: Dict[str, float] = None
) -> Dict:
    """
    Generate a spatial grid over India for map visualization.
    Returns dict with lat, lon, values arrays.
    """
    if scenario_delta is None:
        scenario_delta = {}

    rng = np.random.default_rng(seed=hash(date) % (2**31))
    d = pd.Timestamp(date)
    doy = d.dayofyear

    # India grid: 6.5N-38.5N, 66.5E-100E at 0.5° resolution (coarser for speed)
    lats = np.arange(7.0, 38.5, 0.5)
    lons = np.arange(67.0, 98.0, 0.5)
    LAT, LON = np.meshgrid(lats, lons, indexing="ij")

    if variable == "rainfall":
        monsoon = _monsoon_signal(np.array([doy]))[0]
        # Spatial pattern: Western Ghats high, Rajasthan low, NE high
        base = (
            12 * monsoon
            * np.exp(-0.3 * np.abs(LON - 74))   # Western Ghats peak
            + 5 * monsoon * np.exp(-0.15 * np.abs(LAT - 25) - 0.1 * np.abs(LON - 91))  # NE
            + rng.normal(0, 0.8, LAT.shape)
        )
        base = np.clip(base, 0, None)
        delta = scenario_delta.get("rainfall_pct", 0) / 100
        base = base * (1 + delta)
        values = base

    elif variable == "max_temp":
        # North hot, South moderate, coasts cooler
        base = (
            28 + 0.15 * (LAT - 20)        # latitude gradient
            - 0.05 * (LON - 80) ** 2 / 50  # longitude mild effect
            + 3 * np.sin(2 * np.pi * (doy - 60) / 365)
            + rng.normal(0, 0.5, LAT.shape)
        )
        delta = scenario_delta.get("temp_delta", 0)
        base += delta
        values = base

    elif variable == "min_temp":
        base = (
            18 + 0.12 * (LAT - 20)
            + 2 * np.sin(2 * np.pi * (doy - 75) / 365)
            + rng.normal(0, 0.4, LAT.shape)
        )
        delta = scenario_delta.get("temp_delta", 0)
        base += delta
        values = base

    elif variable == "humidity":
        monsoon = _monsoon_signal(np.array([doy]))[0]
        base = 45 + 40 * monsoon + rng.normal(0, 4, LAT.shape)
        # Coastal strip gets more humid
        coastal_mask = LON < 74
        base[coastal_mask] += 8
        base = np.clip(base, 15, 99)
        values = base

    elif variable == "cloud_cover":
        monsoon = _monsoon_signal(np.array([doy]))[0]
        base = 1.5 + 5.5 * monsoon + rng.normal(0, 0.6, LAT.shape)
        base = np.clip(base, 0, 8)
        values = base

    else:
        values = rng.normal(25, 3, LAT.shape)

    # Build GeoJSON-style grid
    grid_points = []
    step_lat = float(lats[1] - lats[0])
    step_lon = float(lons[1] - lons[0])
    for i in range(len(lats)):
        for j in range(len(lons)):
            v = float(values[i, j])
            if not np.isnan(v):
                grid_points.append({
                    "lat": float(lats[i]),
                    "lon": float(lons[j]),
                    "value": round(v, 2)
                })

    return {
        "variable": variable,
        "date": date,
        "unit": _get_unit(variable),
        "grid_step": step_lat,
        "points": grid_points,
        "stats": {
            "min": round(float(np.nanmin(values)), 2),
            "max": round(float(np.nanmax(values)), 2),
            "mean": round(float(np.nanmean(values)), 2),
        }
    }


def _get_unit(variable: str) -> str:
    """Get unit string for a climate variable."""
    units = {
        "rainfall": "mm/day",
        "max_temp": "°C",
        "min_temp": "°C",
        "humidity": "%",
        "wind_speed": "km/h",
        "cloud_cover": "okta",
    }
    return units.get(variable, "")


def generate_timeline_snapshots(
    variable: str = "rainfall",
    days: int = 30,
    scenario_delta: Dict[str, float] = None,
) -> List[Dict]:
    """Generate multiple daily snapshots for the time scrubber animation."""
    snapshots = []
    base_date = pd.Timestamp("2024-07-01")
    for i in range(days):
        date_str = str((base_date + pd.Timedelta(days=i)).date())
        snap = generate_spatial_grid_snapshot(variable, date_str, scenario_delta)
        # Slim down — only stats and a subset of points for the timeline
        snapshots.append({
            "date": date_str,
            "stats": snap["stats"],
            "points": snap["points"][::3],  # Every 3rd point for speed
        })
    return snapshots


def compute_anomaly(
    current: np.ndarray,
    climatology_mean: np.ndarray,
    climatology_std: np.ndarray
) -> np.ndarray:
    """Standardized anomaly (Z-score)."""
    return (current - climatology_mean) / (climatology_std + 1e-6)


def build_sequences(data: np.ndarray, seq_len: int = 30) -> Tuple[np.ndarray, np.ndarray]:
    """Build input/output sequences for LSTM training."""
    X, y = [], []
    for i in range(len(data) - seq_len):
        X.append(data[i:i + seq_len])
        y.append(data[i + seq_len])
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def normalize(data: np.ndarray) -> Tuple[np.ndarray, float, float]:
    mu, sigma = float(np.nanmean(data)), float(np.nanstd(data))
    return (data - mu) / (sigma + 1e-6), mu, sigma


def denormalize(data: np.ndarray, mu: float, sigma: float) -> np.ndarray:
    return data * sigma + mu
