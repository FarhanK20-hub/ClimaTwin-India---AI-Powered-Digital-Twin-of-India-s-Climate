"""
What-If Scenario Simulation Engine
────────────────────────────────────
Allows users to perturb climate inputs and see cascading effects.
Scenarios:
  - Temperature delta (°C)
  - Rainfall % change
  - El Niño / La Niña modes
  - Drought intensification
  - Extreme heat wave
  - Monsoon delay / advance
  - Urban heat island effects
"""

import numpy as np
from typing import Dict, Any, List
from backend.model import compute_water_stress_index, compute_crop_yield_impact, compute_river_discharge_change
from backend.preprocess import MAHARASHTRA_CITIES, MAHARASHTRA_RIVERS, MAHARASHTRA_RESERVOIRS


SCENARIO_PRESETS = {
    "normal": {
        "name": "Normal Conditions",
        "description": "Long-term climatological average (baseline)",
        "temp_delta": 0.0,
        "rainfall_pct": 0,
        "duration_days": 30,
        "color": "#2ECC71",
        "icon": "🌿"
    },
    "el_nino": {
        "name": "El Niño 2015-like",
        "description": "Strong El Niño event causing below-normal monsoon rainfall",
        "temp_delta": +0.8,
        "rainfall_pct": -35,
        "duration_days": 90,
        "color": "#FF6B35",
        "icon": "🌡️"
    },
    "la_nina": {
        "name": "La Niña Event",
        "description": "La Niña causing above-normal rainfall and flood risk",
        "temp_delta": -0.3,
        "rainfall_pct": +40,
        "duration_days": 90,
        "color": "#4ECDC4",
        "icon": "🌧️"
    },
    "heat_wave": {
        "name": "Extreme Heat Wave",
        "description": "Severe heat wave scenario (+4°C) — similar to 2015 Andhra Pradesh event",
        "temp_delta": +4.0,
        "rainfall_pct": -15,
        "duration_days": 14,
        "color": "#FF3366",
        "icon": "🔥"
    },
    "drought": {
        "name": "Severe Drought",
        "description": "Prolonged drought with −60% rainfall — impact on Marathwada region",
        "temp_delta": +1.5,
        "rainfall_pct": -60,
        "duration_days": 120,
        "color": "#8B4513",
        "icon": "🏜️"
    },
    "monsoon_delay": {
        "name": "Delayed Monsoon Onset",
        "description": "Monsoon onset delayed by 2 weeks — critical for Kharif sowing",
        "temp_delta": +1.2,
        "rainfall_pct": -40,
        "duration_days": 45,
        "color": "#6366F1",
        "icon": "⏳"
    },
    "rcp45": {
        "name": "RCP 4.5 — 2050 Projection",
        "description": "Mid-century climate scenario under moderate emissions",
        "temp_delta": +1.8,
        "rainfall_pct": +10,
        "duration_days": 365,
        "color": "#F39C12",
        "icon": "📈"
    },
    "rcp85": {
        "name": "RCP 8.5 — 2050 Worst Case",
        "description": "High-emissions scenario with severe warming",
        "temp_delta": +3.2,
        "rainfall_pct": -20,
        "duration_days": 365,
        "color": "#C0392B",
        "icon": "⚠️"
    }
}

# Urban Heat Island Effect per city (°C addition)
URBAN_HEAT_ISLAND = {
    "Mumbai": 2.5,    # Dense urban, coastal
    "Pune": 1.8,
    "Nagpur": 2.2,    # Inland, concrete heavy
    "Nashik": 1.2,
    "Aurangabad": 1.5,
    "Solapur": 1.0,
    "Kolhapur": 0.8,
}


def run_scenario(
    preset_key: str = "normal",
    custom_temp_delta: float = None,
    custom_rainfall_pct: float = None,
    cities: List[str] = None,
    base_rainfall: Dict[str, float] = None,
    base_max_temp: Dict[str, float] = None,
) -> Dict[str, Any]:
    """
    Simulate climate perturbation and return cascading impact metrics.
    """
    if cities is None:
        cities = ["Mumbai", "Pune", "Nagpur", "Nashik", "Aurangabad", "Solapur", "Kolhapur"]

    preset = SCENARIO_PRESETS.get(preset_key, SCENARIO_PRESETS["normal"])
    temp_delta = custom_temp_delta if custom_temp_delta is not None else preset["temp_delta"]
    rain_pct = custom_rainfall_pct if custom_rainfall_pct is not None else preset["rainfall_pct"]

    # Default baseline values if not provided (July climatological means)
    if base_rainfall is None:
        base_rainfall = {
            "Mumbai": 18.5, "Pune": 10.2, "Nagpur": 12.0,
            "Nashik": 9.8, "Aurangabad": 7.5, "Solapur": 5.2, "Kolhapur": 14.3
        }
    if base_max_temp is None:
        base_max_temp = {
            "Mumbai": 32.1, "Pune": 30.5, "Nagpur": 36.8,
            "Nashik": 31.2, "Aurangabad": 34.5, "Solapur": 35.0, "Kolhapur": 30.8
        }

    city_impacts = {}
    for city in cities:
        br = base_rainfall.get(city, 10.0)
        bt = base_max_temp.get(city, 32.0)
        uhi = URBAN_HEAT_ISLAND.get(city, 1.0)

        perturbed_rain = max(0, br * (1 + rain_pct / 100))
        # Include urban heat island effect for temperature
        perturbed_temp = bt + temp_delta + (uhi * 0.3 if temp_delta > 0 else 0)

        wsi = compute_water_stress_index(rain_pct, temp_delta)
        crops = ["rice", "wheat", "sugarcane"] if city in ["Pune", "Kolhapur", "Nashik"] else \
                ["cotton", "wheat", "rice"]

        crop_impacts = {c: compute_crop_yield_impact(rain_pct, temp_delta, c) for c in crops}

        flood_risk = _flood_risk(perturbed_rain, br)
        drought_risk = _drought_risk(rain_pct, temp_delta)
        heat_stress = _heat_stress_index(perturbed_temp)

        # River discharge for cities on major rivers
        city_info = MAHARASHTRA_CITIES.get(city, {})
        river_name = city_info.get("river", "")
        river_impact = None
        for r_name, r_data in MAHARASHTRA_RIVERS.items():
            if city in r_data["cities"]:
                river_impact = compute_river_discharge_change(rain_pct, temp_delta, r_name)
                break

        city_impacts[city] = {
            "perturbed_rainfall_mm": round(perturbed_rain, 2),
            "perturbed_temp_c": round(perturbed_temp, 2),
            "urban_heat_island_c": round(uhi, 1),
            "water_stress_index_pct": wsi,
            "flood_risk": flood_risk,
            "drought_risk": drought_risk,
            "heat_stress": heat_stress,
            "crop_impacts": crop_impacts,
            "river_impact": river_impact,
            "alerts": _generate_alerts(flood_risk, drought_risk, heat_stress, city)
        }

    # Aggregate state-level metrics
    all_rain_pct_change = [city_impacts[c]["water_stress_index_pct"] for c in cities]
    all_flood = [city_impacts[c]["flood_risk"]["level"] for c in cities]
    all_drought = [city_impacts[c]["drought_risk"]["level"] for c in cities]

    # Agricultural GDP impact proxy
    agri_gdp_impact = _estimate_agri_gdp_impact(rain_pct, temp_delta)

    # Reservoir storage impact (Maharashtra has Jayakwadi, Koyna, Ujani)
    reservoir_impact = _reservoir_impact(rain_pct)

    # Reservoir-level detail
    reservoir_details = {}
    for res_name, res_data in MAHARASHTRA_RESERVOIRS.items():
        current_pct = 65  # Assume 65% full baseline (typical July)
        change = rain_pct * 0.6  # 60% efficiency
        projected_pct = max(0, min(100, current_pct + change * 0.5))
        reservoir_details[res_name] = {
            "capacity_mcm": res_data["capacity_mcm"],
            "baseline_pct": current_pct,
            "projected_pct": round(projected_pct, 1),
            "river": res_data["river"],
            "status": "Critical" if projected_pct < 25 else "Low" if projected_pct < 40 else "Normal" if projected_pct < 80 else "Flood Risk"
        }

    return {
        "scenario": {
            "key": preset_key,
            "name": preset["name"],
            "description": preset["description"],
            "temp_delta": temp_delta,
            "rainfall_pct": rain_pct,
            "color": preset["color"],
            "icon": preset["icon"]
        },
        "city_impacts": city_impacts,
        "state_summary": {
            "avg_water_stress_pct": round(float(np.mean(all_rain_pct_change)), 1),
            "max_flood_risk": max(all_flood, key=lambda x: ["Low", "Moderate", "High", "Extreme"].index(x)),
            "max_drought_risk": max(all_drought, key=lambda x: ["Low", "Moderate", "High", "Extreme"].index(x)),
            "agri_gdp_impact_pct": agri_gdp_impact,
            "reservoir_storage_change_pct": reservoir_impact,
            "population_at_risk": _population_at_risk(rain_pct, temp_delta),
            "reservoir_details": reservoir_details,
        },
        "recommendations": _generate_recommendations(preset_key, rain_pct, temp_delta)
    }


def _flood_risk(perturbed_rain: float, base_rain: float) -> Dict:
    ratio = perturbed_rain / (base_rain + 0.1)
    if ratio > 2.5:
        level, score = "Extreme", 95
    elif ratio > 1.8:
        level, score = "High", 70
    elif ratio > 1.3:
        level, score = "Moderate", 45
    else:
        level, score = "Low", 15
    return {"level": level, "score": score}


def _drought_risk(rain_pct: float, temp_delta: float) -> Dict:
    # Combine rainfall deficit and heat
    spi_proxy = -rain_pct / 30 + temp_delta / 2
    if spi_proxy > 3:
        level, score = "Extreme", 90
    elif spi_proxy > 2:
        level, score = "High", 65
    elif spi_proxy > 0.5:
        level, score = "Moderate", 40
    else:
        level, score = "Low", 10
    return {"level": level, "score": score}


def _heat_stress_index(temp_c: float) -> Dict:
    if temp_c >= 45:
        level, score = "Extreme", 100
    elif temp_c >= 40:
        level, score = "High", 75
    elif temp_c >= 35:
        level, score = "Moderate", 50
    else:
        level, score = "Low", 20
    return {"level": level, "score": score, "temp_c": round(temp_c, 1)}


def _generate_alerts(flood, drought, heat, city) -> List[str]:
    alerts = []
    if flood["level"] in ["High", "Extreme"]:
        alerts.append(f"⚠️ High flood risk in {city} — activate early warning systems")
    if drought["level"] in ["High", "Extreme"]:
        alerts.append(f"🏜️ Drought conditions developing in {city} — water rationing advised")
    if heat["level"] in ["High", "Extreme"]:
        alerts.append(f"🔥 Dangerous heat levels in {city} — public health advisory")
    return alerts


def _estimate_agri_gdp_impact(rain_pct: float, temp_delta: float) -> float:
    """Maharashtra agriculture GDP ~₹3.5 lakh crore; proxy % impact."""
    rain_effect = rain_pct * 0.25  # 25% sensitivity
    temp_effect = -temp_delta * 3.0  # Each °C costs ~3% yield
    total = round(float(rain_effect + temp_effect), 1)
    return max(-50, min(20, total))


def _reservoir_impact(rain_pct: float) -> float:
    """Proxy: reservoir storage change from normal monsoon fill."""
    return round(float(rain_pct * 0.8), 1)  # 80% efficiency of rainfall → storage


def _population_at_risk(rain_pct: float, temp_delta: float) -> str:
    """Estimate population at risk (millions) in Maharashtra."""
    base_risk = 0
    if rain_pct < -30:
        base_risk += 8  # drought-prone Marathwada
    if rain_pct > 50:
        base_risk += 5  # flood-prone coastal regions
    if temp_delta > 3:
        base_risk += 12  # urban heat island
    elif temp_delta > 1.5:
        base_risk += 4
    return f"~{base_risk}M people" if base_risk > 0 else "Minimal additional risk"


def _generate_recommendations(preset_key: str, rain_pct: float, temp_delta: float) -> List[str]:
    recs = []
    if rain_pct < -20:
        recs.append("📊 Activate drought monitoring via IMD MAWS network")
        recs.append("💧 Pre-position water tankers in Marathwada & Vidarbha districts")
        recs.append("🌾 Advisory to farmers: switch to drought-resistant crop varieties")
    if rain_pct > 30:
        recs.append("🚨 Issue flood alerts for Konkan coast and river basins")
        recs.append("🏗️ Open flood relief camps in low-lying urban areas")
        recs.append("📡 Enhance INSAT satellite monitoring for cloud burst detection")
    if temp_delta > 2:
        recs.append("🏥 Issue heat wave public health advisory")
        recs.append("💦 Increase urban water supply frequency")
        recs.append("⚡ Pre-position emergency power for grid load balancing")
    if preset_key == "monsoon_delay":
        recs.append("🌱 Delay Kharif crop sowing — advisory for cotton & soybean farmers")
        recs.append("💧 Implement water rationing in rain-dependent districts")
        recs.append("📡 Intensify INSAT-3R monitoring for monsoon onset signals")
    if not recs:
        recs.append("✅ Conditions within normal range — routine monitoring sufficient")
        recs.append("📈 Continue data assimilation for Digital Twin state update")
    return recs


def generate_ai_narrative(
    city: str,
    rain_7d: float,
    temp_7d: float,
    humidity: float = 70.0,
    forecast_rain: list = None,
    forecast_temp: list = None,
    scenario_key: str = None,
) -> str:
    """Generate a natural language climate narrative for the dashboard."""
    parts = []

    # Current state narrative
    if rain_7d > 20:
        parts.append(f"Heavy rainfall activity ({rain_7d:.1f} mm/day avg) is being observed over {city} and surrounding districts, consistent with active monsoon conditions.")
    elif rain_7d > 10:
        parts.append(f"Moderate rainfall ({rain_7d:.1f} mm/day avg) continues over {city}, indicating normal monsoon progression.")
    elif rain_7d > 2:
        parts.append(f"Light rainfall ({rain_7d:.1f} mm/day avg) is recorded in {city}. Monsoon activity is below seasonal expectations.")
    else:
        parts.append(f"Dry conditions prevail over {city} with minimal rainfall ({rain_7d:.1f} mm/day avg). This is unusual for the monsoon season.")

    # Temperature narrative
    if temp_7d > 40:
        parts.append(f"Temperatures remain elevated at {temp_7d:.1f}°C, indicating heat stress conditions. Urban heat island effects may amplify this further.")
    elif temp_7d > 35:
        parts.append(f"Maximum temperature of {temp_7d:.1f}°C is above comfort levels.")
    else:
        parts.append(f"Temperature of {temp_7d:.1f}°C remains within the normal monsoon-season range.")

    # Humidity
    if humidity > 85:
        parts.append(f"Humidity is very high at {humidity:.0f}%, creating oppressive conditions.")
    elif humidity > 70:
        parts.append(f"Relative humidity at {humidity:.0f}% supports continued moisture availability.")

    # Forecast outlook
    if forecast_rain:
        avg_fc = np.mean(forecast_rain)
        max_fc = max(forecast_rain)
        if max_fc > 30:
            parts.append(f"⚠️ The LSTM model predicts heavy rainfall events (peak ~{max_fc:.0f} mm/day) in the coming days. Flood preparedness is advised for low-lying areas.")
        elif avg_fc > 15:
            parts.append(f"The AI forecast indicates continued active monsoon with average {avg_fc:.1f} mm/day expected over the next 7 days.")
        elif avg_fc < 3:
            parts.append("A dry spell is forecast for the coming week. Water conservation measures may be needed in rain-dependent regions.")

    if forecast_temp:
        max_t = max(forecast_temp)
        if max_t > 42:
            parts.append(f"🔥 Temperature is expected to reach {max_t:.1f}°C. A heat wave advisory should be considered.")

    # Scenario context
    if scenario_key and scenario_key != "normal":
        preset = SCENARIO_PRESETS.get(scenario_key, {})
        if preset:
            parts.append(f"Under the {preset['name']} scenario, these conditions would be {'intensified' if preset.get('temp_delta', 0) > 0 else 'moderated'} further.")

    return " ".join(parts)
