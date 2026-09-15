# PRAHARI Risk-Aware Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a complete FastAPI + ML + live-OSM risk-aware Dijkstra evacuation system integrated with the existing PRAHARI project.

**Architecture:** Train a Python Random Forest artifact from the supplied seven-feature PRAHARI dataset. Serve a FastAPI application that queries live OSM/Overpass, converts roads into a graph, maps geolocated ML risk onto edges, and runs project-owned Dijkstra. Serve a Leaflet frontend from the same backend.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, scikit-learn, joblib, httpx, Pydantic v2, vanilla JavaScript, Leaflet, pytest.

**Spec:** `docs/superpowers/specs/2026-09-16-risk-aware-routing-design.md`

## Global Constraints
- Keep original source/data files intact.
- Use the existing seven-feature order and scaling metadata.
- Use live OpenStreetMap/Overpass in production routing.
- Do not fabricate a route when live road data fails.
- Candidate OSM facilities must not be labeled official shelters unless source data says so.
- Dijkstra must be implemented in the project, not delegated to an external routing API.

---

### Task 1: ML training and inference service
**Files:** `tests/test_ml_service.py`, `ml/train_model.py`, `backend/app/ml_service.py`, `backend/artifacts/*`
**Produces:** `FloodRiskModel.predict(raw)->RiskPrediction`, trained joblib model and metrics metadata.
- [ ] Write failing ML contract tests.
- [ ] Run tests and confirm failure because service is absent.
- [ ] Implement training/inference and train artifact from supplied data.
- [ ] Run ML tests and full test suite.

### Task 2: Road graph parser and geometry utilities
**Files:** `tests/fixtures/osm_small.json`, `tests/test_osm_graph.py`, `backend/app/osm.py`, `backend/app/geo.py`, `backend/app/models.py`
**Produces:** `OSMRoadProvider.fetch_graph`, `RoadGraph`, snapping and haversine utilities.
- [ ] Write failing deterministic OSM parsing/snapping tests.
- [ ] Run tests and confirm expected failures.
- [ ] Implement parser, graph model, live Overpass fetch, and TTL cache.
- [ ] Run graph tests.

### Task 3: Risk projection and Dijkstra routing
**Files:** `tests/test_routing.py`, `backend/app/routing.py`
**Produces:** `find_safest_route(graph, start, end, risk_points, blocked_edges)`.
- [ ] Write failing tests proving longer safer path wins and blocked edges are excluded.
- [ ] Run tests and confirm failures.
- [ ] Implement explicit Dijkstra, risk interpolation, edge weighting, and route metrics.
- [ ] Run routing tests.

### Task 4: FastAPI service and OSM facility discovery
**Files:** `tests/test_api.py`, `backend/app/main.py`, `backend/app/facilities.py`, `backend/app/config.py`
**Produces:** `/api/health`, `/api/risk/predict`, `/api/route/safest`, `/api/facilities/nearby`, `/api/stations`.
- [ ] Write failing endpoint tests with deterministic provider injection.
- [ ] Run tests and confirm failures.
- [ ] Implement API, validation, errors, facility Overpass lookup, CORS/static serving.
- [ ] Run API tests.

### Task 5: Integrated Leaflet frontend
**Files:** `frontend/index.html`, `frontend/app.js`, `frontend/styles.css`
**Produces:** interactive origin/destination selection, ML scoring, risk points, facility markers, route rendering and metrics.
- [ ] Add frontend smoke assertions for required IDs/assets.
- [ ] Run smoke test and confirm failure.
- [ ] Implement integrated UI and API calls.
- [ ] Re-run smoke and full tests.

### Task 6: Runtime/package/deployment documentation
**Files:** `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `run.sh`, `run.bat`, `.env.example`, `README_FULLSTACK.md`, update `README.md`.
**Produces:** one-command local run and container deployment path.
- [ ] Add packaging smoke checks.
- [ ] Implement runtime files and documentation.
- [ ] Run import tests, pytest, compile checks, model training reproducibility check, and local API smoke test.
- [ ] Create final ZIP after verification.
