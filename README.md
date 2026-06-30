# 🌏 ClimaTwin India - AI-Powered Digital Twin of India's Climate

> **ISRO Hack2Skill 2026 | Problem Statement 5**
> Pilot Region: Maharashtra, India

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Dataset](#2-dataset)
3. [Models](#3-models)
4. [System Architecture](#4-system-architecture)
5. [Features / Dashboard Walkthrough](#5-features--dashboard-walkthrough)
6. [How to Run It](#6-how-to-run-it)
7. [Deployment Plan - PoC to Production](#7-deployment-plan--poc-to-production)
8. [Innovation & Differentiation](#8-innovation--differentiation)
9. [Evaluation Criteria Mapping](#9-evaluation-criteria-mapping)
10. [Team / Credits / Acknowledgments](#10-team--credits--acknowledgments)
11. [Future Work](#11-future-work)

---

## 1. Project Overview

**Elevator Pitch:** ClimaTwin India is an interactive, AI-powered digital twin of India's climate system designed to bridge the gap between raw meteorological data and actionable decision-making. By leveraging deep learning and real-time data assimilation, it provides disaster management agencies, agricultural planners, policymakers, and water resource managers with high-resolution, short-term forecasts (with uncertainty bounds) and a powerful "What-If" scenario simulation engine to anticipate cascading climate impacts before they happen.

**ISRO Problem Statement Alignment:** This project directly addresses the ISRO Hack2Skill challenge to build an AI-driven Climate Digital Twin utilizing indigenous national datasets (IMD, INSAT/MOSDAC, and Bhuvan). It aligns strongly with the *Atmanirbhar Bharat* vision by demonstrating how 100% homegrown data ecosystems can power state-of-the-art climate intelligence and resilience planning.

**Scope Clarity:** Under the hackathon's time constraints, this PoC focuses specifically on **rainfall and maximum temperature forecasting** over a defined pilot region: **Maharashtra**. Limiting the domain to 7 major cities in Maharashtra allows us to deeply explore cascading impacts (like water stress, crop yields, and river discharge) and validate the digital twin architecture end-to-end without requiring massive supercomputing resources for a full Pan-India grid simulation. A production system would seamlessly scale this architecture nationally.

---

## 2. Dataset

### Datasets Integrated
The digital twin is designed to natively ingest the following national datasets:
* **Gridded Rainfall:** IMD Pune, 0.25° × 0.25° resolution, daily (1901–present).
* **Gridded Temperature (Max/Min):** IMD Pune, 1.0° × 1.0° resolution, daily (1951–present).
* **Satellite Observations:** INSAT-3R (via MOSDAC), ~4 km resolution for Land Surface Temperature (LST), Sea Surface Temperature (SST), and Rainfall (IMC).

### Handling of Hackathon Constraints (Synthetic Data)
Due to API access and data download time constraints during the hackathon window, **this PoC utilizes a statistically rigorous synthetic data generator** to emulate 35 years (1990–2024) of daily IMD-like observations. 
* **How it's generated:** We simulate 12,784 days of data using a Gamma distribution for precipitation, superimposed with sinusoidal seasonal patterns (Monsoon peaking around August), a 6-year ENSO proxy cycle, and an anthropogenic warming trend (+0.04°C/year). 
* **Real-world mimics:** It accurately mimics real-world spatial variations (e.g., coastal Mumbai being wetter and windier than inland Nagpur), seasonal temperature dips during the monsoon, and urban heat island effects. 
* **Transition Plan:** The backend includes a binary parser (`imd_bin_to_array` in `preprocess.py`) explicitly built to parse actual IMD `.GRD` / `.bin` files, ensuring a seamless swap to live data post-hackathon.

### Preprocessing & Feature Engineering
* **Missing Values:** Missing data points (-999.0) are gracefully handled and converted to NaN.
* **Feature Engineering:** We inject temporal context using day-of-year (DOY) encodings for seasonality and lag sequences (30-day lookback). We also enrich the state with correlated features like Humidity, Wind Speed, and Cloud Cover.
* **Train/Test Split:** Data is split **chronologically** (1990-2022 for training (85%), 2023-2024 for validation (15%)) rather than randomly. Chronological splitting is critical in time-series forecasting to prevent data leakage from the future into the past.

---

## 3. Models

### Algorithm Selection
For our primary forecasting engine, we chose a **Long Short-Term Memory (LSTM)** neural network (2 layers, 64 hidden units). 
* **Why LSTM?** Traditional Numerical Weather Prediction (NWP) models require massive compute and take hours to run. For a rapid-response PoC, LSTMs are exceptionally lightweight, capture non-linear temporal dynamics well, and can execute sub-second inferences on standard hardware.
* **Prediction Horizon:** 7-day short-term forecast.
* **Input Features:** 30-day sequence of normalized historical observations (Rainfall, Max Temp).

### Training Methodology & Hyperparameters
* **Hyperparameters:** Batch Size = 64, Learning Rate = 1e-3 (with Cosine Annealing scheduler), Epochs = 40.
* **Uncertainty Quantification:** We implement **Monte Carlo Dropout (MC Dropout)** with 50 forward passes during inference to generate a distribution of predictions. This allows us to provide **95% Confidence Intervals (CI)** and an explicit "Confidence Score," treating the neural network as a Bayesian estimator.
* **Overfitting Check:** Early stopping is employed by monitoring validation loss. We use `BatchNorm1d` and `Dropout (0.2)` regularization.

### Performance Metrics
Based on the validation set (2023-2024), the models achieve:
* **MAE (Mean Absolute Error):** Typically ~1.5 to 3.5 mm/day for rainfall (varies by city).
* **Skill Score:** We evaluate against a Naive Persistence Baseline. The model demonstrates a positive skill score, meaning it significantly outperforms simply guessing that "tomorrow's weather will be the same as today's." 
* *Practical Interpretation:* A low MAE means the model reliably captures the dry spells, while the MC Dropout bands accurately widen during volatile monsoon downpours, giving decision-makers an honest assessment of uncertainty.

### Honest Limitations
* **Limitation:** The current LSTM is univariate per city and lacks spatial awareness (it doesn't know that a storm in Pune might move to Solapur). 
* **Solution:** We have stubbed a `ConvLSTM` architecture in `model.py` which, given more compute and time, would replace the standard LSTM to capture spatial-temporal dynamics across the entire geographic grid simultaneously.

---

## 4. System Architecture

### Pipeline Flow
`Data Ingestion (IMD/INSAT)` → `Preprocessing (QC, Regrid, Norm)` → `AI Engine (LSTM, MC Dropout)` → `Digital Twin Core (State Manager, Scenario Engine)` → `Dashboard (React/Leaflet)`

### The "Digital Twin" Concept
In this PoC, the digital twin is implemented as a **continuously-updatable state representation**. It is not a complete physics-based emulation of the atmosphere. Instead, it maintains a live "digital state" of the pilot region, updates it with recent observations (simulating real-time data assimilation), overlays AI-driven forecasts, and runs cascading impact rules. A production version would expand this to include 6-hourly automated data assimilation from MOSDAC APIs and multi-model ensembling.

### Tech Stack
* **Backend:** Python, FastAPI (REST API, fast async execution).
* **Data & AI:** Pandas, NumPy, PyTorch (LSTM training and inference).
* **Frontend:** HTML, Vanilla JavaScript, CSS (Dark glassmorphism theme).
* **Visualizations:** Leaflet.js (Geospatial mapping), Chart.js (Time-series and prediction charts).

---

## 5. Features / Dashboard Walkthrough

### 1. 🗺️ Climate State Tab (Overview)
* **What it shows:** An interactive map of India with real-time geospatial choropleth overlays (Rainfall, Max/Min Temp, Humidity).
* **Interaction:** Users can click variables to change the map layer, use a 30-day time scrubber animation to see weather systems move, or click city markers for a deep-dive modal profile.
* **Insight:** Provides an immediate, visceral understanding of current spatial climate patterns. A live Digital Twin panel lists the assimilated state of monitored cities alongside an active anomaly alert feed.

### 2. 📈 AI Forecast Tab
* **What it shows:** Historical climate trends alongside a 7-day AI prediction.
* **Interaction:** Select City, Variable, and Time Resolution (Monthly, Weekly, Yearly).
* **Insight:** Visualizes long-term trends alongside immediate futures. Crucially, the forecast chart plots the **MC Dropout 95% Confidence Intervals**, visually communicating uncertainty to planners. 

### 3. 🔬 What-If Scenarios Tab
* **What it shows:** A simulation engine to test climate perturbations. 
* **Interaction:** Users can select 8 presets (e.g., El Niño, Heat Wave, RCP 8.5) or use custom sliders for Temperature Delta (−3°C to +6°C) and Rainfall Change (−80% to +100%).
* **Insight:** Computes and maps cascading impacts using proxy models. Outputs changes to Water Stress Index, Agricultural GDP, Crop Yields (rice, wheat, cotton), River Discharge, and Reservoir Storage. It automatically generates decision-support recommendations based on the simulated severity.

### 4. 📊 Model Performance Tab
* **What it shows:** The architecture of the AI pipeline and validation metrics.
* **Insight:** Fosters trust in the system by transparently showing MAE, RMSE, Skill Scores, and a direct visual comparison of the model's accuracy against a naive baseline.

### 5. ℹ️ Architecture Tab
* **What it shows:** Data pipeline flowcharts, dataset acknowledgments, and a scalability roadmap.

---

## 6. How to Run It

### Setup Instructions (Local)
1. **Prerequisites:** Python 3.10+ installed.
2. **Clone the repository.**
3. **Run the startup script:**
   * **Windows:** Double-click `run.bat` or execute `.\run.bat` in Command Prompt.
   * **Mac / Linux:** Run `chmod +x run.sh && ./run.sh`
4. **Manual Setup:**
   ```bash
   pip install -r requirements.txt
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
   ```
5. **Access Dashboard:** Open your browser to `http://127.0.0.1:8000`

### Project Structure
* `backend/` - FastAPI server (`main.py`), ML logic (`model.py`), Scenario engine (`simulator.py`), Data prep (`preprocess.py`).
* `frontend/` - SPA UI (`index.html`, `app.js`, `style.css`).
* `models/` - Saved PyTorch `.pt` model weights.

---

## 7. Deployment Plan - PoC to Production

* **Current PoC:** Runs seamlessly as a standalone local application or on a single cloud VM (e.g., AWS EC2, Heroku) using Uvicorn/FastAPI.
* **Scaling to Operational National System:**
  * **Ingestion:** Establish direct, secure automated API pipelines to MOSDAC and IMD FTP servers for 6-hourly live assimilation.
  * **Expansion:** Scale the domain from the Maharashtra bounding box to the full 0.25° India grid, expanding variables to include Soil Moisture and Vegetation Indices from Bhuvan.
  * **Compute:** Containerize via Docker and orchestrate with Kubernetes on NIC (National Informatics Centre) or ISRO cloud infrastructure to handle the massive array operations required for national ConvLSTM inferences.
* **Phased Roadmap:**
  * **Phase 1 (Now):** PoC validation in Maharashtra.
  * **Phase 2 (Months 1-3):** Swap synthetic pipelines for live IMD/INSAT data ingestion and validate historical accuracy.
  * **Phase 3 (Months 4-6):** Transition from univariate LSTMs to spatial ConvLSTM networks.
  * **Phase 4 (Months 7-12):** National rollout, providing API access for state disaster management authorities.

---

## 8. Innovation & Differentiation

* **AI-Driven Agility:** Unlike traditional numerical models that take hours on supercomputers, our deep learning approach enables near-instantaneous inference and scenario testing.
* **Cascading Impacts:** The Digital Twin doesn't just predict "35°C." It translates that into actionable insights: "35°C means a 5% drop in wheat yield and Moderate heat stress for 12M people."
* **Uncertainty as a Feature:** By utilizing Monte Carlo Dropout, we treat uncertainty as a first-class metric, producing confidence bands that are essential for risk-averse government planning.
* **Interactive What-If Engine:** Empowers policymakers to simulate climate futures intuitively via a UI, rather than writing code.

---

## 9. Evaluation Criteria Mapping

| Hackathon Parameter | Where it is Addressed in Project / README |
| :--- | :--- |
| **Problem Understanding** | Section 1 (Overview) & Section 4 (Architecture) - Clear alignment with ISRO constraints. |
| **Data Usage** | Section 2 (Dataset) - Detailed plan for IMD/INSAT, rigorous handling of synthetic data. |
| **Model Development** | Section 3 (Models) - LSTM, MC Dropout, Hyperparameters. |
| **Prediction Performance**| Section 3 (Models) & Dashboard "Metrics" Tab - MAE, RMSE, Skill Scores. |
| **Digital Twin Impl.** | Section 4 (Architecture) & Dashboard "Climate State" Tab. |
| **Visualization** | Section 5 (Dashboard Walkthrough) - Leaflet maps, time scrubbers, choropleths. |
| **Innovation** | Section 8 (Innovation) - MC Dropout bands, Cascading Impact Simulator. |
| **Presentation** | Clean UI, comprehensive README, AI-generated narratives for clarity. |

---

## 10. Team / Credits / Acknowledgments

Built by **[Your Name/Team]**, FRK Productions / Symbiosis Institute of Computer Studies and Research, for **ISRO Hack2Skill 2026**.

**Acknowledgments:** 
We acknowledge the vital data ecosystem provided by **IMD (India Meteorological Department)**, **ISRO / MOSDAC**, and **Bhuvan**, whose continuous monitoring of the Indian subcontinent makes concepts like a National Climate Digital Twin possible.

---

## 11. Future Work

With additional time and resources, the immediate next steps involve:
1. **Spatial Deep Learning:** Implementing the `ConvLSTM` architecture to forecast the entire geographic grid simultaneously, capturing storm movement and spatial dependencies.
2. **Extended Horizons:** Training seq2seq transformers for 30-day and 90-day seasonal outlooks.
3. **Advanced Impact Models:** Replacing proxy rule-based impact equations with dedicated machine learning models trained on historical agricultural output and river gauge data.
4. **Bhuvan Integration:** Adding dynamic map layers directly from Bhuvan APIs (e.g., live vegetation stress indices).
