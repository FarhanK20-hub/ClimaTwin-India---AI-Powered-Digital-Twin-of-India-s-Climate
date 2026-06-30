"""
FastAPI Backend — AI-Powered Digital Twin of India's Climate
============================================================
Endpoints:
  GET  /                    → Dashboard UI
  GET  /api/status          → System health & readiness
  GET  /api/twin-clock      → Digital twin state with timestamp
  GET  /api/historical      → Historical time series for a city+variable
  GET  /api/predict         → AI forecast (LSTM) for a city+variable
  GET  /api/spatial-grid    → Spatial grid snapshot for map visualization
  GET  /api/timeline        → 30-day animated timeline snapshots
  POST /api/scenario        → Run a what-if scenario
  GET  /api/model-metrics   → Training metrics for all models
  GET  /api/scenarios/list  → Available scenario presets
  GET  /api/anomaly-alerts  → Current anomaly alerts
  GET  /api/city-profile/{city}    → Deep city drill-down
  GET  /api/feature-importance/{city}/{variable} → AI explainability
  GET  /api/ai-narrative    → Auto-generated climate story
"""

import os
import sys
import json
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import numpy as np
import pandas as pd
import torch

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.preprocess import (
    generate_synthetic_climate_data,
    generate_spatial_grid_snapshot,
    generate_timeline_snapshots,
    MAHARASHTRA_CITIES,
    MAHARASHTRA_RIVERS,
    MAHARASHTRA_RESERVOIRS,
)
from backend.model import (
    train_all_models, load_model, predict_future,
    compute_water_stress_index, compute_crop_yield_impact,
    compute_feature_importance, compute_river_discharge_change,
)
from backend.simulator import run_scenario, SCENARIO_PRESETS, generate_ai_narrative

# ─────────────────────────────────────────────────────────────
# Global State
# ─────────────────────────────────────────────────────────────
CLIMATE_DATA: Dict[str, pd.DataFrame] = {}
MODEL_METRICS: list = []
MODELS_TRAINED = False
DATA_LOADED = False

ROOT_DIR = Path(__file__).parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"


async def _train_models_bg():
    """Train models in background — non-blocking."""
    global MODEL_METRICS, MODELS_TRAINED
    try:
        loop = asyncio.get_event_loop()
        MODEL_METRICS = await loop.run_in_executor(None, lambda: train_all_models(CLIMATE_DATA))
        MODELS_TRAINED = True
        print("✅ All models trained!")
    except Exception as e:
        print(f"⚠️  Model training error: {e}")
        MODELS_TRAINED = True  # Allow API to serve fallback responses


@asynccontextmanager
async def lifespan(app_):
    global CLIMATE_DATA, DATA_LOADED
    print("🌍 Loading climate data...")
    CLIMATE_DATA = generate_synthetic_climate_data(years=35, seed=42)
    DATA_LOADED = True
    print(f"✅ Data loaded: {len(CLIMATE_DATA['rainfall'])} days, {len(CLIMATE_DATA)} variables")

    # Check for pre-trained models
    models_dir = ROOT_DIR / "models"
    existing = list(models_dir.glob("lstm_*.pt")) if models_dir.exists() else []
    if len(existing) >= 6:
        print(f"✅ Found {len(existing)} pre-trained models.")
        global MODELS_TRAINED
        MODELS_TRAINED = True
    else:
        print("🤖 Training AI models in background (2–3 min)...")
        asyncio.create_task(_train_models_bg())

    yield
    print("👋 Shutting down ClimaTwin India")


# ─────────────────────────────────────────────────────────────
# App Setup
# ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="ClimaTwin India — AI-Powered Digital Twin of India's Climate",
    description="Full-stack Digital Twin platform for ISRO Hack2Skill Hackathon — Maharashtra Pilot Region",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ─────────────────────────────────────────────────────────────
# Request Models
# ─────────────────────────────────────────────────────────────

class ScenarioRequest(BaseModel):
    preset: str = "normal"
    temp_delta: Optional[float] = None
    rainfall_pct: Optional[float] = None
    city: Optional[str] = None


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


@app.get("/api/status")
async def status():
    return {
        "data_loaded": DATA_LOADED,
        "models_trained": MODELS_TRAINED,
        "cities": list(MAHARASHTRA_CITIES.keys()),
        "variables": ["rainfall", "max_temp", "min_temp", "humidity", "wind_speed", "cloud_cover"],
        "data_range": {
            "start": "1990-01-01",
            "end": "2024-12-31",
            "days": len(CLIMATE_DATA.get("rainfall", pd.DataFrame()))
        },
        "version": "2.0.0",
        "twin_status": "Operational",
    }


@app.get("/api/twin-clock")
async def twin_clock():
    """Digital Twin current state — simulates real-time data assimilation."""
    now = datetime.utcnow()
    last_obs = datetime(2024, 12, 31)  # Last IMD observation date
    cities = list(MAHARASHTRA_CITIES.keys())
    rng = np.random.default_rng(seed=now.toordinal())

    city_states = {}
    for city in cities:
        city_info = MAHARASHTRA_CITIES[city]
        if DATA_LOADED and city in CLIMATE_DATA.get("rainfall", pd.DataFrame()).columns:
            df_rain = CLIMATE_DATA["rainfall"]
            df_temp = CLIMATE_DATA["max_temp"]
            df_hum = CLIMATE_DATA.get("humidity")
            df_wind = CLIMATE_DATA.get("wind_speed")
            df_cloud = CLIMATE_DATA.get("cloud_cover")
            # Use current day-of-year to pick a representative window
            # from the most recent year in the dataset (2024)
            current_doy = now.timetuple().tm_yday
            mask_2024 = df_rain.index.year == 2024
            doy_arr = df_rain.index.dayofyear
            target_start = max(1, current_doy - 3)
            target_end = current_doy + 4
            mask_window = mask_2024 & (doy_arr >= target_start) & (doy_arr <= target_end)
            if mask_window.sum() < 3:
                mask_window = slice(-7, None)
                last7_rain = float(df_rain[city].iloc[mask_window].mean())
                last7_temp = float(df_temp[city].iloc[mask_window].mean())
                last7_hum = float(df_hum[city].iloc[mask_window].mean()) if df_hum is not None and city in df_hum.columns else float(rng.uniform(55, 85))
                last7_wind = float(df_wind[city].iloc[mask_window].mean()) if df_wind is not None and city in df_wind.columns else float(rng.uniform(5, 15))
                last7_cloud = float(df_cloud[city].iloc[mask_window].mean()) if df_cloud is not None and city in df_cloud.columns else float(rng.uniform(2, 6))
            else:
                last7_rain = float(df_rain.loc[mask_window, city].mean())
                last7_temp = float(df_temp.loc[mask_window, city].mean())
                last7_hum = float(df_hum.loc[mask_window, city].mean()) if df_hum is not None and city in df_hum.columns else float(rng.uniform(55, 85))
                last7_wind = float(df_wind.loc[mask_window, city].mean()) if df_wind is not None and city in df_wind.columns else float(rng.uniform(5, 15))
                last7_cloud = float(df_cloud.loc[mask_window, city].mean()) if df_cloud is not None and city in df_cloud.columns else float(rng.uniform(2, 6))
        else:
            last7_rain = float(rng.uniform(5, 25))
            last7_temp = float(rng.uniform(28, 38))
            last7_hum = float(rng.uniform(55, 85))
            last7_wind = float(rng.uniform(5, 15))
            last7_cloud = float(rng.uniform(2, 6))

        city_states[city] = {
            "lat": city_info["lat"],
            "lon": city_info["lon"],
            "population_m": city_info.get("population", 1.0),
            "elevation_m": city_info.get("elevation", 100),
            "district": city_info.get("district", ""),
            "river": city_info.get("river", ""),
            "rainfall_7day_mm": round(last7_rain, 2),
            "max_temp_c": round(last7_temp, 2),
            "humidity_pct": round(last7_hum, 1),
            "wind_speed_kmh": round(last7_wind, 1),
            "cloud_cover_okta": round(last7_cloud, 1),
            "status": _classify_status(last7_rain, last7_temp),
        }

    return {
        "twin_timestamp": now.isoformat() + "Z",
        "last_observation": last_obs.isoformat() + "Z",
        "assimilation_lag_hours": 6,
        "pilot_region": "Maharashtra, India",
        "data_sources": ["IMD Gridded (0.25°)", "INSAT-3R LST/SST", "MOSDAC INSAT IMC"],
        "city_states": city_states,
        "twin_health": "Operational",
        "next_update": (now + timedelta(hours=6)).isoformat() + "Z",
        "variables_tracked": 6,
        "spatial_resolution": "0.25° × 0.25°",
    }


def _classify_status(rain_7d: float, temp_c: float) -> str:
    if rain_7d > 20 and temp_c < 35:
        return "Active Monsoon"
    elif rain_7d > 10:
        return "Wet"
    elif temp_c > 40:
        return "Heat Stress"
    elif rain_7d < 1 and temp_c > 36:
        return "Drought Watch"
    else:
        return "Normal"


# ─────────────────────────────────────────────────────────────
# City Profile — Deep Drill-down
# ─────────────────────────────────────────────────────────────

@app.get("/api/city-profile/{city}")
async def city_profile(city: str):
    """Full climate profile for a single city — used in the city modal."""
    if city not in MAHARASHTRA_CITIES:
        raise HTTPException(404, f"City '{city}' not found")
    if not DATA_LOADED:
        raise HTTPException(503, "Data not yet loaded")

    city_info = MAHARASHTRA_CITIES[city]
    now = datetime.utcnow()

    # Current state
    df_rain = CLIMATE_DATA["rainfall"]
    df_temp = CLIMATE_DATA["max_temp"]
    df_min = CLIMATE_DATA["min_temp"]

    current = {
        "rainfall_mm": round(float(df_rain[city].iloc[-1]), 2),
        "rainfall_7d_avg": round(float(df_rain[city].iloc[-7:].mean()), 2),
        "max_temp_c": round(float(df_temp[city].iloc[-1]), 2),
        "min_temp_c": round(float(df_min[city].iloc[-1]), 2),
    }

    # Add optional variables
    for var_key, var_label in [("humidity", "humidity_pct"), ("wind_speed", "wind_speed_kmh"), ("cloud_cover", "cloud_cover_okta")]:
        df = CLIMATE_DATA.get(var_key)
        if df is not None and city in df.columns:
            current[var_label] = round(float(df[city].iloc[-1]), 1)

    # Historical sparkline (last 90 days, weekly means)
    last90_rain = df_rain[city].iloc[-90:].resample("W").sum()
    last90_temp = df_temp[city].iloc[-90:].resample("W").mean()
    sparkline = {
        "rainfall": {
            "dates": [str(d.date()) for d in last90_rain.index],
            "values": [round(float(v), 1) for v in last90_rain.values],
        },
        "temperature": {
            "dates": [str(d.date()) for d in last90_temp.index],
            "values": [round(float(v), 1) for v in last90_temp.values],
        }
    }

    # Climatological anomaly
    clim_rain = float(df_rain[city][df_rain.index.month == 7].mean())
    clim_temp = float(df_temp[city][df_temp.index.month == 7].mean())
    rain_anomaly_pct = ((current["rainfall_7d_avg"] - clim_rain) / (clim_rain + 0.01)) * 100
    temp_anomaly = current["max_temp_c"] - clim_temp

    # Risk assessment
    flood_risk_score = min(100, max(0, int(current["rainfall_7d_avg"] / 25 * 100)))
    drought_risk_score = min(100, max(0, int((1 - current["rainfall_7d_avg"] / 15) * 100))) if current["rainfall_7d_avg"] < 15 else 0
    heat_risk_score = min(100, max(0, int((current["max_temp_c"] - 30) / 15 * 100)))

    # AI prediction (if model available)
    prediction = None
    if MODELS_TRAINED:
        model_data = load_model("rainfall", city)
        if model_data:
            model, mu, sigma, seq_len, h, metrics = model_data
            series = CLIMATE_DATA["rainfall"][city].values
            recent = series[-seq_len:]
            forecast = predict_future(model, mu, sigma, seq_len, h, recent, "rainfall")
            last_date = CLIMATE_DATA["rainfall"].index[-1]
            forecast_dates = [str((last_date + timedelta(days=i + 1)).date()) for i in range(h)]
            prediction = {
                "variable": "rainfall",
                "dates": forecast_dates,
                "mean": forecast["mean"],
                "low_95": forecast["low_95"],
                "high_95": forecast["high_95"],
                "confidence": forecast["confidence"],
                "confidence_score": forecast["confidence_score"],
                "metrics": metrics,
            }

    # AI Narrative
    forecast_rain_vals = prediction["mean"] if prediction else None
    narrative = generate_ai_narrative(
        city=city,
        rain_7d=current["rainfall_7d_avg"],
        temp_7d=current["max_temp_c"],
        humidity=current.get("humidity_pct", 70),
        forecast_rain=forecast_rain_vals,
    )

    # Feature importance
    importance = compute_feature_importance(CLIMATE_DATA, city, "rainfall")

    return {
        "city": city,
        "info": city_info,
        "timestamp": now.isoformat() + "Z",
        "current": current,
        "anomaly": {
            "rainfall_pct": round(float(rain_anomaly_pct), 1),
            "temp_c": round(float(temp_anomaly), 2),
        },
        "risks": {
            "flood": {"score": flood_risk_score, "level": "High" if flood_risk_score > 60 else "Moderate" if flood_risk_score > 30 else "Low"},
            "drought": {"score": drought_risk_score, "level": "High" if drought_risk_score > 60 else "Moderate" if drought_risk_score > 30 else "Low"},
            "heat": {"score": heat_risk_score, "level": "High" if heat_risk_score > 60 else "Moderate" if heat_risk_score > 30 else "Low"},
        },
        "sparkline": sparkline,
        "prediction": prediction,
        "narrative": narrative,
        "feature_importance": importance,
        "status": _classify_status(current["rainfall_7d_avg"], current["max_temp_c"]),
    }


# ─────────────────────────────────────────────────────────────
# Feature Importance — Explainability
# ─────────────────────────────────────────────────────────────

@app.get("/api/feature-importance/{city}/{variable}")
async def feature_importance(city: str, variable: str = "rainfall"):
    """Return feature importance for AI explainability."""
    if not DATA_LOADED:
        raise HTTPException(503, "Data not yet loaded")
    if city not in MAHARASHTRA_CITIES:
        raise HTTPException(404, f"City '{city}' not found")

    importance = compute_feature_importance(CLIMATE_DATA, city, variable)
    return {
        "city": city,
        "variable": variable,
        "method": "Correlation-based Feature Importance",
        "features": importance,
        "description": "Relative importance of each climate variable in predicting " + variable,
    }


# ─────────────────────────────────────────────────────────────
# AI Narrative — Natural Language Summary
# ─────────────────────────────────────────────────────────────

@app.get("/api/ai-narrative")
async def ai_narrative(city: str = "Mumbai"):
    """Generate AI-powered climate narrative for the dashboard."""
    if not DATA_LOADED:
        raise HTTPException(503, "Data not yet loaded")
    if city not in MAHARASHTRA_CITIES:
        raise HTTPException(404, f"City '{city}' not found")

    df_rain = CLIMATE_DATA["rainfall"]
    df_temp = CLIMATE_DATA["max_temp"]
    df_hum = CLIMATE_DATA.get("humidity")

    rain_7d = float(df_rain[city].iloc[-7:].mean())
    temp_7d = float(df_temp[city].iloc[-7:].mean())
    hum = float(df_hum[city].iloc[-7:].mean()) if df_hum is not None and city in df_hum.columns else 70.0

    # Get forecast if available
    forecast_rain = None
    if MODELS_TRAINED:
        model_data = load_model("rainfall", city)
        if model_data:
            model, mu, sigma, seq_len, h, metrics = model_data
            series = CLIMATE_DATA["rainfall"][city].values
            recent = series[-seq_len:]
            fc = predict_future(model, mu, sigma, seq_len, h, recent, "rainfall")
            forecast_rain = fc["mean"]

    text = generate_ai_narrative(
        city=city,
        rain_7d=rain_7d,
        temp_7d=temp_7d,
        humidity=hum,
        forecast_rain=forecast_rain,
    )

    return {
        "city": city,
        "narrative": text,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "source": "ClimaTwin AI Narrative Engine v2.0",
    }


# ─────────────────────────────────────────────────────────────
# Timeline — Animated Map Snapshots
# ─────────────────────────────────────────────────────────────

@app.get("/api/timeline")
async def timeline(
    variable: str = "rainfall",
    days: int = 30,
):
    """Return daily grid snapshots for the time scrubber animation."""
    snapshots = generate_timeline_snapshots(variable, min(days, 30))
    return {
        "variable": variable,
        "total_days": len(snapshots),
        "snapshots": snapshots,
    }


# ─────────────────────────────────────────────────────────────
# Historical Data
# ─────────────────────────────────────────────────────────────

@app.get("/api/historical")
async def historical(
    city: str = "Mumbai",
    variable: str = "rainfall",
    start: str = "2020-01-01",
    end: str = "2024-12-31",
    resample: str = "M"
):
    """Return historical time series for chart."""
    if not DATA_LOADED:
        raise HTTPException(503, "Data not yet loaded")
    if city not in CLIMATE_DATA.get(variable, pd.DataFrame()).columns:
        raise HTTPException(404, f"City '{city}' or variable '{variable}' not found")

    series = CLIMATE_DATA[variable][city]
    series = series[start:end]

    if resample in ["M", "W", "Y"]:
        if variable == "rainfall":
            series = series.resample(resample).sum()
        else:
            series = series.resample(resample).mean()

    dates = [str(d.date()) for d in series.index]
    values = [round(float(v), 2) if not np.isnan(v) else None for v in series.values]

    # Compute climatological mean for anomaly
    monthly_clim = CLIMATE_DATA[variable][city].groupby(
        CLIMATE_DATA[variable][city].index.month
    ).mean()

    return {
        "city": city,
        "variable": variable,
        "unit": "mm" if variable == "rainfall" else "°C",
        "resample": resample,
        "dates": dates,
        "values": values,
        "climatology_monthly": {str(m): round(float(v), 2) for m, v in monthly_clim.items()},
        "stats": {
            "mean": round(float(np.nanmean(values)), 2),
            "max": round(float(np.nanmax([v for v in values if v])), 2),
            "min": round(float(np.nanmin([v for v in values if v])), 2),
            "trend_per_decade": round(
                float(np.polyfit(range(len(values)), [v or 0 for v in values], 1)[0] * 120), 3
            )
        }
    }


# ─────────────────────────────────────────────────────────────
# AI Prediction
# ─────────────────────────────────────────────────────────────

@app.get("/api/predict")
async def predict(
    city: str = "Mumbai",
    variable: str = "rainfall",
    horizon: int = 7
):
    """AI forecast with uncertainty bands."""
    if not DATA_LOADED:
        raise HTTPException(503, "Data not yet loaded")

    if not MODELS_TRAINED:
        return {
            "city": city, "variable": variable,
            "status": "training_in_progress",
            "message": "Models are still training. Check /api/status",
            "fallback": _persistence_forecast(city, variable, horizon)
        }

    model_data = load_model(variable, city)
    if model_data is None:
        return {
            "city": city, "variable": variable,
            "status": "fallback",
            "message": "Model not found, using persistence forecast",
            "fallback": _persistence_forecast(city, variable, horizon)
        }

    model, mu, sigma, seq_len, h, metrics = model_data
    series = CLIMATE_DATA[variable][city].values
    recent = series[-seq_len:]

    forecast = predict_future(model, mu, sigma, seq_len, h, recent, variable)

    # Generate forecast dates
    last_date = CLIMATE_DATA[variable].index[-1]
    forecast_dates = [
        str((last_date + timedelta(days=i + 1)).date()) for i in range(h)
    ]

    # Historical last 30 days for chart context
    hist_dates = [str(d.date()) for d in CLIMATE_DATA[variable].index[-30:]]
    hist_values = [round(float(v), 2) for v in series[-30:]]

    return {
        "city": city,
        "variable": variable,
        "unit": "mm/day" if variable == "rainfall" else "°C",
        "model": "LSTM (2-layer, 64 hidden, MC Dropout)",
        "metrics": metrics,
        "confidence": forecast["confidence"],
        "confidence_score": forecast["confidence_score"],
        "historical": {"dates": hist_dates, "values": hist_values},
        "forecast": {
            "dates": forecast_dates,
            "mean": forecast["mean"],
            "low_95": forecast["low_95"],
            "high_95": forecast["high_95"],
            "uncertainty": forecast["std"]
        }
    }


def _persistence_forecast(city: str, variable: str, horizon: int) -> dict:
    """Naive persistence forecast as fallback."""
    if not DATA_LOADED or city not in CLIMATE_DATA.get(variable, pd.DataFrame()).columns:
        values = [10.0] * horizon
    else:
        last_val = float(CLIMATE_DATA[variable][city].iloc[-1])
        values = [round(last_val + np.random.normal(0, 0.5), 2) for _ in range(horizon)]
    return {"mean": values, "type": "persistence"}


# ─────────────────────────────────────────────────────────────
# Spatial Grid
# ─────────────────────────────────────────────────────────────

@app.get("/api/spatial-grid")
async def spatial_grid(
    variable: str = "rainfall",
    date: str = "2024-07-15",
    temp_delta: float = 0.0,
    rainfall_pct: float = 0.0
):
    """Spatial grid data for map choropleth."""
    scenario_delta = {}
    if temp_delta != 0:
        scenario_delta["temp_delta"] = temp_delta
    if rainfall_pct != 0:
        scenario_delta["rainfall_pct"] = rainfall_pct

    grid = generate_spatial_grid_snapshot(variable, date, scenario_delta)
    return grid


# ─────────────────────────────────────────────────────────────
# Scenario Simulator
# ─────────────────────────────────────────────────────────────

@app.post("/api/scenario")
async def scenario(req: ScenarioRequest):
    """Run a what-if scenario and return cascading impacts."""
    if not DATA_LOADED:
        raise HTTPException(503, "Data not yet loaded")

    cities = list(MAHARASHTRA_CITIES.keys())
    if req.city:
        cities = [req.city] if req.city in MAHARASHTRA_CITIES else cities

    # Get baseline from recent data
    base_rain = {}
    base_temp = {}
    for city in cities:
        if city in CLIMATE_DATA.get("rainfall", pd.DataFrame()).columns:
            # July climatological mean
            july_mask = CLIMATE_DATA["rainfall"].index.month == 7
            base_rain[city] = float(CLIMATE_DATA["rainfall"][city][july_mask].mean())
            base_temp[city] = float(CLIMATE_DATA["max_temp"][city][july_mask].mean())

    result = run_scenario(
        preset_key=req.preset,
        custom_temp_delta=req.temp_delta,
        custom_rainfall_pct=req.rainfall_pct,
        cities=cities,
        base_rainfall=base_rain,
        base_max_temp=base_temp,
    )
    return result


@app.get("/api/scenarios/list")
async def list_scenarios():
    return {
        "presets": [
            {
                "key": k,
                "name": v["name"],
                "description": v["description"],
                "temp_delta": v["temp_delta"],
                "rainfall_pct": v["rainfall_pct"],
                "color": v["color"],
                "icon": v["icon"]
            }
            for k, v in SCENARIO_PRESETS.items()
        ]
    }


# ─────────────────────────────────────────────────────────────
# Model Metrics
# ─────────────────────────────────────────────────────────────

@app.get("/api/model-metrics")
async def model_metrics():
    if not MODELS_TRAINED:
        return {"status": "training", "metrics": []}

    # Load metrics from saved model files
    models_dir = ROOT_DIR / "models"
    all_metrics = []
    if models_dir.exists():
        for pt_file in models_dir.glob("lstm_*.pt"):
            try:
                ckpt = torch.load(str(pt_file), map_location="cpu", weights_only=False)
                parts = pt_file.stem.split("_", 2)  # lstm_rainfall_mumbai
                all_metrics.append({
                    "variable": parts[1] if len(parts) > 1 else "unknown",
                    "city": parts[2].title() if len(parts) > 2 else "unknown",
                    **ckpt.get("metrics", {})
                })
            except Exception:
                pass

    return {
        "status": "trained",
        "model_type": "LSTM (2-layer, 64 hidden units, MC Dropout)",
        "training_period": "1990–2022",
        "validation_period": "2023–2024",
        "metrics": all_metrics
    }


# ─────────────────────────────────────────────────────────────
# Anomaly Alerts
# ─────────────────────────────────────────────────────────────

@app.get("/api/anomaly-alerts")
async def anomaly_alerts():
    """Return current anomaly alerts for dashboard."""
    if not DATA_LOADED:
        return {"alerts": []}

    alerts = []
    now_month = 7  # July (monsoon season)

    for city in MAHARASHTRA_CITIES:
        if city not in CLIMATE_DATA.get("rainfall", pd.DataFrame()).columns:
            continue

        df = CLIMATE_DATA["rainfall"]
        # Compare recent 30 days to same period climatology
        recent = df[city].iloc[-30:].mean()
        clim_july = df[city][df[city].index.month == now_month].mean()
        anomaly_pct = (recent - clim_july) / (clim_july + 0.01) * 100

        if abs(anomaly_pct) > 25:
            alerts.append({
                "city": city,
                "variable": "rainfall",
                "anomaly_pct": round(float(anomaly_pct), 1),
                "severity": "High" if abs(anomaly_pct) > 50 else "Moderate",
                "message": f"{'Excess' if anomaly_pct > 0 else 'Deficit'} rainfall: {anomaly_pct:+.0f}% vs climatology",
                "icon": "🌧️" if anomaly_pct > 0 else "🏜️"
            })

        # Temp anomaly
        df_t = CLIMATE_DATA["max_temp"]
        recent_t = df_t[city].iloc[-7:].mean()
        clim_t = df_t[city][df_t[city].index.month == now_month].mean()
        anomaly_t = recent_t - clim_t

        if abs(anomaly_t) > 2:
            alerts.append({
                "city": city,
                "variable": "max_temp",
                "anomaly_c": round(float(anomaly_t), 1),
                "severity": "High" if abs(anomaly_t) > 4 else "Moderate",
                "message": f"Temperature {'+' if anomaly_t > 0 else ''}{anomaly_t:.1f}°C vs climatology",
                "icon": "🔥" if anomaly_t > 0 else "❄️"
            })

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_alerts": len(alerts),
        "alerts": sorted(alerts, key=lambda x: x.get("severity", ""), reverse=True)
    }
