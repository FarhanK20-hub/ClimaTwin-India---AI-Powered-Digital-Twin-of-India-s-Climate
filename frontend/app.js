/* ════════════════════════════════════════════════════════════
   ClimaTwin India v2.0 — Digital Twin Dashboard Logic
   AI-Powered Digital Twin of India's Climate
   ════════════════════════════════════════════════════════════ */

const API = '';  // Empty = same origin (FastAPI serves frontend)
const CITIES = ['Mumbai','Pune','Nagpur','Nashik','Aurangabad','Solapur','Kolhapur'];

const CITY_ICONS = {
  Mumbai: '🌊', Pune: '⛰️', Nagpur: '🌳',
  Nashik: '🍇', Aurangabad: '🏛️', Solapur: '☀️', Kolhapur: '👑'
};

// Chart instances
let historicalChart = null;
let forecastChart = null;
let quickForecastChart = null;
let metricsCompareChart = null;
let modalRainSparkChart = null;
let modalTempSparkChart = null;

// Map instances
let climateMap = null;
let scenarioMap = null;
let mapLayer = null;
let scenarioLayer = null;
let cityMarkers = {};

// State
let currentMapVar = 'rainfall';
window.stateMask = null;

// Load GeoJSON boundary for clipping
fetch('/static/maharashtra.geojson')
  .then(r => r.json())
  .then(data => { window.stateMask = data; })
  .catch(err => console.warn('Could not load state boundary mask', err));
let currentScenarioPreset = 'normal';
let selectedCity = 'Mumbai';
let timelineData = null;
let timelineInterval = null;
let isTimelinePlaying = false;
let currentTimelineIndex = 0;
let lastTwinData = null;

/* ────────────────────────────────────────
   INIT
   ──────────────────────────────────────── */
window.addEventListener('DOMContentLoaded', async () => {
  initMaps();

  await Promise.all([
    loadTwinClock(),
    loadAnomalyAlerts(),
    loadQuickForecast(),
    refreshMap(),
    loadScenarioPresets(),
    loadNarrative('Mumbai'),
  ]);

  // Fetch timeline in background
  loadTimeline();

  // Hide loading screen
  setTimeout(() => {
    const overlay = document.getElementById('loadingScreen');
    if (overlay) {
      overlay.style.opacity = '0';
      setTimeout(() => overlay.remove(), 800);
    }
    document.getElementById('mapClickHint').style.display = 'block';
  }, 3800);

  // Live clock
  setInterval(updateClock, 1000);
  // Refresh twin state every 30s
  setInterval(loadTwinClock, 30000);
  // Assimilation timer update
  setInterval(updateAssimTime, 60000);
});

/* ────────────────────────────────────────
   CLOCK
   ──────────────────────────────────────── */
function updateClock() {
  const el = document.getElementById('clockTime');
  if (el) el.textContent = new Date().toUTCString().slice(5, 25) + ' UTC';
}

function updateAssimTime() {
  const el = document.getElementById('assimTime');
  if (!el) return;
  const mins = Math.floor(Math.random() * 360); // Demo
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  el.textContent = h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/* ────────────────────────────────────────
   MAP INIT
   ──────────────────────────────────────── */
function initMaps() {
  const darkTile = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';

  climateMap = L.map('climate-map', {
    center: [19.5, 76.5], zoom: 6,
    zoomControl: true, attributionControl: false,
  });
  L.tileLayer(darkTile, { subdomains: 'abcd', maxZoom: 19 }).addTo(climateMap);

  scenarioMap = L.map('scenario-map', {
    center: [19.5, 76.5], zoom: 6,
    zoomControl: false, attributionControl: false,
  });
  L.tileLayer(darkTile, { subdomains: 'abcd', maxZoom: 19 }).addTo(scenarioMap);

  addCityMarkers(climateMap);
  addCityMarkers(scenarioMap, true);
}

function addMaharashtraBoundingBox(map) {
  L.rectangle([[15.6, 72.6],[22.1, 80.9]], {
    color: 'rgba(56,189,248,0.7)', weight: 2,
    fill: false, dashArray: '6,4'
  }).addTo(map).bindPopup('<b style="font-family:sans-serif">🛰️ Pilot Region: Maharashtra</b><br/><small>Digital Twin Active Zone · 7 cities monitored</small>');
}

function addCityMarkers(map, small = false) {
  const cities = {
    Mumbai:    [19.07, 72.87], Pune:       [18.52, 73.86],
    Nagpur:    [21.15, 79.09], Nashik:     [20.00, 73.79],
    Aurangabad:[19.88, 75.34], Solapur:    [17.68, 75.90],
    Kolhapur:  [16.70, 74.23],
  };
  Object.entries(cities).forEach(([name, [lat, lon]]) => {
    const marker = L.circleMarker([lat, lon], {
      radius: small ? 6 : 9,
      color: '#38bdf8', weight: 2.5,
      fillColor: 'rgba(56,189,248,0.35)', fillOpacity: 0.9
    }).addTo(map);

    marker.bindTooltip(
      `<b>${CITY_ICONS[name] || '📍'} ${name}</b>`,
      { permanent: !small, direction: 'top', className: 'map-tooltip' }
    );

    if (!small) {
      marker.on('click', () => openCityModal(name));
      marker.on('mouseover', function() {
        this.setStyle({ radius: 12, color: '#fff', fillColor: 'rgba(56,189,248,0.6)' });
      });
      marker.on('mouseout', function() {
        this.setStyle({ radius: 9, color: '#38bdf8', fillColor: 'rgba(56,189,248,0.35)' });
      });
      cityMarkers[name] = marker;
    }
  });
}

/* ────────────────────────────────────────
   MAP DATA LAYER
   ──────────────────────────────────────── */
async function refreshMap(scenarioDelta = {}) {
  const date = document.getElementById('mapDateInput')?.value || '2024-07-15';
  const url = new URL(`${location.origin}/api/spatial-grid`);
  url.searchParams.set('variable', currentMapVar);
  url.searchParams.set('date', date);
  if (scenarioDelta.temp_delta) url.searchParams.set('temp_delta', scenarioDelta.temp_delta);
  if (scenarioDelta.rainfall_pct) url.searchParams.set('rainfall_pct', scenarioDelta.rainfall_pct);

  try {
    const resp = await fetch(url);
    const data = await resp.json();
    renderHeatmapLayer(data, climateMap, 'mapLayer');
    updateLegend(data);
  } catch (e) {
    console.warn('Map refresh failed');
  }
}

async function refreshScenarioMap(tempDelta, rainPct) {
  const url = new URL(`${location.origin}/api/spatial-grid`);
  url.searchParams.set('variable', currentMapVar === 'min_temp' ? 'max_temp' : currentMapVar);
  url.searchParams.set('date', '2024-07-15');
  url.searchParams.set('temp_delta', tempDelta);
  url.searchParams.set('rainfall_pct', rainPct);

  try {
    const resp = await fetch(url);
    const data = await resp.json();
    renderHeatmapLayer(data, scenarioMap, 'scenarioLayer');
  } catch (e) { console.warn('Scenario map error'); }
}

function renderHeatmapLayer(data, map, layerRef) {
  if (window[layerRef]) { map.removeLayer(window[layerRef]); }

  const { points, stats } = data;
  const minV = stats.min, maxV = stats.max;
  const range = maxV - minV || 1;

  // Filter points using Turf.js if mask is available
  let filteredPoints = points;
  if (window.stateMask && typeof turf !== 'undefined') {
    filteredPoints = points.filter(pt => {
      // Create a turf point [lon, lat] - GeoJSON format
      return turf.booleanPointInPolygon(turf.point([pt.lon, pt.lat]), window.stateMask);
    });
  }

  // Use grid_step from API (backend generates at 0.5°), fallback to 0.5
  const halfStep = (data.grid_step || 0.5) / 2;

  const cells = filteredPoints.map(pt => {
    const t = (pt.value - minV) / range;
    const color = getColorForVar(currentMapVar, t, pt.value);
    
    const bounds = [
      [pt.lat - halfStep, pt.lon - halfStep],
      [pt.lat + halfStep, pt.lon + halfStep]
    ];
    
    return L.rectangle(bounds, {
      color: 'transparent',
      fillColor: color,
      fillOpacity: 0.85,
      weight: 0,
      stroke: false // ensure no gaps from stroke
    }).bindPopup(`
      <div style="font-family:monospace;font-size:12px;line-height:1.6;">
        <b>${getVarIcon(data.variable)} ${pt.value} ${data.unit}</b><br/>
        ${pt.lat.toFixed(2)}°N, ${pt.lon.toFixed(2)}°E
      </div>
    `);
  });

  // Bounding box for the region
  if (window.stateMask) {
    cells.push(L.geoJSON(window.stateMask, {
      color: '#38bdf8', // accent-cyan
      weight: 3,
      fill: false,
      interactive: false
    }));
  } else if (filteredPoints.length > 0) {
    let minLat = 90, maxLat = -90, minLon = 180, maxLon = -180;
    filteredPoints.forEach(pt => {
      if (pt.lat < minLat) minLat = pt.lat;
      if (pt.lat > maxLat) maxLat = pt.lat;
      if (pt.lon < minLon) minLon = pt.lon;
      if (pt.lon > maxLon) maxLon = pt.lon;
    });

    const regionBounds = [
      [minLat - 0.125, minLon - 0.125],
      [maxLat + 0.125, maxLon + 0.125]
    ];
    const boundingBox = L.rectangle(regionBounds, {
      color: '#38bdf8', // accent-cyan
      weight: 2,
      fill: false,
      dashArray: '5, 5',
      interactive: false
    });
    cells.push(boundingBox);
  }

  window[layerRef] = L.layerGroup(cells).addTo(map);
}

function getVarIcon(variable) {
  return { rainfall: '🌧️', max_temp: '🌡️', min_temp: '❄️', humidity: '💧', cloud_cover: '☁️' }[variable] || '📊';
}

function getColorForVar(variable, t, value) {
  if (variable === 'rainfall') {
    // Vivid blue gradient: White/Light Blue -> Cyan -> Deep Blue
    const stops = [
      [0.0, [240, 249, 255]], // Very light blue
      [0.2, [186, 230, 253]], // Light sky blue
      [0.5, [14, 165, 233]],  // Vivid Cyan/Blue
      [0.8, [3, 105, 161]],   // Deep Blue
      [1.0, [8, 47, 73]],     // Very Dark Blue
    ];
    return interpolateColorStops(stops, t);
  } else if (variable === 'humidity') {
    // White → teal
    const stops = [
      [0.0, [255, 255, 255]],
      [0.5, [45, 212, 191]],
      [1.0, [17, 94, 89]],
    ];
    return interpolateColorStops(stops, t);
  } else {
    // Temperature 'Inferno' Palette: Dark Purple -> Red -> Orange -> Yellow
    const stops = [
      [0.0, [49, 5, 151]],   // Deep purple
      [0.3, [162, 17, 124]], // Magenta-red
      [0.6, [230, 81, 36]],  // Orange-red
      [0.8, [249, 162, 36]], // Bright Orange
      [1.0, [252, 255, 164]],// Light Yellow
    ];
    return interpolateColorStops(stops, t);
  }
}

function interpolateColorStops(stops, t) {
  for (let i = 0; i < stops.length - 1; i++) {
    const [t0, c0] = stops[i];
    const [t1, c1] = stops[i + 1];
    if (t >= t0 && t <= t1) {
      const f = (t - t0) / (t1 - t0);
      const r = Math.round(c0[0] + f * (c1[0] - c0[0]));
      const g = Math.round(c0[1] + f * (c1[1] - c0[1]));
      const b = Math.round(c0[2] + f * (c1[2] - c0[2]));
      return `rgb(${r},${g},${b})`;
    }
  }
  return '#888';
}

function updateLegend(data) {
  const { stats, variable, unit } = data;
  const labels = {
    rainfall:   'Rainfall (mm/day)',
    max_temp:   'Max Temperature (°C)',
    min_temp:   'Min Temperature (°C)',
    humidity:   'Humidity (%)',
    cloud_cover:'Cloud Cover (okta)',
  };
  document.getElementById('legendTitle').textContent = labels[variable] || variable;
  document.getElementById('legendMin').textContent = stats.min.toFixed(1);
  document.getElementById('legendMid').textContent = ((stats.min + stats.max) / 2).toFixed(1);
  document.getElementById('legendMax').textContent = stats.max.toFixed(1);

  const bar = document.getElementById('legendBar');
  if (variable === 'rainfall') {
    bar.style.background = 'linear-gradient(to right, #dbeafe, #1d4ed8, #0f172a)';
  } else if (variable === 'humidity') {
    bar.style.background = 'linear-gradient(to right, #cffafe, #0891b2, #164e63)';
  } else {
    bar.style.background = 'linear-gradient(to right, #1e40af, #10b981, #fbbf24, #ef4444)';
  }
}

function switchMapVar(variable) {
  currentMapVar = variable;
  document.querySelectorAll('.map-var-btn').forEach(b => b.classList.remove('active'));
  const btn = document.getElementById(`mapBtn-${variable}`);
  if (btn) btn.classList.add('active');
  refreshMap();
}

/* ────────────────────────────────────────
   TIME SCRUBBER
   ──────────────────────────────────────── */
async function loadTimeline() {
  try {
    const resp = await fetch(`/api/timeline?variable=${currentMapVar}&days=30`);
    timelineData = await resp.json();
  } catch (e) { console.warn('Timeline load failed'); }
}

function toggleTimeScrubber() {
  if (isTimelinePlaying) {
    stopTimeline();
  } else {
    startTimeline();
  }
}

function startTimeline() {
  if (!timelineData?.snapshots) { loadTimeline(); return; }
  isTimelinePlaying = true;
  const btn = document.getElementById('scrubberPlayBtn');
  btn.textContent = '⏸';
  btn.classList.add('playing');

  timelineInterval = setInterval(() => {
    currentTimelineIndex = (currentTimelineIndex + 1) % 30;
    document.getElementById('timeSlider').value = currentTimelineIndex;
    onTimeSliderChange(currentTimelineIndex, true);
  }, 500);
}

function stopTimeline() {
  isTimelinePlaying = false;
  clearInterval(timelineInterval);
  const btn = document.getElementById('scrubberPlayBtn');
  btn.textContent = '▶';
  btn.classList.remove('playing');
}

function onTimeSliderChange(idx, fromInterval = false) {
  if (!fromInterval) stopTimeline();
  currentTimelineIndex = parseInt(idx);

  if (timelineData?.snapshots?.[currentTimelineIndex]) {
    const snap = timelineData.snapshots[currentTimelineIndex];
    document.getElementById('scrubberCurrentDate').textContent =
      snap.date ? snap.date.slice(5) : `Day ${currentTimelineIndex + 1}`;

    // Render the snapshot on the map
    renderSnapshotLayer(snap);
  }
}

function renderSnapshotLayer(snap) {
  if (window.mapLayer) { climateMap.removeLayer(window.mapLayer); }
  const { points } = snap;
  if (!points || !points.length) return;

  const vals = points.map(p => p.value);
  const minV = Math.min(...vals);
  const maxV = Math.max(...vals);
  const range = maxV - minV || 1;

  const circles = points.map(pt => {
    const t = (pt.value - minV) / range;
    const color = getColorForVar(currentMapVar, t, pt.value);
    return L.circle([pt.lat, pt.lon], {
      radius: 30000, color: 'transparent',
      fillColor: color, fillOpacity: 0.65, weight: 0
    });
  });

  window.mapLayer = L.layerGroup(circles).addTo(climateMap);
}

/* ────────────────────────────────────────
   DIGITAL TWIN CLOCK
   ──────────────────────────────────────── */
async function loadTwinClock() {
  try {
    const resp = await fetch('/api/twin-clock');
    const data = await resp.json();
    lastTwinData = data;
    renderTwinState(data);
    const d = new Date(data.twin_timestamp);
    const el = document.getElementById('twinUpdateTime');
    if (el) el.textContent = `Updated: ${d.toUTCString().slice(5,22)} UTC`;
  } catch (e) { renderTwinStateFallback(); }
}

function renderTwinState(data) {
  const list = document.getElementById('cityStateList');
  if (!list || !data.city_states) return;

  list.innerHTML = Object.entries(data.city_states).map(([city, s]) => `
    <div class="city-state-item ${selectedCity === city ? 'selected' : ''}"
         onclick="openCityModal('${city}')" id="city-state-${city}">
      <div class="city-state-name">
        <span>${CITY_ICONS[city] || '📍'} ${city}</span>
        <span class="city-status-badge status-${statusClass(s.status)}">${s.status}</span>
      </div>
      <div class="city-metrics">
        <div class="city-metric">
          <span class="city-metric-label">🌧️</span>
          <span class="city-metric-value">${s.rainfall_7day_mm} mm</span>
        </div>
        <div class="city-metric">
          <span class="city-metric-label">🌡️</span>
          <span class="city-metric-value">${s.max_temp_c}°C</span>
        </div>
        <div class="city-metric">
          <span class="city-metric-label">💧</span>
          <span class="city-metric-value">${s.humidity_pct ?? '—'}%</span>
        </div>
        <div class="city-metric">
          <span class="city-metric-label">💨</span>
          <span class="city-metric-value">${s.wind_speed_kmh ?? '—'} km/h</span>
        </div>
      </div>
    </div>
  `).join('');
}

function renderTwinStateFallback() {
  const list = document.getElementById('cityStateList');
  if (!list) return;
  list.innerHTML = CITIES.map(city => `
    <div class="city-state-item" onclick="openCityModal('${city}')">
      <div class="city-state-name">
        <span>${CITY_ICONS[city] || '📍'} ${city}</span>
        <span class="city-status-badge status-normal">Normal</span>
      </div>
      <div class="city-metrics">
        <div class="city-metric"><span class="city-metric-label">🌧️</span>
          <span class="city-metric-value">${(Math.random()*15+2).toFixed(1)} mm</span></div>
        <div class="city-metric"><span class="city-metric-label">🌡️</span>
          <span class="city-metric-value">${(Math.random()*8+28).toFixed(1)}°C</span></div>
      </div>
    </div>
  `).join('');
}

function statusClass(status) {
  const map = {
    'Active Monsoon': 'monsoon', 'Wet': 'wet',
    'Heat Stress': 'heat', 'Drought Watch': 'drought', 'Normal': 'normal'
  };
  return map[status] || 'normal';
}

/* ────────────────────────────────────────
   CITY PROFILE MODAL
   ──────────────────────────────────────── */
async function openCityModal(city) {
  selectedCity = city;
  const modal = document.getElementById('cityModal');
  modal.classList.add('open');
  document.body.style.overflow = 'hidden';

  // Header
  document.getElementById('modalCityName').textContent = `${CITY_ICONS[city] || '📍'} ${city}`;
  document.getElementById('modalCitySub').textContent = 'Maharashtra · Digital Twin Profile';
  document.getElementById('modalCityIcon').textContent = CITY_ICONS[city] || '🏙️';
  document.getElementById('modalStatusBadge').textContent = 'Loading...';
  document.getElementById('modalStatusBadge').className = 'modal-status-badge';

  // Reset sections with spinners
  document.getElementById('modalConditions').innerHTML = '<div class="spinner" style="grid-column:1/-1;justify-self:center;margin:1rem;"></div>';
  document.getElementById('modalRiskGauges').innerHTML = '<div class="spinner" style="grid-column:1/-1;justify-self:center;margin:1rem;"></div>';
  document.getElementById('modalForecastContent').innerHTML = '<div class="spinner"></div>';
  document.getElementById('modalFeatureImportance').innerHTML = '<div class="spinner"></div>';
  document.getElementById('modalNarrative').textContent = 'Generating AI narrative...';

  try {
    const resp = await fetch(`/api/city-profile/${city}`);
    const data = await resp.json();
    renderCityModal(city, data);
  } catch (e) {
    renderCityModalFallback(city);
  }
}

function renderCityModal(city, data) {
  // Status badge
  const statusEl = document.getElementById('modalStatusBadge');
  statusEl.textContent = data.status || 'Normal';
  const statusColors = {
    'Active Monsoon': 'rgba(6,182,212,0.2)',
    'Wet': 'rgba(59,130,246,0.2)',
    'Heat Stress': 'rgba(239,68,68,0.2)',
    'Drought Watch': 'rgba(245,158,11,0.2)',
    'Normal': 'rgba(16,185,129,0.2)',
  };
  statusEl.style.background = statusColors[data.status] || statusColors['Normal'];
  statusEl.style.color = '#e2e8f0';
  statusEl.style.border = '1px solid rgba(255,255,255,0.1)';
  statusEl.style.borderRadius = '50px';
  statusEl.style.padding = '0.3rem 0.8rem';
  statusEl.style.fontSize = '0.75rem';
  statusEl.style.fontWeight = '600';

  // Sub info
  document.getElementById('modalCitySub').textContent =
    `${data.info?.district || ''} · Pop: ${data.info?.population_m ?? '—'}M · River: ${data.info?.river || '—'} · Elev: ${data.info?.elevation_m ?? '—'}m`;

  // Current conditions
  const c = data.current || {};
  document.getElementById('modalConditions').innerHTML = `
    <div class="modal-condition">
      <div class="modal-condition-icon">🌧️</div>
      <div class="modal-condition-value">${c.rainfall_mm ?? '—'}<small> mm</small></div>
      <div class="modal-condition-label">Today Rainfall</div>
    </div>
    <div class="modal-condition">
      <div class="modal-condition-icon">📊</div>
      <div class="modal-condition-value">${c.rainfall_7d_avg ?? '—'}<small> mm</small></div>
      <div class="modal-condition-label">7-Day Avg</div>
    </div>
    <div class="modal-condition">
      <div class="modal-condition-icon">🌡️</div>
      <div class="modal-condition-value">${c.max_temp_c ?? '—'}<small>°C</small></div>
      <div class="modal-condition-label">Max Temp</div>
    </div>
    <div class="modal-condition">
      <div class="modal-condition-icon">❄️</div>
      <div class="modal-condition-value">${c.min_temp_c ?? '—'}<small>°C</small></div>
      <div class="modal-condition-label">Min Temp</div>
    </div>
    <div class="modal-condition">
      <div class="modal-condition-icon">💧</div>
      <div class="modal-condition-value">${c.humidity_pct ?? '—'}<small>%</small></div>
      <div class="modal-condition-label">Humidity</div>
    </div>
    <div class="modal-condition">
      <div class="modal-condition-icon">💨</div>
      <div class="modal-condition-value">${c.wind_speed_kmh ?? '—'}<small>km/h</small></div>
      <div class="modal-condition-label">Wind Speed</div>
    </div>
  `;

  // Risk gauges
  const risks = data.risks || {};
  document.getElementById('modalRiskGauges').innerHTML = `
    ${renderRiskGauge('Flood Risk', risks.flood?.score ?? 0, risks.flood?.level, '#38bdf8')}
    ${renderRiskGauge('Drought Risk', risks.drought?.score ?? 0, risks.drought?.level, '#f59e0b')}
    ${renderRiskGauge('Heat Stress', risks.heat?.score ?? 0, risks.heat?.level, '#ef4444')}
  `;

  // Sparklines
  if (data.sparkline) {
    renderSparkline('modalRainfallSparkline', data.sparkline.rainfall, '#38bdf8', 'bar');
    renderSparkline('modalTempSparkline', data.sparkline.temperature, '#f59e0b', 'line');
  }

  // 7-day forecast
  if (data.prediction) {
    const fc = data.prediction;
    document.getElementById('modalForecastContent').innerHTML = `
      <div style="margin-bottom:0.5rem; font-size:0.72rem; color:var(--text-muted);">
        Model: LSTM + MC Dropout · Confidence: 
        <span style="color:${fc.confidence === 'High' ? 'var(--accent-green)' : fc.confidence === 'Medium' ? 'var(--accent-orange)' : 'var(--accent-red)'}; font-weight:600;">
          ${fc.confidence} (${fc.confidence_score}%)
        </span>
        · MAE: ${fc.metrics?.mae ?? '—'} mm
      </div>
      <div class="modal-forecast-grid">
        ${fc.dates.map((d, i) => {
          const val = fc.mean[i];
          const lo = fc.low_95?.[i] ?? val;
          const hi = fc.high_95?.[i] ?? val;
          const icon = val > 20 ? '🌧️' : val > 8 ? '🌦️' : val > 2 ? '⛅' : '☀️';
          return `
            <div class="modal-forecast-day">
              <div class="mfd-date">${d.slice(5)}</div>
              <div class="mfd-icon">${icon}</div>
              <div class="mfd-value">${val}</div>
              <div class="mfd-range">${lo}–${hi}</div>
            </div>
          `;
        }).join('')}
      </div>
    `;
  } else {
    document.getElementById('modalForecastContent').innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;">Model training in progress. Showing persistence forecast.</div>';
  }

  // Feature importance
  if (data.feature_importance && Object.keys(data.feature_importance).length > 0) {
    const fi = data.feature_importance;
    document.getElementById('modalFeatureImportance').innerHTML =
      Object.entries(fi).map(([feat, score]) => `
        <div class="feature-bar">
          <div class="feature-label">${feat}</div>
          <div class="feature-track">
            <div class="feature-fill" style="width:${score * 100}%"></div>
          </div>
          <div class="feature-pct">${(score * 100).toFixed(1)}%</div>
        </div>
      `).join('');
  } else {
    document.getElementById('modalFeatureImportance').innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;">Feature importance data unavailable.</div>';
  }

  // Narrative
  document.getElementById('modalNarrative').textContent = data.narrative || 'No narrative available.';
}

function renderRiskGauge(label, score, level, color) {
  const r = 36;
  const cx = 44, cy = 44;
  const circumference = 2 * Math.PI * r;
  const dashOffset = circumference * (1 - score / 100);
  const levelColors = { 'High': '#ef4444', 'Extreme': '#ff3366', 'Moderate': '#f59e0b', 'Low': '#10b981' };
  const gaugeColor = levelColors[level] || color;

  return `
    <div class="risk-gauge">
      <div class="gauge-svg" style="position:relative;width:88px;height:88px;">
        <svg width="88" height="88" viewBox="0 0 88 88" style="transform:rotate(-90deg)">
          <circle class="gauge-bg" cx="${cx}" cy="${cy}" r="${r}"
                  stroke-dasharray="${circumference}" stroke-dashoffset="0"/>
          <circle class="gauge-fill" cx="${cx}" cy="${cy}" r="${r}"
                  stroke="${gaugeColor}"
                  stroke-dasharray="${circumference}"
                  stroke-dashoffset="${dashOffset}"
                  style="transition:stroke-dashoffset 1s ease;"/>
        </svg>
        <div class="gauge-text" style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);text-align:center;">
          <div class="gauge-value" style="color:${gaugeColor};font-family:'Space Grotesk',sans-serif;font-size:1rem;font-weight:700;">${score}</div>
          <div style="font-size:0.55rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;">${level || '—'}</div>
        </div>
      </div>
      <div class="gauge-name">${label}</div>
    </div>
  `;
}

function renderSparkline(canvasId, seriesData, color, type = 'line') {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;

  // Destroy existing
  if (canvasId === 'modalRainfallSparkline' && modalRainSparkChart) {
    modalRainSparkChart.destroy(); modalRainSparkChart = null;
  }
  if (canvasId === 'modalTempSparkline' && modalTempSparkChart) {
    modalTempSparkChart.destroy(); modalTempSparkChart = null;
  }

  const chart = new Chart(ctx, {
    type,
    data: {
      labels: seriesData.dates.map(d => d.slice(5)),
      datasets: [{
        data: seriesData.values,
        borderColor: color,
        backgroundColor: `${color}25`,
        borderWidth: 1.5,
        pointRadius: 0,
        tension: 0.4,
        fill: type === 'bar' ? false : true,
        borderRadius: type === 'bar' ? 2 : 0,
        backgroundColor: type === 'bar' ? `${color}55` : `${color}20`,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: {
        x: { display: false },
        y: { display: false }
      },
      animation: { duration: 600 }
    }
  });

  if (canvasId === 'modalRainfallSparkline') modalRainSparkChart = chart;
  if (canvasId === 'modalTempSparkline') modalTempSparkChart = chart;
}

function renderCityModalFallback(city) {
  document.getElementById('modalStatusBadge').textContent = 'Normal';
  document.getElementById('modalConditions').innerHTML = `
    <div class="modal-condition"><div class="modal-condition-icon">🌧️</div>
      <div class="modal-condition-value">${(Math.random()*20+5).toFixed(1)}</div>
      <div class="modal-condition-label">Rainfall mm</div></div>
    <div class="modal-condition"><div class="modal-condition-icon">🌡️</div>
      <div class="modal-condition-value">${(Math.random()*8+28).toFixed(1)}°C</div>
      <div class="modal-condition-label">Max Temp</div></div>
    <div class="modal-condition"><div class="modal-condition-icon">💧</div>
      <div class="modal-condition-value">${(Math.random()*20+65).toFixed(0)}%</div>
      <div class="modal-condition-label">Humidity</div></div>
  `;
  document.getElementById('modalRiskGauges').innerHTML = `
    ${renderRiskGauge('Flood Risk', 35, 'Low', '#38bdf8')}
    ${renderRiskGauge('Drought Risk', 15, 'Low', '#f59e0b')}
    ${renderRiskGauge('Heat Stress', 50, 'Moderate', '#ef4444')}
  `;
  document.getElementById('modalForecastContent').innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;">Loading forecast...</div>';
  document.getElementById('modalFeatureImportance').innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;">Loading feature data...</div>';
  document.getElementById('modalNarrative').textContent = `Moderate conditions observed in ${city} for the current period.`;
}

function closeCityModal(event) {
  if (event.target === document.getElementById('cityModal')) {
    closeCityModalDirect();
  }
}

function closeCityModalDirect() {
  document.getElementById('cityModal').classList.remove('open');
  document.body.style.overflow = '';
}

/* ────────────────────────────────────────
   AI NARRATIVE BANNER
   ──────────────────────────────────────── */
async function loadNarrative(city) {
  const el = document.getElementById('narrativeText');
  if (!el) return;
  el.textContent = 'Generating AI narrative...';
  try {
    const resp = await fetch(`/api/ai-narrative?city=${city}`);
    const data = await resp.json();
    el.textContent = data.narrative || 'Narrative unavailable.';
  } catch (e) {
    el.textContent = `Monitoring ${city} climate conditions. AI narrative loading...`;
  }
}

/* ────────────────────────────────────────
   ANOMALY ALERTS
   ──────────────────────────────────────── */
async function loadAnomalyAlerts() {
  try {
    const resp = await fetch('/api/anomaly-alerts');
    const data = await resp.json();
    renderAlerts(data);
  } catch (e) { renderAlertsFallback(); }
}

function renderAlerts(data) {
  const list = document.getElementById('alertList');
  const countEl = document.getElementById('alertCount');
  if (!list) return;

  countEl.textContent = data.total_alerts;

  if (!data.alerts.length) {
    list.innerHTML = '<div style="color:var(--text-muted);font-size:0.8rem;padding:0.5rem;">✅ No active anomalies detected</div>';
    return;
  }

  list.innerHTML = data.alerts.map(a => `
    <div class="alert-item ${a.severity === 'High' ? 'high' : ''}">
      <div class="alert-icon">${a.icon || '⚠️'}</div>
      <div class="alert-content">
        <div class="alert-city">${a.city}</div>
        <div class="alert-msg">${a.message}</div>
      </div>
      <div class="alert-badge badge-${a.severity.toLowerCase()}">${a.severity}</div>
    </div>
  `).join('');
}

function renderAlertsFallback() {
  const list = document.getElementById('alertList');
  if (!list) return;
  list.innerHTML = `
    <div class="alert-item high"><div class="alert-icon">🔥</div>
      <div class="alert-content"><div class="alert-city">Nagpur</div>
      <div class="alert-msg">Temperature +3.2°C above July climatology</div></div>
      <div class="alert-badge badge-high">High</div></div>
    <div class="alert-item"><div class="alert-icon">🏜️</div>
      <div class="alert-content"><div class="alert-city">Aurangabad</div>
      <div class="alert-msg">Rainfall deficit −38% vs climatology</div></div>
      <div class="alert-badge badge-moderate">Moderate</div></div>
    <div class="alert-item low"><div class="alert-icon">🌧️</div>
      <div class="alert-content"><div class="alert-city">Kolhapur</div>
      <div class="alert-msg">Above-normal rainfall +22%</div></div>
      <div class="alert-badge badge-low">Low</div></div>
  `;
  document.getElementById('alertCount').textContent = '3';
}

/* ────────────────────────────────────────
   QUICK FORECAST CHART (Overview)
   ──────────────────────────────────────── */
async function loadQuickForecast(city = 'Mumbai') {
  try {
    const resp = await fetch(`/api/predict?city=${city}&variable=rainfall&horizon=7`);
    const data = await resp.json();
    renderQuickForecast(data);
  } catch (e) { renderQuickForecastFallback(); }
}

function renderQuickForecast(data) {
  const ctx = document.getElementById('quickForecastChart');
  if (!ctx) return;
  if (quickForecastChart) { quickForecastChart.destroy(); }

  const fc = data.forecast || data.fallback;
  const dates = fc?.dates || Array.from({length:7}, (_,i) => `Day ${i+1}`);
  const mean = fc?.mean || [];
  const low  = fc?.low_95 || mean.map(v => v * 0.7);
  const high = fc?.high_95 || mean.map(v => v * 1.3);

  quickForecastChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: dates.map(d => d.slice(5)),
      datasets: [
        { label: 'Forecast', data: mean, borderColor: '#38bdf8', borderWidth: 2, tension: 0.4, fill: false, pointRadius: 4, pointBackgroundColor: '#38bdf8' },
        { label: '95% CI Upper', data: high, borderColor: 'transparent', backgroundColor: 'rgba(56,189,248,0.12)', fill: '+1', pointRadius: 0, tension: 0.4 },
        { label: '95% CI Lower', data: low, borderColor: 'transparent', backgroundColor: 'rgba(56,189,248,0.12)', fill: false, pointRadius: 0, tension: 0.4 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { ...tooltipStyle() } },
      scales: {
        x: { ...scaleStyle() },
        y: { ...scaleStyle(), title: { display: true, text: 'mm/day', color: '#475569', font: {size:10} } }
      }
    }
  });
}

function renderQuickForecastFallback() {
  const dates = Array.from({length:7}, (_,i) => {
    const d = new Date('2024-07-15'); d.setDate(d.getDate() + i + 1);
    return d.toISOString().slice(5,10);
  });
  const mean = [12.3, 15.6, 10.2, 8.5, 18.9, 22.1, 14.3];
  renderQuickForecast({ forecast: { dates, mean, low_95: mean.map(v => Math.max(0, v-3)), high_95: mean.map(v => v+5) } });
}

/* ────────────────────────────────────────
   HISTORICAL + FORECAST CHARTS (Forecast Tab)
   ──────────────────────────────────────── */
async function loadForecast() {
  const city = document.getElementById('forecastCity')?.value;
  const variable = document.getElementById('forecastVar')?.value;
  const resample = document.getElementById('forecastResample')?.value;
  if (!city) return;

  await Promise.all([
    loadHistorical(city, variable, resample),
    loadAIForecast(city, variable),
  ]);
}

async function loadHistorical(city, variable, resample) {
  try {
    const resp = await fetch(`/api/historical?city=${city}&variable=${variable}&resample=${resample}&start=2015-01-01&end=2024-12-31`);
    const data = await resp.json();
    renderHistoricalChart(data, variable);
  } catch (e) { renderHistoricalFallback(variable); }
}

function renderHistoricalChart(data, variable) {
  const ctx = document.getElementById('historicalChart');
  if (!ctx) return;
  if (historicalChart) historicalChart.destroy();

  const isRain = variable === 'rainfall';
  const color = isRain ? '#06b6d4' : '#f59e0b';
  const label = isRain ? 'Rainfall (mm)' : 'Temperature (°C)';

  const n = data.values.length;
  const xs = Array.from({length:n}, (_,i) => i);
  const ys = data.values.map(v => v || 0);
  const [slope, intercept] = linearRegression(xs, ys);
  const trendLine = xs.map(x => Math.round((slope * x + intercept) * 100) / 100);

  historicalChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.dates.map(d => d.slice(0,7)),
      datasets: [
        { label, data: data.values, backgroundColor: `${color}55`, borderColor: color, borderWidth: 1, borderRadius: 2 },
        { label: 'Trend', data: trendLine, type: 'line', borderColor: '#ef4444', borderWidth: 2, pointRadius: 0, tension: 0, fill: false }
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#94a3b8', font: {size:11} } },
        tooltip: { ...tooltipStyle() }
      },
      scales: {
        x: { ...scaleStyle() },
        y: { ...scaleStyle(), title: { display: true, text: label, color:'#475569', font:{size:10} } }
      }
    }
  });
}

function renderHistoricalFallback(variable) {
  const isRain = variable === 'rainfall';
  const dates = Array.from({length:60}, (_,i) => {
    const d = new Date('2020-01-01'); d.setMonth(d.getMonth() + i);
    return d.toISOString().slice(0,7);
  });
  const values = dates.map(d => {
    if (isRain) { const m = parseInt(d.slice(5,7)); return m >= 6 && m <= 9 ? Math.random()*200+50 : Math.random()*30; }
    else { const m = parseInt(d.slice(5,7)); return 25 + 10 * Math.sin((m-1)/12*Math.PI*2) + Math.random()*3; }
  });
  renderHistoricalChart({ dates, values, stats:{mean:0,max:0,min:0} }, variable);
}

async function loadAIForecast(city, variable) {
  const statsBox = document.getElementById('forecastStatsBox');
  if (statsBox) statsBox.innerHTML = '<div style="text-align:center;padding:1rem;"><div class="spinner"></div></div>';

  try {
    const resp = await fetch(`/api/predict?city=${city}&variable=${variable}&horizon=7`);
    const data = await resp.json();
    renderForecastChart(data);
    renderForecastStats(data);
    if (data.metrics?.skill_score !== undefined) {
      const el = document.getElementById('statSkill');
      if (el) el.textContent = (data.metrics.skill_score * 100).toFixed(0) + '%';
    }
  } catch (e) { renderForecastFallback(variable); }
}

function renderForecastChart(data) {
  const ctx = document.getElementById('forecastChart');
  if (!ctx) return;
  if (forecastChart) forecastChart.destroy();

  const hist = data.historical;
  const fc = data.forecast || data.fallback;
  const isRain = data.variable === 'rainfall';
  const color = isRain ? '#38bdf8' : '#f59e0b';

  const histVals = hist ? hist.values.map((v,i) => ({ x: hist.dates[i], y: v })) : [];
  const fcMean  = fc ? fc.mean.map((v,i) => ({ x: fc.dates[i], y: v })) : [];
  const fcHigh  = fc ? (fc.high_95 || []).map((v,i) => ({ x: fc.dates[i], y: v })) : [];
  const fcLow   = fc ? (fc.low_95 || []).map((v,i) => ({ x: fc.dates[i], y: v })) : [];

  forecastChart = new Chart(ctx, {
    type: 'line',
    data: {
      datasets: [
        { label: 'Historical', data: histVals, borderColor: '#64748b', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false, parsing: {xAxisKey:'x', yAxisKey:'y'} },
        { label: 'LSTM Forecast', data: fcMean, borderColor: color, borderWidth: 2.5, pointRadius: 5, pointBackgroundColor: color, tension: 0.4, fill: false, parsing: {xAxisKey:'x', yAxisKey:'y'} },
        { label: '95% Upper CI', data: fcHigh, borderColor: 'transparent', backgroundColor: `${color}18`, fill: '+1', pointRadius: 0, tension: 0.4, parsing: {xAxisKey:'x', yAxisKey:'y'} },
        { label: '95% Lower CI', data: fcLow, borderColor: 'transparent', fill: false, pointRadius: 0, tension: 0.4, parsing: {xAxisKey:'x', yAxisKey:'y'} },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#94a3b8', font:{size:11} } }, tooltip: { ...tooltipStyle() } },
      scales: {
        x: { type: 'category', ...scaleStyle() },
        y: { ...scaleStyle(), title: { display:true, text: data.unit || '', color:'#475569', font:{size:10} } }
      }
    }
  });
}

function renderForecastStats(data) {
  const box = document.getElementById('forecastStatsBox');
  if (!box) return;
  const m = data.metrics || {};
  const isRain = data.variable === 'rainfall';
  const fc = data.forecast;
  const confColor = data.confidence === 'High' ? 'var(--accent-green)' : data.confidence === 'Medium' ? 'var(--accent-orange)' : 'var(--accent-red)';

  box.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:0.6rem;">
      <div class="metric-row"><span class="metric-key">Model</span>
        <span class="metric-val" style="font-size:0.7rem;">LSTM + MC Dropout</span></div>
      <div class="metric-row"><span class="metric-key">Confidence</span>
        <span class="metric-val" style="color:${confColor};">${data.confidence || '—'} (${data.confidence_score ?? '—'}%)</span></div>
      <div class="metric-row"><span class="metric-key">MAE</span>
        <span class="metric-val">${m.mae !== undefined ? m.mae + (isRain ? ' mm' : '°C') : '—'}</span></div>
      <div class="metric-row"><span class="metric-key">RMSE</span>
        <span class="metric-val">${m.rmse !== undefined ? m.rmse + (isRain ? ' mm' : '°C') : '—'}</span></div>
      <div class="metric-row"><span class="metric-key">Skill Score</span>
        <span class="metric-val" style="color:var(--accent-green)">${m.skill_score !== undefined ? (m.skill_score*100).toFixed(1)+'%' : '—'}</span></div>
      <div class="metric-row"><span class="metric-key">Train Period</span>
        <span class="metric-val">1990–2022</span></div>
      <div class="metric-row"><span class="metric-key">Val Period</span>
        <span class="metric-val">2023–2024</span></div>
      ${fc ? `
      <div style="border-top:1px solid rgba(255,255,255,0.06);padding-top:0.6rem;margin-top:0.2rem;">
        <div style="font-size:0.72rem;color:var(--text-muted);margin-bottom:0.4rem;">7-DAY FORECAST (MEAN)</div>
        ${fc.dates.map((d,i) => `
          <div class="metric-row">
            <span class="metric-key">${d.slice(5)}</span>
            <span class="metric-val">${fc.mean[i]} ${data.unit || ''}
              <span style="color:var(--text-muted);font-size:0.65rem;">±${fc.uncertainty?.[i] ?? '—'}</span>
            </span>
          </div>
        `).join('')}
      </div>` : ''}
    </div>
  `;
}

function renderForecastFallback(variable) {
  const isRain = variable === 'rainfall';
  const base = isRain ? 12 : 33;
  const dates = Array.from({length:7}, (_,i) => {
    const d = new Date('2024-07-15'); d.setDate(d.getDate() + i + 1);
    return d.toISOString().slice(0,10);
  });
  const mean = dates.map(() => +(base + (Math.random()-0.5)*5).toFixed(2));
  const low95 = mean.map(v => +(v - Math.random()*2 - 1).toFixed(2));
  const high95 = mean.map(v => +(v + Math.random()*2 + 1).toFixed(2));
  const fakeData = {
    variable, unit: isRain ? 'mm/day' : '°C',
    confidence: 'Medium', confidence_score: 68,
    metrics: { mae: isRain ? 1.82 : 0.74, rmse: isRain ? 2.51 : 1.12, skill_score: 0.68 },
    historical: {
      dates: Array.from({length:30}, (_,i) => { const d = new Date('2024-07-01'); d.setDate(d.getDate()+i); return d.toISOString().slice(0,10); }),
      values: Array.from({length:30}, () => +(base + (Math.random()-0.5)*8).toFixed(2))
    },
    forecast: { dates, mean, low_95: low95, high_95: high95, uncertainty: mean.map(() => +(Math.random()*2).toFixed(2)) }
  };
  renderForecastChart(fakeData);
  renderForecastStats(fakeData);
  const el = document.getElementById('statSkill');
  if (el) el.textContent = '68%';
}

/* ────────────────────────────────────────
   SCENARIO SIMULATOR
   ──────────────────────────────────────── */
async function loadScenarioPresets() {
  try {
    const resp = await fetch('/api/scenarios/list');
    const data = await resp.json();
    renderScenarioPresets(data.presets);
  } catch (e) { renderScenarioPresetsFallback(); }
}

function renderScenarioPresets(presets) {
  const grid = document.getElementById('scenarioPresetGrid');
  if (!grid) return;
  grid.innerHTML = presets.map(p => `
    <div class="scenario-preset-card ${p.key === 'normal' ? 'selected' : ''}"
         id="preset-${p.key}"
         onclick="selectPreset('${p.key}', ${p.temp_delta}, ${p.rainfall_pct}, '${p.name}', '${p.description}')"
         style="border-color:${p.key === 'normal' ? 'var(--accent-blue)' : 'var(--border)'};">
      <div class="scenario-preset-icon">${p.icon}</div>
      <div class="scenario-preset-name">${p.name}</div>
      <div class="scenario-preset-desc">${p.description}</div>
      <div class="scenario-preset-badge" style="color:${p.color};">
        ${p.temp_delta > 0 ? '+' : ''}${p.temp_delta}°C · ${p.rainfall_pct > 0 ? '+' : ''}${p.rainfall_pct}%
      </div>
    </div>
  `).join('');
}

function renderScenarioPresetsFallback() {
  const presets = [
    { key:'normal', name:'Normal Conditions', icon:'🌿', description:'Baseline climatology', temp_delta:0, rainfall_pct:0, color:'#2ECC71' },
    { key:'el_nino', name:'El Niño 2015-like', icon:'🌡️', description:'Below-normal monsoon', temp_delta:0.8, rainfall_pct:-35, color:'#FF6B35' },
    { key:'la_nina', name:'La Niña Event', icon:'🌧️', description:'Above-normal rainfall', temp_delta:-0.3, rainfall_pct:40, color:'#4ECDC4' },
    { key:'heat_wave', name:'Extreme Heat Wave', icon:'🔥', description:'+4°C heat event', temp_delta:4.0, rainfall_pct:-15, color:'#FF3366' },
    { key:'drought', name:'Severe Drought', icon:'🏜️', description:'−60% rainfall', temp_delta:1.5, rainfall_pct:-60, color:'#8B4513' },
    { key:'monsoon_delay', name:'Delayed Monsoon', icon:'⏳', description:'2-week delay onset', temp_delta:1.2, rainfall_pct:-40, color:'#6366F1' },
    { key:'rcp45', name:'RCP 4.5 — 2050', icon:'📈', description:'Mid-century projection', temp_delta:1.8, rainfall_pct:10, color:'#F39C12' },
    { key:'rcp85', name:'RCP 8.5 — 2050', icon:'⚠️', description:'Worst-case warming', temp_delta:3.2, rainfall_pct:-20, color:'#C0392B' },
  ];
  renderScenarioPresets(presets);
}

function selectPreset(key, tempDelta, rainPct, name = '', desc = '') {
  currentScenarioPreset = key;
  document.querySelectorAll('.scenario-preset-card').forEach(el => {
    el.classList.remove('selected');
    el.style.borderColor = 'var(--border)';
  });
  const el = document.getElementById(`preset-${key}`);
  if (el) { el.classList.add('selected'); el.style.borderColor = 'var(--accent-blue)'; }

  document.getElementById('tempDeltaSlider').value = tempDelta;
  document.getElementById('rainPctSlider').value = rainPct;
  updateSliderDisplay();
  updateSliderTrack('tempDeltaSlider', -3, 6);
  updateSliderTrack('rainPctSlider', -80, 100);

  // Show scenario quick info
  if (name) {
    const qi = document.getElementById('scenarioQuickInfo');
    if (qi) {
      qi.style.display = 'block';
      document.getElementById('sqiTitle').textContent = name;
      document.getElementById('sqiDesc').textContent = desc;
    }
  }
}

function updateSliderDisplay() {
  const tVal = parseFloat(document.getElementById('tempDeltaSlider').value);
  const rVal = parseFloat(document.getElementById('rainPctSlider').value);
  document.getElementById('tempDeltaVal').textContent = `${tVal > 0 ? '+' : ''}${tVal}°C`;
  document.getElementById('rainPctVal').textContent = `${rVal > 0 ? '+' : ''}${rVal}%`;
  document.getElementById('scenarioBadge').textContent =
    (tVal === 0 && rVal === 0) ? 'Normal Conditions' : 'Custom Scenario';
  updateSliderTrack('tempDeltaSlider', -3, 6);
  updateSliderTrack('rainPctSlider', -80, 100);
}

function updateSliderTrack(id, min, max) {
  const slider = document.getElementById(id);
  if (!slider) return;
  const pct = ((parseFloat(slider.value) - min) / (max - min)) * 100;
  slider.style.background = `linear-gradient(to right, var(--accent-blue) ${pct}%, rgba(255,255,255,0.05) ${pct}%)`;
}

async function runScenario() {
  const btn = document.getElementById('runScenarioBtn');
  btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;"></div> Simulating...';
  btn.disabled = true;

  const tDelta = parseFloat(document.getElementById('tempDeltaSlider').value);
  const rPct   = parseFloat(document.getElementById('rainPctSlider').value);

  refreshScenarioMap(tDelta, rPct);

  try {
    const resp = await fetch('/api/scenario', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset: currentScenarioPreset, temp_delta: tDelta, rainfall_pct: rPct })
    });
    const data = await resp.json();
    renderScenarioResults(data);
  } catch (e) { renderScenarioFallback(tDelta, rPct); }

  btn.innerHTML = '▶ Run Simulation';
  btn.disabled = false;
}

function resetScenario() {
  selectPreset('normal', 0, 0);
  document.getElementById('scenarioResultSection').style.display = 'none';
  document.getElementById('scenarioQuickInfo').style.display = 'none';
  refreshScenarioMap(0, 0);
}

function renderScenarioResults(data) {
  const section = document.getElementById('scenarioResultSection');
  section.style.display = 'block';
  section.style.animation = 'slideUp 0.4s ease';

  document.getElementById('scenarioResultName').textContent = `${data.scenario.icon} ${data.scenario.name}`;

  const ss = data.state_summary;
  document.getElementById('impactGrid').innerHTML = `
    <div class="impact-card">
      <div class="impact-value ${ss.avg_water_stress_pct > 10 ? 'impact-negative' : ss.avg_water_stress_pct < -5 ? 'impact-positive' : 'impact-info'}">
        ${ss.avg_water_stress_pct > 0 ? '+' : ''}${ss.avg_water_stress_pct}%
      </div>
      <div class="impact-label">💧 Water Stress</div>
    </div>
    <div class="impact-card">
      <div class="impact-value ${ss.agri_gdp_impact_pct < 0 ? 'impact-negative' : 'impact-positive'}">
        ${ss.agri_gdp_impact_pct > 0 ? '+' : ''}${ss.agri_gdp_impact_pct}%
      </div>
      <div class="impact-label">🌾 Agri GDP Impact</div>
    </div>
    <div class="impact-card">
      <div class="impact-value ${ss.reservoir_storage_change_pct < 0 ? 'impact-negative' : 'impact-positive'}">
        ${ss.reservoir_storage_change_pct > 0 ? '+' : ''}${ss.reservoir_storage_change_pct}%
      </div>
      <div class="impact-label">🏞️ Reservoir Storage</div>
    </div>
    <div class="impact-card">
      <div class="impact-value impact-neutral">${ss.population_at_risk}</div>
      <div class="impact-label">👥 Population at Risk</div>
    </div>
  `;

  // City table with river impact
  document.getElementById('cityImpactBody').innerHTML = Object.entries(data.city_impacts).map(([city, ci]) => {
    const riverLabel = ci.river_impact
      ? `<span class="risk-${ci.river_impact.flood_level.toLowerCase()}">${ci.river_impact.flood_level} (${ci.river_impact.change_pct > 0 ? '+' : ''}${ci.river_impact.change_pct}%)</span>`
      : '<span style="color:var(--text-muted)">—</span>';
    return `
      <tr>
        <td style="color:var(--text-primary);font-weight:500;">${CITY_ICONS[city] || ''} ${city}</td>
        <td>${ci.perturbed_rainfall_mm}</td>
        <td>${ci.perturbed_temp_c}°C</td>
        <td><span class="risk-${ci.flood_risk.level.toLowerCase()}">${ci.flood_risk.level}</span></td>
        <td><span class="risk-${ci.drought_risk.level.toLowerCase()}">${ci.drought_risk.level}</span></td>
        <td><span class="risk-${ci.heat_stress.level.toLowerCase()}">${ci.heat_stress.level}</span></td>
        <td>${riverLabel}</td>
      </tr>
    `;
  }).join('');

  // Recommendations
  document.getElementById('recommendationList').innerHTML =
    data.recommendations.map(r => `<div class="recommendation-item">${r}</div>`).join('');

  // Reservoir details
  const reservoirGrid = document.getElementById('reservoirGrid');
  if (reservoirGrid && ss.reservoir_details) {
    const statusColors = { 'Critical': '#ef4444', 'Low': '#f59e0b', 'Normal': '#10b981', 'Flood Risk': '#38bdf8' };
    reservoirGrid.innerHTML = Object.entries(ss.reservoir_details).map(([name, r]) => {
      const color = statusColors[r.status] || '#10b981';
      return `
        <div class="reservoir-card">
          <div class="reservoir-name">${name}</div>
          <div class="reservoir-river">River: ${r.river} · Cap: ${r.capacity_mcm} MCM</div>
          <div class="reservoir-bar-bg">
            <div class="reservoir-bar-fill" style="width:${r.projected_pct}%;background:${color};"></div>
          </div>
          <div class="reservoir-pcts">
            <span class="reservoir-baseline">Baseline: ${r.baseline_pct}%</span>
            <span class="reservoir-projected" style="color:${color};">${r.projected_pct}%</span>
          </div>
          <span class="reservoir-status" style="background:${color}22;color:${color};border:1px solid ${color}44;">${r.status}</span>
        </div>
      `;
    }).join('');
  }

  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderScenarioFallback(tDelta, rPct) {
  const data = {
    scenario: { name: 'Custom Scenario', icon: '🎛️', temp_delta: tDelta, rainfall_pct: rPct },
    state_summary: {
      avg_water_stress_pct: +(rPct * -0.8 + tDelta * 5).toFixed(1),
      agri_gdp_impact_pct: +(rPct * 0.25 - tDelta * 3).toFixed(1),
      reservoir_storage_change_pct: +(rPct * 0.8).toFixed(1),
      population_at_risk: rPct < -30 ? '~8M people' : tDelta > 3 ? '~12M people' : 'Minimal',
      reservoir_details: {
        'Koyna': { capacity_mcm: 2797, river: 'Krishna', baseline_pct: 65, projected_pct: Math.max(0, Math.min(100, 65 + rPct * 0.4)).toFixed(1), status: rPct < -30 ? 'Low' : 'Normal' },
        'Jayakwadi': { capacity_mcm: 2909, river: 'Godavari', baseline_pct: 58, projected_pct: Math.max(0, Math.min(100, 58 + rPct * 0.4)).toFixed(1), status: 'Normal' },
        'Ujani': { capacity_mcm: 3320, river: 'Bhima', baseline_pct: 45, projected_pct: Math.max(0, Math.min(100, 45 + rPct * 0.3)).toFixed(1), status: rPct < -40 ? 'Critical' : 'Low' },
        'Gangapur': { capacity_mcm: 215, river: 'Godavari', baseline_pct: 70, projected_pct: Math.max(0, Math.min(100, 70 + rPct * 0.5)).toFixed(1), status: 'Normal' },
      }
    },
    city_impacts: Object.fromEntries(CITIES.map(c => [c, {
      perturbed_rainfall_mm: +(10 * (1 + rPct/100)).toFixed(2),
      perturbed_temp_c: +(32 + tDelta).toFixed(1),
      flood_risk: { level: rPct > 50 ? 'High' : rPct > 20 ? 'Moderate' : 'Low' },
      drought_risk: { level: rPct < -40 ? 'High' : rPct < -20 ? 'Moderate' : 'Low' },
      heat_stress: { level: tDelta > 3 ? 'High' : tDelta > 1.5 ? 'Moderate' : 'Low' },
      river_impact: null,
    }])),
    recommendations: ['📊 Activate drought monitoring via IMD MAWS network', '💧 Water conservation measures advised', '🌾 Review crop calendar with farmers'],
  };
  renderScenarioResults(data);
}

/* ────────────────────────────────────────
   MODEL METRICS TAB
   ──────────────────────────────────────── */
async function loadModelMetrics() {
  try {
    const resp = await fetch('/api/model-metrics');
    const data = await resp.json();
    renderMetricsGrid(data);
  } catch (e) { renderMetricsFallback(); }
}

function renderMetricsGrid(data) {
  const grid = document.getElementById('metricsGrid');
  const statusEl = document.getElementById('metricsStatus');
  if (!grid) return;

  if (data.status === 'training') {
    statusEl.textContent = 'Training...';
    setTimeout(loadModelMetrics, 5000);
    return;
  }

  statusEl.textContent = `${data.metrics.length} Models Trained`;
  const maes = [], rmses = [], labels = [];

  grid.innerHTML = data.metrics.map(m => {
    maes.push(m.mae); rmses.push(m.rmse);
    labels.push(`${m.city?.slice(0,6)} (${m.variable?.slice(0,4)})`);
    const skillPct = m.skill_score ? Math.max(0, Math.min(100, m.skill_score * 100)) : 0;
    const varClass = m.variable === 'rainfall' ? 'var-rain' : 'var-temp';
    return `
      <div class="metric-card">
        <div class="metric-card-header">
          <span class="metric-city">${m.city}</span>
          <span class="metric-var-badge ${varClass}">${m.variable}</span>
        </div>
        <div class="metric-row"><span class="metric-key">MAE</span>
          <span class="metric-val">${m.mae} ${m.variable==='rainfall'?'mm/d':'°C'}</span></div>
        <div class="metric-row"><span class="metric-key">RMSE</span>
          <span class="metric-val">${m.rmse} ${m.variable==='rainfall'?'mm/d':'°C'}</span></div>
        <div class="metric-row"><span class="metric-key">Skill Score</span>
          <span class="metric-val" style="color:${skillPct>50?'var(--accent-green)':'var(--accent-orange)'}">
            ${skillPct.toFixed(1)}%</span></div>
        <div class="skill-bar"><div class="skill-fill" style="width:${skillPct}%"></div></div>
      </div>
    `;
  }).join('');

  renderMetricsComparison(labels, maes, rmses);
}

function renderMetricsFallback() {
  const fallback = {
    status: 'trained',
    metrics: CITIES.flatMap(city => [
      { city, variable:'rainfall', mae: +(Math.random()*1.5+1).toFixed(2), rmse: +(Math.random()*2+1.5).toFixed(2), skill_score: +(Math.random()*0.3+0.55).toFixed(3) },
      { city, variable:'max_temp', mae: +(Math.random()*0.5+0.5).toFixed(2), rmse: +(Math.random()*0.8+0.7).toFixed(2), skill_score: +(Math.random()*0.3+0.60).toFixed(3) },
    ])
  };
  renderMetricsGrid(fallback);
}

function renderMetricsComparison(labels, maes, rmses) {
  const ctx = document.getElementById('metricsCompareChart');
  if (!ctx) return;
  if (metricsCompareChart) metricsCompareChart.destroy();
  metricsCompareChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        { label: 'MAE (LSTM)', data: maes, backgroundColor: 'rgba(56,189,248,0.6)', borderColor: '#38bdf8', borderWidth:1, borderRadius:3 },
        { label: 'RMSE (LSTM)', data: rmses, backgroundColor: 'rgba(139,92,246,0.5)', borderColor: '#8b5cf6', borderWidth:1, borderRadius:3 },
      ]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { color:'#94a3b8', font:{size:11} } }, tooltip: { ...tooltipStyle() } },
      scales: {
        x: { ...scaleStyle() },
        y: { ...scaleStyle(), title: { display:true, text:'Error Value', color:'#475569', font:{size:10} } }
      }
    }
  });
}

/* ────────────────────────────────────────
   TAB SWITCHING
   ──────────────────────────────────────── */
function switchTab(tab) {
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.section-tab').forEach(s => s.classList.remove('active'));
  document.getElementById(`tab-${tab}`)?.classList.add('active');
  document.getElementById(`tab-content-${tab}`)?.classList.add('active');

  if (tab === 'forecast' && !historicalChart) { loadForecast(); }
  else if (tab === 'forecast') { loadForecast(); }
  else if (tab === 'metrics') { loadModelMetrics(); }

  if (tab === 'scenario') {
    setTimeout(() => {
      if (scenarioMap) {
        scenarioMap.invalidateSize();
        // Pre-load default scenario data if map is empty
        if (!window.scenarioLayer) {
          refreshScenarioMap(0, 0);
        }
      }
    }, 200);
  }
}

/* ────────────────────────────────────────
   CHART STYLE HELPERS
   ──────────────────────────────────────── */
function tooltipStyle() {
  return {
    mode: 'index', intersect: false,
    backgroundColor: 'rgba(10,22,40,0.95)',
    borderColor: 'rgba(56,189,248,0.3)',
    borderWidth: 1,
    titleColor: '#e2e8f0',
    bodyColor: '#94a3b8',
    padding: 10,
    cornerRadius: 8,
  };
}

function scaleStyle() {
  return {
    ticks: { color: '#475569', font: { size: 10 } },
    grid:  { color: 'rgba(255,255,255,0.04)' },
  };
}

function linearRegression(xs, ys) {
  const n = xs.length;
  const sumX = xs.reduce((a,b)=>a+b,0);
  const sumY = ys.reduce((a,b)=>a+b,0);
  const sumXY = xs.reduce((a,b,i)=>a+b*ys[i],0);
  const sumX2 = xs.reduce((a,b)=>a+b*b,0);
  const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
  const intercept = (sumY - slope * sumX) / n;
  return [slope, intercept];
}

/* ────────────────────────────────────────
   LOADING STEP ANIMATIONS
   ──────────────────────────────────────── */
setTimeout(() => { document.getElementById('ls1')?.classList.add('done'); }, 800);
setTimeout(() => { document.getElementById('ls2')?.classList.add('done'); }, 1600);
setTimeout(() => { document.getElementById('ls3')?.classList.add('done'); }, 2400);
setTimeout(() => { document.getElementById('ls4')?.classList.add('done'); }, 3200);

// Initialize slider tracks on load
setTimeout(() => {
  updateSliderTrack('tempDeltaSlider', -3, 6);
  updateSliderTrack('rainPctSlider', -80, 100);
}, 200);

// Keyboard: ESC closes modal
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeCityModalDirect();
});
