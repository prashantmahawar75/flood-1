# PRAHARI / PravahAI Full-Stack Risk-Aware Evacuation System

This version extends the original SIH 26192 flash-flood dashboard into a complete full-stack prototype:

1. **PRAHARI Random Forest ML** scores flash-flood probability from rainfall, 3-day rainfall, river discharge, discharge rate-of-change, slope, drainage density, and outage state.
2. Every geolocated ML score becomes a **spatial risk point**.
3. The backend downloads the relevant **live OpenStreetMap road network** through a failover pool of Overpass providers.
4. Risk is projected onto nearby road segments.
5. A project-owned **risk-aware Dijkstra algorithm** minimizes a weighted road cost rather than raw distance.
6. If every Overpass road-graph provider is temporarily unavailable, PRAHARI asks public OSRM instances for real-road alternatives and scores those alternatives with the same ML risk surface.
7. Facility discovery uses staged Overpass queries and falls back to Photon/OpenStreetMap when needed.
8. The Leaflet frontend shows the recommended route, ETA, route risk, extra distance versus the shortest path, risky roads avoided, and which live provider served the request.

## Important safety statement

This is a hackathon/research decision-support prototype. It is **not an official evacuation-order system**. OSM hospitals, schools, community centres, and shelter-tagged objects are presented as **candidate refuge facilities** only. A real deployment must integrate verified government shelter/road-closure feeds and local authority procedures.

## Quick start

### Windows

```bat
python -m pip install -r requirements.txt
run.bat
```

### Linux/macOS

```bash
python -m pip install -r requirements.txt
./run.sh
```

Open `http://localhost:8000`.

### Docker

```bash
docker compose up --build
```

Open `http://localhost:8000`.

## Train/retrain the ML model

A trained artifact is already included at `backend/artifacts/flood_rf.joblib`.
To reproduce it from the supplied PRAHARI train/test data:

```bash
python ml/train_model.py
```

The script writes:

- `backend/artifacts/flood_rf.joblib`
- `backend/artifacts/model_metrics.json`

The current packaged model is a 30-tree, max-depth-5 `RandomForestClassifier` using class balancing and random seed 42. The generated metrics file records its held-out performance.

## End-to-end workflow

### 1. Set origin
Use browser geolocation, select a monitored CWC station, or click the map.

### 2. Score risk
Enter hydrometeorological values and click **Run ML risk score**. You can repeat this at several locations; each result becomes a geolocated risk point.

### 3. Set destination
Either click **Find nearby facilities** (live OSM search) or choose any destination directly on the map.

### 4. Find safest route
The backend fetches live drivable OSM roads and runs risk-aware Dijkstra.

For an edge `e`, the route cost is conceptually:

```text
cost(e) = distance(e) × [1 + flood_penalty + slope_penalty]
```

where flood penalty rises non-linearly with the interpolated ML risk. Roads above the configured extreme-risk threshold can be removed from the graph entirely.

The system also computes the pure shortest-distance path for comparison, but it does **not** use that path as the recommendation if a longer route has a lower risk-weighted cost.

## API

### `GET /api/health`
Backend/model status and packaged model metrics.

### `GET /api/stations`
CWC station metadata joined with terrain slope/drainage values.

### `POST /api/risk/predict`
Example:

```json
{
  "lat": 11.8081,
  "lon": 76.0842,
  "label": "MUTHANKERA",
  "observation": {
    "rainfall_mm": 90,
    "rainfall_3d_cum_mm": 210,
    "river_discharge": 330,
    "river_discharge_roc": 65,
    "slope": 14.2,
    "drainage_density": 2.45,
    "discharge_sensor_outage": 0
  }
}
```

### `GET /api/facilities/nearby?lat=...&lon=...&radius_m=10000`
Returns live OSM candidate refuge facilities ranked by refuge priority and distance. Primary source: failover Overpass pool. Fallback: Photon/OpenStreetMap.

### `POST /api/route/safest`
Example:

```json
{
  "start": {"lat": 11.8081, "lon": 76.0842},
  "end": {"lat": 11.835, "lon": 76.102},
  "risk_points": [
    {"lat": 11.8081, "lon": 76.0842, "probability": 0.86, "slope": 14.2, "label": "MUTHANKERA"}
  ],
  "blocked_way_ids": [],
  "routing": {
    "risk_penalty_multiplier": 10,
    "extreme_risk_block_threshold": 0.97
  }
}
```

## Key folders

```text
backend/app/
  main.py          FastAPI application and endpoints
  ml_service.py    scaling + model inference
  overpass_client.py provider failover/cooldown for public Overpass instances
  osm.py           live road query + OSM road graph parser/cache
  facilities.py    resilient OSM candidate-refuge discovery
  photon.py        facility fallback using Photon/OpenStreetMap
  osrm_fallback.py real-road alternative fallback when graph extraction fails
  routing.py       explicit Dijkstra + risk weighting
  geo.py           distance/bbox/snapping helpers
  schemas.py       API validation models
backend/artifacts/
  flood_rf.joblib
  model_metrics.json
frontend/
  index.html
  app.js
  styles.css
ml/
  train_model.py
tests/
  deterministic ML/OSM/routing/API/frontend tests
```

## Internet dependency

Option A intentionally uses **real OSM roads**. The ML model itself runs locally on the backend, but live road/facility discovery requires internet access. The app no longer depends on one public endpoint: it uses multiple Overpass instances, Photon as a facility fallback, and OSRM alternatives as a routing fallback. A `503` is returned only when all suitable providers for that operation are unavailable; the app never fabricates road geometry.

## Production deployment

Netlify alone cannot host this FastAPI backend. Deploy the container to a service such as Render/Railway/Fly.io/Azure/AWS, or host the API separately and change the frontend API base URL. The included Dockerfile is the recommended single-service deployment because FastAPI also serves the frontend.

For a field deployment, add:
- verified government evacuation shelter feeds,
- official road-closure feeds,
- live CWC/IMD/IoT ingestion,
- authentication and audit logs,
- redundant/self-hosted OSM/Overpass infrastructure,
- calibrated road-level hazard layers,
- offline/failover routing.


## Render environment variables (v2.1 resilient services)

Recommended values are already included in `render.yaml` and `.env.example`:

```text
OVERPASS_ENDPOINTS=https://overpass.private.coffee/api/interpreter,https://maps.mail.ru/osm/tools/overpass/api/interpreter,https://overpass-api.de/api/interpreter
OVERPASS_TIMEOUT_SECONDS=12
PROVIDER_COOLDOWN_SECONDS=120
ROAD_CACHE_TTL_SECONDS=900
PHOTON_URL=https://photon.komoot.io/reverse
OSRM_ENDPOINTS=https://router.project-osrm.org/route/v1/driving,https://routing.openstreetmap.de/routed-car/route/v1/driving
EXTERNAL_API_TIMEOUT_SECONDS=12
MAX_ROUTE_DISTANCE_KM=35
```

If an old Render service still has only `OVERPASS_URL`, remove that single-provider variable or add `OVERPASS_ENDPOINTS` above. The new code intentionally keeps `overpass-api.de` as the last fallback rather than the only dependency.
