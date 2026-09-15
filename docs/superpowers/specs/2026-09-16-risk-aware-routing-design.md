# PRAHARI Real-Road Risk-Aware Routing Design

## Goal
Extend the existing PRAHARI/PravahAI flash-flood dashboard into a complete full-stack evacuation-routing system where the trained flood ML model produces spatial risk scores and a backend runs an explicit risk-aware Dijkstra algorithm over live OpenStreetMap road data to find a safer route to a selected destination or nearby candidate refuge.

## Architecture
- **ML layer:** Python Random Forest trained from the supplied PRAHARI train/test feature files using the same seven deployed features and the existing scaling metadata. The backend accepts raw hydrometeorological values and returns probability, 0-100 score, and SAFE/WATCH/HIGH_RISK tier.
- **Road layer:** Backend queries OpenStreetMap through Overpass for drivable roads in a bounded area around the requested route, parses ways/nodes into a directed adjacency graph, snaps start/destination to nearby graph nodes, and caches fetched road graphs.
- **Risk projection:** ML/station risk points are projected onto each road edge using distance-decayed interpolation. Edge cost combines road length with flood-risk and slope/landslide penalties. Very-high-risk or explicitly blocked edges are excluded.
- **Routing:** A project-owned Dijkstra implementation minimizes the risk-weighted cost, not raw distance. Response includes route geometry, distance, estimated duration, average/max route risk, avoided high-risk edge count, and comparison with the shortest-distance path.
- **Frontend:** Leaflet UI served by FastAPI. User can use browser geolocation or map click for origin, click/select destination, enter sensor observations, obtain ML risk, load candidate OSM refuge facilities, and request/display the safest route. The UI explains why the safer route differs from the shortest route.

## Data Flow
1. User enters/loads hydrometeorological observations for a station/location.
2. `/api/risk/predict` scales inputs and scores the trained RF model.
3. Frontend stores one or more geolocated risk points.
4. User selects origin and destination (or chooses a nearby OSM facility).
5. `/api/route/safest` fetches live OSM roads, projects risk points onto edges, removes blocked/extreme-risk edges, and runs Dijkstra.
6. Frontend renders route, risk-colored risk points, metrics, and warnings.

## Safety/Truthfulness Constraints
- Candidate facilities discovered from OSM are labeled **candidate refuge facilities**, not guaranteed official government shelters.
- If OSM/Overpass is unavailable or no road path exists, the API returns a clear error; it must not fabricate a route.
- ML score is decision support and not presented as an official evacuation order.
- Explicit blocked road segments are treated as impassable.

## Testing
- Unit tests for scaling/ML output contract.
- Unit tests proving risk-aware Dijkstra can prefer a longer safer path.
- Unit tests for blocked/high-risk edge exclusion and snapping.
- Parser tests using a deterministic OSM fixture (tests do not depend on internet).
- FastAPI endpoint tests with the OSM provider replaced by deterministic fixture data.
- Frontend asset smoke checks and Python syntax/import checks.
