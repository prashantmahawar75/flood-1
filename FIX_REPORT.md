# PRAHARI v2.1 Reliability Fix Report

## Production failures fixed

### 1. Leaflet `NaN` crash
Root cause: Leaflet map clicks expose longitude as `latlng.lng`, while the old code only read `point.lon`.

Fix: every map coordinate now passes through `normalizePoint()`, which accepts either `lon` or Leaflet `lng` and rejects non-finite/out-of-range coordinates before a marker is created.

### 2. `/api/facilities/nearby` 503 from a single Overpass dependency
Root cause: the deployed backend depended on one public Overpass endpoint and used one comparatively broad facility query.

Fix:
- Overpass failover pool with cooldown after failures.
- Staged facility search: shelter/hospital/community/clinic first, schools/colleges only when needed.
- Photon/OpenStreetMap fallback if Overpass providers cannot return useful facilities.
- Provider name returned with facility results and shown in the UI.

### 3. `Find safest route` depended on the same live road-graph provider
Fix:
- Primary mode remains project-owned risk-aware Dijkstra on live OSM roads.
- If Overpass graph extraction is unavailable, the backend asks public OSRM services for real-road alternatives, applies the same PRAHARI ML risk surface to every alternative, and returns the lowest risk-weighted candidate.
- The UI clearly labels fallback mode and never claims project-owned Dijkstra ran when it did not.

## External service order

### Road graph / primary Dijkstra
1. `https://overpass.private.coffee/api/interpreter`
2. `https://maps.mail.ru/osm/tools/overpass/api/interpreter`
3. `https://overpass-api.de/api/interpreter`

### Facility fallback
- `https://photon.komoot.io/reverse`

### Real-road routing fallback
1. `https://router.project-osrm.org/route/v1/driving`
2. `https://routing.openstreetmap.de/routed-car/route/v1/driving`

All public third-party APIs are best-effort services, so no software can guarantee 100% uptime. This release removes single-provider failure points and only returns 503 when every suitable provider for the requested operation is unavailable.

## Verification

- Full test suite: 32 passed
- Python compile: passed
- Frontend JavaScript syntax: passed
- Shell syntax: passed
- `/`: 200
- `/api/health`: 200
- `/api/stations`: 200
- deterministic failover tests: passed
- longer-but-lower-risk OSRM alternative test: passed
- risk-aware Dijkstra regression tests: passed
