"""
AI Models for Climate Digital Twin
──────────────────────────────────
1. LSTM  – univariate time-series forecasting per city
2. ConvLSTM cell – spatial forecasting architecture
3. Feature importance – permutation-based explainability
4. Confidence classification – MC Dropout uncertainty bands
"""

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler
from pathlib import Path
import json
import os

MODELS_DIR = Path(__file__).parent.parent / "models"
MODELS_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────
# LSTM Architecture
# ─────────────────────────────────────────────────────────────

class ClimateISTM(nn.Module):
    """Lightweight LSTM for daily climate variable forecasting."""
    def __init__(self, input_size: int = 1, hidden_size: int = 64,
                 num_layers: int = 2, dropout: float = 0.2, horizon: int = 7):
        super().__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        self.horizon = horizon
        self.lstm = nn.LSTM(
            input_size, hidden_size, num_layers,
            batch_first=True, dropout=dropout
        )
        self.bn = nn.BatchNorm1d(hidden_size)
        self.fc = nn.Linear(hidden_size, horizon)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        out = out[:, -1, :]  # Last time step
        out = self.bn(out)
        return self.fc(out)


class ConvLSTMCell(nn.Module):
    """Single ConvLSTM cell for spatial forecasting."""
    def __init__(self, in_ch: int, h_ch: int, kernel_size: int = 3):
        super().__init__()
        pad = kernel_size // 2
        self.h_ch = h_ch
        self.gates = nn.Conv2d(in_ch + h_ch, 4 * h_ch, kernel_size, padding=pad)

    def forward(self, x, h_prev, c_prev):
        combined = torch.cat([x, h_prev], dim=1)
        gates = self.gates(combined)
        i, f, o, g = gates.chunk(4, dim=1)
        c = torch.sigmoid(f) * c_prev + torch.sigmoid(i) * torch.tanh(g)
        h = torch.sigmoid(o) * torch.tanh(c)
        return h, c

    def init_hidden(self, batch, H, W, device):
        return (torch.zeros(batch, self.h_ch, H, W, device=device),
                torch.zeros(batch, self.h_ch, H, W, device=device))


# ─────────────────────────────────────────────────────────────
# Training & Inference Helpers
# ─────────────────────────────────────────────────────────────

def prepare_sequences(series: np.ndarray, seq_len: int = 30, horizon: int = 7):
    X, y = [], []
    for i in range(len(series) - seq_len - horizon + 1):
        X.append(series[i: i + seq_len])
        y.append(series[i + seq_len: i + seq_len + horizon])
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def train_lstm(
    series: np.ndarray,
    variable: str = "rainfall",
    city: str = "Mumbai",
    seq_len: int = 30,
    horizon: int = 7,
    epochs: int = 40,
    lr: float = 1e-3,
    batch_size: int = 64,
    device: str = "cpu"
) -> dict:
    """Train LSTM on a climate time series. Returns metrics + model path."""
    # Normalize
    mu, sigma = float(np.nanmean(series)), float(np.nanstd(series) + 1e-6)
    norm = (series - mu) / sigma
    norm = np.nan_to_num(norm, nan=0.0)

    X, y = prepare_sequences(norm, seq_len, horizon)
    split = int(0.85 * len(X))
    X_tr, X_val = X[:split], X[split:]
    y_tr, y_val = y[:split], y[split:]

    X_tr_t = torch.tensor(X_tr).unsqueeze(-1)
    y_tr_t = torch.tensor(y_tr)
    X_val_t = torch.tensor(X_val).unsqueeze(-1)
    y_val_t = torch.tensor(y_val)

    loader = DataLoader(TensorDataset(X_tr_t, y_tr_t), batch_size=batch_size, shuffle=True)

    model = ClimateISTM(input_size=1, hidden_size=64, num_layers=2, horizon=horizon).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, epochs)
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    best_state = None

    model.train()
    for epoch in range(epochs):
        epoch_loss = 0
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            pred = model(xb)
            loss = criterion(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            epoch_loss += loss.item()
        scheduler.step()

        # Validation
        model.eval()
        with torch.no_grad():
            val_pred = model(X_val_t.to(device))
            val_loss = criterion(val_pred, y_val_t.to(device)).item()
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
        model.train()

    # Load best weights
    model.load_state_dict(best_state)
    model.eval()

    # Compute metrics in original scale
    with torch.no_grad():
        val_pred_np = model(X_val_t.to(device)).cpu().numpy()
    val_pred_denorm = val_pred_np * sigma + mu
    val_true_denorm = y_val * sigma + mu
    if variable == "rainfall":
        val_pred_denorm = np.maximum(val_pred_denorm, 0)
        val_true_denorm = np.maximum(val_true_denorm, 0)

    flat_pred = val_pred_denorm.flatten()
    flat_true = val_true_denorm.flatten()
    mae = float(mean_absolute_error(flat_true, flat_pred))
    rmse = float(np.sqrt(mean_squared_error(flat_true, flat_pred)))

    # Persistence baseline (naive forecast = last value)
    persist_pred = np.repeat(X_val[:, -1:], horizon, axis=1) * sigma + mu
    persist_mae = float(mean_absolute_error(flat_true, persist_pred.flatten()))
    skill_score = float(1 - mae / (persist_mae + 1e-6))

    # Save model
    save_path = MODELS_DIR / f"lstm_{variable}_{city.lower()}.pt"
    torch.save({
        "state_dict": best_state,
        "mu": mu, "sigma": sigma,
        "seq_len": seq_len, "horizon": horizon,
        "metrics": {"mae": mae, "rmse": rmse, "skill_score": skill_score}
    }, save_path)

    return {
        "city": city, "variable": variable,
        "mae": round(mae, 3), "rmse": round(rmse, 3),
        "skill_score": round(skill_score, 3),
        "val_loss": round(best_val_loss, 5),
        "model_path": str(save_path)
    }


def load_model(variable: str, city: str, device: str = "cpu"):
    """Load saved LSTM model and return (model, mu, sigma, seq_len, horizon)."""
    path = MODELS_DIR / f"lstm_{variable}_{city.lower()}.pt"
    if not path.exists():
        return None
    ckpt = torch.load(path, map_location=device, weights_only=False)
    model = ClimateISTM(
        input_size=1, hidden_size=64, num_layers=2,
        horizon=ckpt["horizon"]
    ).to(device)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model, ckpt["mu"], ckpt["sigma"], ckpt["seq_len"], ckpt["horizon"], ckpt["metrics"]


def predict_future(
    model, mu: float, sigma: float, seq_len: int, horizon: int,
    recent_data: np.ndarray, variable: str = "rainfall",
    device: str = "cpu", n_samples: int = 50
) -> dict:
    """
    Monte Carlo Dropout forecast → returns mean + uncertainty bands.
    recent_data: last `seq_len` days of observations.
    """
    norm = (recent_data[-seq_len:] - mu) / sigma
    norm = np.nan_to_num(norm, nan=0.0).astype(np.float32)
    x_t = torch.tensor(norm).unsqueeze(0).unsqueeze(-1).to(device)

    # Enable MC dropout for uncertainty
    def enable_dropout(m):
        if isinstance(m, nn.Dropout):
            m.train()

    model.eval()
    model.apply(enable_dropout)

    preds = []
    with torch.no_grad():
        for _ in range(n_samples):
            out = model(x_t).cpu().numpy()[0]
            preds.append(out * sigma + mu)

    preds = np.array(preds)
    if variable == "rainfall":
        preds = np.maximum(preds, 0)

    mean_pred = preds.mean(axis=0)
    std_pred = preds.std(axis=0)
    low_95 = mean_pred - 1.96 * std_pred
    high_95 = mean_pred + 1.96 * std_pred
    if variable == "rainfall":
        low_95 = np.maximum(low_95, 0)

    # Confidence classification
    avg_std = float(np.mean(std_pred))
    rel_uncertainty = avg_std / (float(np.mean(np.abs(mean_pred))) + 1e-6)
    if rel_uncertainty < 0.15:
        confidence = "High"
        confidence_score = 95 - rel_uncertainty * 100
    elif rel_uncertainty < 0.35:
        confidence = "Medium"
        confidence_score = 75 - (rel_uncertainty - 0.15) * 100
    else:
        confidence = "Low"
        confidence_score = max(30, 55 - (rel_uncertainty - 0.35) * 100)

    return {
        "mean": [round(float(v), 2) for v in mean_pred],
        "low_95": [round(float(v), 2) for v in low_95],
        "high_95": [round(float(v), 2) for v in high_95],
        "std": [round(float(v), 2) for v in std_pred],
        "confidence": confidence,
        "confidence_score": round(float(confidence_score), 1),
    }


# ─────────────────────────────────────────────────────────────
# Feature Importance (Permutation-based)
# ─────────────────────────────────────────────────────────────

def compute_feature_importance(
    climate_data: dict,
    city: str,
    variable: str = "rainfall",
) -> dict:
    """
    Compute approximate feature importance for a city's prediction.
    Uses correlation-based importance as a fast proxy.
    Returns dict of feature_name → importance_score.
    """
    target = climate_data.get(variable)
    if target is None or city not in target.columns:
        return {}

    target_series = target[city].values
    importances = {}

    # Features: all other variables for this city
    feature_map = {
        "rainfall": ("Previous Rainfall", "rainfall"),
        "max_temp": ("Max Temperature", "max_temp"),
        "min_temp": ("Min Temperature", "min_temp"),
        "humidity": ("Humidity", "humidity"),
        "wind_speed": ("Wind Speed", "wind_speed"),
        "cloud_cover": ("Cloud Cover", "cloud_cover"),
    }

    for label, (display_name, var_key) in feature_map.items():
        df = climate_data.get(var_key)
        if df is None or city not in df.columns:
            continue
        feat_series = df[city].values
        # Use rolling correlation (last 365 days)
        n = min(365, len(target_series))
        t_recent = target_series[-n:]
        f_recent = feat_series[-n:]
        # Remove NaN
        mask = ~(np.isnan(t_recent) | np.isnan(f_recent))
        if mask.sum() < 30:
            continue
        corr = np.abs(np.corrcoef(t_recent[mask], f_recent[mask])[0, 1])
        importances[display_name] = round(float(corr), 3)

    # Add temporal features
    doy = np.array([d.dayofyear for d in target.index[-365:]])
    mask = ~np.isnan(target_series[-365:])
    if mask.sum() > 30:
        corr_doy = np.abs(np.corrcoef(
            np.sin(2 * np.pi * doy[mask] / 365),
            target_series[-365:][mask]
        )[0, 1])
        importances["Seasonality (Day of Year)"] = round(float(corr_doy), 3)

    # ENSO proxy (6-year cycle)
    years = np.array([d.year for d in target.index[-365:]])
    enso_proxy = np.sin(2 * np.pi * years / 6.1)
    if mask.sum() > 30:
        corr_enso = np.abs(np.corrcoef(enso_proxy[mask], target_series[-365:][mask])[0, 1])
        importances["ENSO Signal"] = round(float(corr_enso), 3)

    # Normalize to sum to 1
    total = sum(importances.values()) or 1
    importances = {k: round(v / total, 3) for k, v in importances.items()}

    # Sort by importance
    importances = dict(sorted(importances.items(), key=lambda x: x[1], reverse=True))

    return importances


def classify_confidence(std_values: list, mean_values: list) -> dict:
    """Classify prediction confidence based on uncertainty spread."""
    avg_std = np.mean(std_values)
    avg_mean = np.mean(np.abs(mean_values)) + 1e-6
    ratio = avg_std / avg_mean

    if ratio < 0.15:
        return {"level": "High", "score": 92, "color": "#10b981"}
    elif ratio < 0.35:
        return {"level": "Medium", "score": 68, "color": "#f59e0b"}
    else:
        return {"level": "Low", "score": 40, "color": "#ef4444"}


# ─────────────────────────────────────────────────────────────
# Impact Models
# ─────────────────────────────────────────────────────────────

def compute_water_stress_index(rainfall_pct_change: float, temp_delta: float) -> float:
    """Simple proxy: Palmer-like Water Stress Index change."""
    # Higher temp → more evaporation → more stress
    # Lower rain → less recharge → more stress
    evap_factor = 1 + 0.06 * temp_delta
    supply_factor = 1 + rainfall_pct_change / 100
    wsi_change = (1 / supply_factor) * evap_factor - 1
    return round(float(wsi_change * 100), 1)


def compute_crop_yield_impact(
    rainfall_pct_change: float, temp_delta: float, crop: str = "rice"
) -> dict:
    """
    Simplified crop yield sensitivity model.
    Based on published sensitivity coefficients (ICAR estimates).
    """
    # Sensitivity: % yield change per % rainfall change, per °C
    sensitivity = {
        "rice":   {"rain": 0.45, "temp": -4.0},
        "wheat":  {"rain": 0.20, "temp": -6.0},
        "cotton": {"rain": 0.30, "temp": -2.5},
        "sugarcane": {"rain": 0.50, "temp": -3.0},
    }
    s = sensitivity.get(crop, sensitivity["rice"])
    yield_change = (s["rain"] * rainfall_pct_change / 100 * 100) + (s["temp"] * temp_delta)
    return {
        "crop": crop,
        "yield_change_pct": round(float(yield_change), 1),
        "outlook": "Positive" if yield_change > 0 else "Negative" if yield_change < -5 else "Neutral"
    }


def compute_river_discharge_change(
    rainfall_pct_change: float, temp_delta: float, river: str = "Godavari"
) -> dict:
    """Estimate river discharge change from rainfall and temperature perturbation."""
    from backend.preprocess import MAHARASHTRA_RIVERS
    river_data = MAHARASHTRA_RIVERS.get(river, {"avg_discharge_m3s": 1000, "basin_area_km2": 100000})
    base_discharge = river_data["avg_discharge_m3s"]

    # Discharge is roughly proportional to rainfall, reduced by evaporation
    rain_factor = 1 + rainfall_pct_change / 100
    evap_factor = 1 - 0.04 * temp_delta  # Higher temp → more evaporation
    new_discharge = base_discharge * rain_factor * evap_factor

    change_pct = ((new_discharge - base_discharge) / base_discharge) * 100

    # Flood risk from discharge
    if new_discharge > base_discharge * 2.0:
        flood_level = "Extreme"
    elif new_discharge > base_discharge * 1.5:
        flood_level = "High"
    elif new_discharge > base_discharge * 1.2:
        flood_level = "Moderate"
    else:
        flood_level = "Low"

    return {
        "river": river,
        "base_discharge_m3s": round(base_discharge, 0),
        "projected_discharge_m3s": round(new_discharge, 0),
        "change_pct": round(float(change_pct), 1),
        "flood_level": flood_level,
    }


def train_all_models(data: dict) -> list:
    """Train LSTM for rainfall + max_temp for each Maharashtra city."""
    results = []
    cities = list(data["rainfall"].columns)
    for city in cities:
        for var in ["rainfall", "max_temp"]:
            series = data[var][city].values
            print(f"  Training {var} model for {city}...")
            r = train_lstm(series, variable=var, city=city, epochs=40)
            results.append(r)
            print(f"    MAE={r['mae']}, RMSE={r['rmse']}, Skill={r['skill_score']}")
    return results
