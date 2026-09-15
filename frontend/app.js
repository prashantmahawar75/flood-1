(() => {
  const $ = (id) => document.getElementById(id);
  const state = {
    map: null,
    mapMode: null,
    origin: null,
    destination: null,
    originMarker: null,
    destinationMarker: null,
    routeLayer: null,
    riskPoints: [],
    riskLayers: [],
    facilities: [],
    facilityLayers: [],
    stations: [],
    stationLayers: [],
  };

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[char]));
  }

  const riskColor = (probability) => probability >= 0.8 ? '#ff5c73' : probability >= 0.4 ? '#ffd166' : '#4ee59d';

  function normalizePoint(point) {
    const lat = Number(point?.lat);
    const rawLon = point && point.lon != null ? point.lon : point && point.lng;
    const lon = Number(rawLon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
      throw new Error('Invalid map coordinates. Please choose the point again.');
    }
    return { lat, lon };
  }

  const fmtCoord = (point) => `${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}`;
  const fmtKm = (meters) => `${(meters / 1000).toFixed(meters < 10000 ? 2 : 1)} km`;
  const facilityIcon = (category) => ({ shelter: '🛟', hospital: '🏥', clinic: '➕', community_centre: '🏛️', school: '🏫', college: '🎓' }[category] || '📍');

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    let payload = null;
    try { payload = await response.json(); } catch (_) { payload = { detail: response.statusText }; }
    if (!response.ok) throw new Error(payload?.detail || `Request failed (${response.status})`);
    return payload;
  }

  function initMap() {
    state.map = L.map('map', { zoomControl: true }).setView([10.85, 76.27], 8);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(state.map);
    state.map.on('click', onMapClick);
  }

  function markerIcon(color, label) {
    return L.divIcon({
      className: '',
      html: `<div style="width:28px;height:28px;border-radius:50%;display:grid;place-items:center;background:${color};color:#041017;border:3px solid white;box-shadow:0 5px 16px rgba(0,0,0,.35);font-weight:900;font-size:11px">${label}</div>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });
  }

  function setOrigin(point, label = 'Origin') {
    try {
      const normalized = normalizePoint(point);
      state.origin = { ...normalized, label };
      if (state.originMarker) state.map.removeLayer(state.originMarker);
      state.originMarker = L.marker([state.origin.lat, state.origin.lon], { icon: markerIcon('#39d7ff', 'A') })
        .addTo(state.map).bindPopup(`<b>${escapeHtml(label)}</b><br>${fmtCoord(state.origin)}`);
      $('originReadout').classList.remove('muted');
      $('originReadout').textContent = `${label}: ${fmtCoord(state.origin)}`;
      clearRouteError();
      return true;
    } catch (error) {
      showRouteError(error.message || 'Invalid map coordinates.');
      return false;
    }
  }

  function setDestination(point, label = 'Destination') {
    try {
      const normalized = normalizePoint(point);
      state.destination = { ...normalized, label };
      if (state.destinationMarker) state.map.removeLayer(state.destinationMarker);
      state.destinationMarker = L.marker([state.destination.lat, state.destination.lon], { icon: markerIcon('#4ee59d', 'B') })
        .addTo(state.map).bindPopup(`<b>${escapeHtml(label)}</b><br>${fmtCoord(state.destination)}`);
      $('destinationReadout').classList.remove('muted');
      $('destinationReadout').textContent = `${label}: ${fmtCoord(state.destination)}`;
      clearRouteError();
      return true;
    } catch (error) {
      showRouteError(error.message || 'Invalid map coordinates.');
      return false;
    }
  }

  function setMapMode(mode) {
    state.mapMode = mode;
    $('mapMode').textContent = mode === 'origin' ? 'Click map to set origin' : mode === 'destination' ? 'Click map to set destination' : 'Map ready';
    $('cancelMapMode').classList.toggle('hidden', !mode);
    state.map.getContainer().style.cursor = mode ? 'crosshair' : '';
  }

  function onMapClick(event) {
    if (state.mapMode === 'origin') setOrigin(event.latlng, 'Map origin');
    if (state.mapMode === 'destination') setDestination(event.latlng, 'Map destination');
    if (state.mapMode) setMapMode(null);
  }

  async function checkHealth() {
    try {
      const data = await api('/api/health');
      $('apiStatus').textContent = `API online • RF AUC ${(data.model_metrics?.roc_auc || 0).toFixed(3)}`;
      $('apiStatus').classList.add('online');
    } catch (error) {
      $('apiStatus').textContent = 'API offline';
      $('apiStatus').classList.add('offline');
    }
  }

  async function loadStations() {
    state.stations = await api('/api/stations');
    const hilly = state.stations.filter((station) => station.is_hilly_catchment && Number.isFinite(station.slope));
    $('stationSelect').innerHTML = '<option value="">Choose a station…</option>' + hilly.map((station) =>
      `<option value="${escapeHtml(station.station_name)}">${escapeHtml(station.station_name)} • ${escapeHtml(station.district)}</option>`
    ).join('');
    hilly.slice(0, 20).forEach((station) => {
      const marker = L.circleMarker([station.lat, station.lon], {
        radius: 4, color: '#7fb8cc', fillColor: '#193f50', fillOpacity: .75, weight: 1,
      }).addTo(state.map).bindTooltip(`${escapeHtml(station.station_name)} • ${escapeHtml(station.river)}`);
      state.stationLayers.push(marker);
    });
  }

  function stationSelected() {
    const station = state.stations.find((item) => item.station_name === $('stationSelect').value);
    if (!station) return;
    setOrigin({ lat: station.lat, lon: station.lon }, station.station_name);
    if (Number.isFinite(station.slope)) $('slope').value = station.slope;
    if (Number.isFinite(station.drainage_density)) $('drainage').value = station.drainage_density;
    state.map.setView([station.lat, station.lon], 13);
  }

  function useMyLocation() {
    if (!navigator.geolocation) return showRouteError('Geolocation is not supported by this browser.');
    $('useLocationBtn').disabled = true;
    navigator.geolocation.getCurrentPosition(
      (position) => {
        $('useLocationBtn').disabled = false;
        setOrigin({ lat: position.coords.latitude, lon: position.coords.longitude }, 'My location');
        state.map.setView([position.coords.latitude, position.coords.longitude], 15);
      },
      (error) => {
        $('useLocationBtn').disabled = false;
        showRouteError(`Could not read location: ${error.message}`);
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
    );
  }

  function observationPayload() {
    return {
      rainfall_mm: Number($('rainfall').value),
      rainfall_3d_cum_mm: Number($('rainfall3d').value),
      river_discharge: Number($('discharge').value),
      river_discharge_roc: Number($('dischargeRoc').value),
      slope: Number($('slope').value),
      drainage_density: Number($('drainage').value),
      discharge_sensor_outage: $('sensorOutage').checked ? 1 : 0,
    };
  }

  async function scoreRisk() {
    if (!state.origin) return showRouteError('Choose an origin before scoring risk.');
    const btn = $('scoreRiskBtn');
    btn.disabled = true; btn.textContent = 'Scoring…';
    clearRouteError();
    try {
      const result = await api('/api/risk/predict', {
        method: 'POST',
        body: JSON.stringify({
          lat: state.origin.lat,
          lon: state.origin.lon,
          label: state.origin.label || 'Risk point',
          observation: observationPayload(),
        }),
      });
      const riskPoint = {
        lat: result.lat, lon: result.lon, probability: result.probability,
        slope: Number($('slope').value), label: result.label || `Risk point ${state.riskPoints.length + 1}`,
      };
      state.riskPoints.push(riskPoint);
      addRiskLayer(riskPoint);
      renderRiskPoints();
      renderLatestRisk(result);
    } catch (error) { showRouteError(error.message); }
    finally { btn.disabled = false; btn.textContent = 'Run ML risk score'; }
  }

  function renderLatestRisk(result) {
    const card = $('latestRisk');
    card.className = `risk-card ${result.tier === 'HIGH_RISK' ? 'high' : result.tier === 'WATCH' ? 'watch' : 'safe'}`;
    card.innerHTML = `<span class="risk-label">${result.tier.replace('_',' ')}</span><strong>${result.score.toFixed(1)}</strong><small>ML probability ${(result.probability * 100).toFixed(1)}%</small>`;
  }

  function addRiskLayer(point) {
    const color = riskColor(point.probability);
    const circle = L.circle([point.lat, point.lon], {
      radius: 700 + point.probability * 1800,
      color, weight: 2, fillColor: color, fillOpacity: .16,
    }).addTo(state.map).bindPopup(`<b>${point.label}</b><br>Flood risk: ${(point.probability * 100).toFixed(1)}%<br>Slope: ${point.slope.toFixed(1)}°`);
    state.riskLayers.push(circle);
  }

  function renderRiskPoints() {
    if (!state.riskPoints.length) {
      $('riskPointsList').innerHTML = '<div class="muted mini">None yet.</div>';
      return;
    }
    $('riskPointsList').innerHTML = state.riskPoints.map((point, index) =>
      `<div class="risk-item"><span>${index + 1}. ${escapeHtml(point.label)}</span><strong style="color:${riskColor(point.probability)}">${(point.probability * 100).toFixed(0)}%</strong></div>`
    ).join('');
  }

  function clearRiskPoints() {
    state.riskPoints = [];
    state.riskLayers.forEach((layer) => state.map.removeLayer(layer));
    state.riskLayers = [];
    renderRiskPoints();
    $('latestRisk').className = 'risk-card empty';
    $('latestRisk').innerHTML = '<span class="risk-label">Latest score</span><strong>—</strong><small>No active risk points.</small>';
  }

  async function loadFacilities() {
    if (!state.origin) return showRouteError('Choose an origin before searching facilities.');
    const btn = $('loadFacilitiesBtn');
    const status = $('facilityStatus');
    btn.disabled = true; btn.textContent = 'Searching live sources…'; clearRouteError();
    status.classList.remove('hidden');
    status.textContent = 'Searching emergency shelters, hospitals and community facilities…';
    try {
      state.facilities = await api(`/api/facilities/nearby?lat=${state.origin.lat}&lon=${state.origin.lon}&radius_m=10000`);
      renderFacilities();
      if (state.facilities.length) {
        const first = state.facilities[0];
        $('facilitySelect').value = first.osm_id;
        setDestination({ lat: first.lat, lon: first.lon }, first.name);
        const providers = [...new Set(state.facilities.map((item) => item.provider).filter(Boolean))];
        status.textContent = `${state.facilities.length} candidate facilities found${providers.length ? ` • ${providers.join(' / ')}` : ''}.`;
      } else {
        status.textContent = 'No mapped candidate facilities were found within 10 km.';
        showRouteError('No candidate refuge facilities were found within 10 km. Pick a destination on the map.');
      }
    } catch (error) {
      status.textContent = 'Automatic facility lookup is temporarily unavailable. Manual map destination still works.';
      showRouteError(error.message);
    } finally { btn.disabled = false; btn.textContent = 'Find nearby facilities'; }
  }

  function renderFacilities() {
    state.facilityLayers.forEach((layer) => state.map.removeLayer(layer));
    state.facilityLayers = [];
    $('facilitySelect').innerHTML = '<option value="">Choose a candidate facility…</option>' + state.facilities.map((facility) =>
      `<option value="${escapeHtml(facility.osm_id)}">${escapeHtml(facility.name)} • ${(facility.distance_m / 1000).toFixed(1)} km</option>`
    ).join('');

    $('facilityCards').innerHTML = state.facilities.length ? state.facilities.slice(0, 8).map((facility) =>
      `<button type="button" class="facility-card" data-osm-id="${escapeHtml(facility.osm_id)}">` +
        `<span class="facility-icon">${facilityIcon(facility.category)}</span>` +
        `<span class="facility-copy"><strong>${escapeHtml(facility.name)}</strong><small>${escapeHtml(facility.category.replaceAll('_', ' '))} • ${(facility.distance_m / 1000).toFixed(1)} km</small></span>` +
        `<span class="facility-arrow">›</span>` +
      `</button>`
    ).join('') : '<div class="muted mini">Search to see nearby candidate facilities.</div>';

    document.querySelectorAll('.facility-card').forEach((card) => {
      card.addEventListener('click', () => {
        const facility = state.facilities.find((item) => item.osm_id === card.dataset.osmId);
        if (!facility) return;
        $('facilitySelect').value = facility.osm_id;
        setDestination({ lat: facility.lat, lon: facility.lon }, facility.name);
        state.map.setView([facility.lat, facility.lon], Math.max(state.map.getZoom(), 14));
      });
    });

    state.facilities.forEach((facility) => {
      const marker = L.circleMarker([facility.lat, facility.lon], {
        radius: 6, color: '#4ee59d', fillColor: '#153c31', fillOpacity: .95, weight: 2,
      }).addTo(state.map).bindPopup(`<b>${escapeHtml(facility.name)}</b><br>${escapeHtml(facility.category)}<br>${(facility.distance_m/1000).toFixed(1)} km from origin<br><em>Candidate refuge facility • OSM</em>`);
      marker.on('click', () => {
        $('facilitySelect').value = facility.osm_id;
        setDestination({ lat: facility.lat, lon: facility.lon }, facility.name);
      });
      state.facilityLayers.push(marker);
    });
  }

  function facilitySelected() {
    const facility = state.facilities.find((item) => item.osm_id === $('facilitySelect').value);
    if (!facility) return;
    setDestination({ lat: facility.lat, lon: facility.lon }, facility.name);
    state.map.panTo([facility.lat, facility.lon]);
  }

  async function calculateRoute() {
    if (!state.origin || !state.destination) return showRouteError('Choose both origin and destination.');
    clearRouteError();
    const btn = $('routeBtn'); btn.disabled = true; btn.textContent = 'Finding safest real-road route…';
    const threshold = $('blockThreshold').value;
    try {
      const result = await api('/api/route/safest', {
        method: 'POST',
        body: JSON.stringify({
          start: { lat: state.origin.lat, lon: state.origin.lon },
          end: { lat: state.destination.lat, lon: state.destination.lon },
          risk_points: state.riskPoints,
          blocked_way_ids: [],
          routing: {
            risk_penalty_multiplier: Number($('riskPenalty').value),
            extreme_risk_block_threshold: threshold === '' ? null : Number(threshold),
          },
        }),
      });
      drawRoute(result);
      renderRouteSummary(result);
    } catch (error) { showRouteError(error.message); }
    finally { btn.disabled = false; btn.textContent = 'Find safest route'; }
  }

  function drawRoute(result) {
    if (state.routeLayer) state.map.removeLayer(state.routeLayer);
    const latlngs = (result.geometry || []).map((point) => normalizePoint(point)).map((point) => [point.lat, point.lon]);
    if (latlngs.length < 2) throw new Error('Routing service returned an invalid route geometry.');
    state.routeLayer = L.layerGroup().addTo(state.map);
    const mainLine = L.polyline(latlngs, { color: '#39d7ff', weight: 7, opacity: .92, lineJoin: 'round' }).addTo(state.routeLayer);
    L.polyline(latlngs, { color: '#ffffff', weight: 2, opacity: .38, dashArray: '4 8', interactive: false }).addTo(state.routeLayer);
    state.map.fitBounds(mainLine.getBounds().pad(.18));
  }

  function renderRouteSummary(result) {
    $('routeSummary').classList.remove('hidden');
    const isFallback = result.routing_mode === 'risk-aware-osrm-alternatives-fallback';
    $('routeEngine').textContent = isFallback ? 'Risk-aware real-road alternatives' : 'Risk-aware Dijkstra';
    $('routingProvider').textContent = result.provider ? `${isFallback ? 'Fallback' : 'Primary'} • ${result.provider}` : (isFallback ? 'OSRM fallback' : 'OpenStreetMap graph');
    $('routeDistance').textContent = fmtKm(result.distance_m);
    $('routeEta').textContent = `${Math.max(1, Math.round(result.eta_minutes))} min`;
    $('routeAvgRisk').textContent = `${(result.average_risk * 100).toFixed(1)}%`;
    $('routeMaxRisk').textContent = `${(result.max_risk * 100).toFixed(1)}%`;
    $('routeExtra').textContent = result.extra_distance_m > 25 ? `+${fmtKm(result.extra_distance_m)}` : '≈ shortest';
    $('routeAvoided').textContent = String(result.avoided_high_risk_edges);
    const badge = $('routeRiskBadge');
    const routeTier = result.max_risk >= .8 ? 'HIGH RISK' : result.max_risk >= .4 ? 'WATCH' : 'LOWER RISK';
    badge.textContent = routeTier;
    badge.style.color = riskColor(result.max_risk);
    if (isFallback) {
      $('routeExplanation').textContent = result.extra_distance_m > 25
        ? `The primary live OSM graph was unavailable, so PRAHARI scored real OSRM road alternatives with the same ML risk surface and selected a route ${fmtKm(result.extra_distance_m)} longer than the shortest candidate to reduce risk.`
        : `The primary live OSM graph was unavailable, so PRAHARI scored real OSRM road alternatives with the ML risk surface. The safest candidate is approximately the shortest candidate.`;
    } else {
      $('routeExplanation').textContent = result.extra_distance_m > 25
        ? `Dijkstra accepted ${fmtKm(result.extra_distance_m)} of additional travel to reduce the risk-weighted route cost. Shortest-road distance is ${fmtKm(result.shortest_distance_m)}.`
        : `The risk-aware path is effectively the same length as the shortest available road path. ${result.risk_point_count} spatial ML risk point(s) influenced edge costs.`;
    }
  }

  function showRouteError(message) {
    $('routeError').textContent = message;
    $('routeError').classList.remove('hidden');
  }
  function clearRouteError() { $('routeError').classList.add('hidden'); $('routeError').textContent = ''; }

  function bindEvents() {
    $('useLocationBtn').addEventListener('click', useMyLocation);
    $('setOriginBtn').addEventListener('click', () => setMapMode('origin'));
    $('setDestinationBtn').addEventListener('click', () => setMapMode('destination'));
    $('cancelMapMode').addEventListener('click', () => setMapMode(null));
    $('stationSelect').addEventListener('change', stationSelected);
    $('scoreRiskBtn').addEventListener('click', scoreRisk);
    $('clearRiskBtn').addEventListener('click', clearRiskPoints);
    $('loadFacilitiesBtn').addEventListener('click', loadFacilities);
    $('facilitySelect').addEventListener('change', facilitySelected);
    $('routeBtn').addEventListener('click', calculateRoute);
    $('riskPenalty').addEventListener('input', () => { $('riskPenaltyValue').textContent = `${$('riskPenalty').value}×`; });
  }

  async function boot() {
    initMap();
    bindEvents();
    await checkHealth();
    try { await loadStations(); } catch (error) { showRouteError(`Could not load stations: ${error.message}`); }
  }

  boot();
})();
