from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import Settings
from .facilities import FacilityLookupError, OSMFacilityProvider
from .geo import haversine_m
from .ml_service import FloodRiskModel
from .models import GeoPoint, RiskPoint
from .osm import OSMRoadProvider
from .overpass_client import OverpassUnavailableError, ResilientOverpassClient
from .osrm_fallback import OSRMAlternativeRouter, OSRMUnavailableError
from .photon import PhotonFacilityProvider
from .routing import RouteNotFoundError, RoutingConfig, find_safest_route
from .schemas import RiskRequest, RouteRequest


def _load_stations(path: Path, terrain_path: Path) -> list[dict[str, Any]]:
    terrain: dict[str, dict[str, float]] = {}
    if terrain_path.exists():
        with terrain_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for item in csv.DictReader(handle):
                try:
                    terrain[item["station"].strip()] = {
                        "slope": float(item["slope"]),
                        "drainage_density": float(item["drainage_density"]),
                        "elevation": float(item["elevation"]),
                    }
                except (KeyError, ValueError):
                    continue
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                station_name = row["station_name"].strip()
                rows.append({
                    "station_name": station_name,
                    "river": row["river"].strip(),
                    "district": row["district"].strip(),
                    "lat": float(row["latitude"]),
                    "lon": float(row["longitude"]),
                    "is_hilly_catchment": str(row.get("is_hilly_catchment", "")).lower() == "true",
                    **terrain.get(station_name, {}),
                })
            except (KeyError, ValueError):
                continue
    return rows


def _routing_config(payload) -> RoutingConfig:
    if payload is None:
        return RoutingConfig()
    return RoutingConfig(**payload.model_dump())


def create_app(
    road_provider=None,
    facility_provider=None,
    risk_model: FloodRiskModel | None = None,
    settings: Settings | None = None,
    fallback_router=None,
) -> FastAPI:
    settings = settings or Settings()
    risk_model = risk_model or FloodRiskModel(settings.model_path, settings.scaling_path)
    shared_overpass = ResilientOverpassClient(
        endpoints=settings.overpass_endpoints,
        timeout_seconds=settings.overpass_timeout_seconds,
        cooldown_seconds=settings.provider_cooldown_seconds,
    )
    road_provider = road_provider or OSMRoadProvider(
        overpass_client=shared_overpass,
        cache_ttl_seconds=settings.road_cache_ttl_seconds,
    )
    facility_provider = facility_provider or OSMFacilityProvider(
        overpass_client=shared_overpass,
        photon_provider=PhotonFacilityProvider(
            endpoint=settings.photon_url, timeout_seconds=min(settings.external_api_timeout_seconds, 8.0)
        ),
        cache_ttl_seconds=settings.road_cache_ttl_seconds,
    )
    fallback_router = fallback_router or OSRMAlternativeRouter(
        endpoints=settings.osrm_endpoints, timeout_seconds=settings.external_api_timeout_seconds
    )
    stations = _load_stations(settings.station_inventory_path, settings.terrain_path)

    app = FastAPI(
        title="PRAHARI Risk-Aware Evacuation API",
        version="2.1.0",
        description="Flash-flood ML risk scoring and real OpenStreetMap risk-aware Dijkstra routing.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.road_provider = road_provider
    app.state.facility_provider = facility_provider
    app.state.risk_model = risk_model
    app.state.settings = settings

    @app.get("/api/health")
    async def health():
        metrics_path = settings.project_root / "backend" / "artifacts" / "model_metrics.json"
        metrics = json.loads(metrics_path.read_text(encoding="utf-8")) if metrics_path.exists() else None
        return {
            "status": "ok",
            "service": "prahari-routing",
            "version": "2.1.0",
            "model_metrics": metrics,
            "external_services": {
                "overpass_failover_count": len(settings.overpass_endpoints),
                "photon_fallback": True,
                "osrm_fallback_count": len(settings.osrm_endpoints),
            },
        }

    @app.get("/api/stations")
    async def get_stations():
        return stations

    @app.post("/api/risk/predict")
    async def predict_risk(request: RiskRequest):
        try:
            prediction = risk_model.predict(request.observation.model_dump())
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "lat": request.lat,
            "lon": request.lon,
            "label": request.label,
            "probability": prediction.probability,
            "score": prediction.score,
            "tier": prediction.tier,
            "feature_order": list(prediction.feature_order),
            "disclaimer": "Decision-support estimate; not an official evacuation order.",
        }

    @app.get("/api/facilities/nearby")
    async def nearby_facilities(
        lat: float = Query(ge=-90, le=90),
        lon: float = Query(ge=-180, le=180),
        radius_m: int = Query(default=10000, ge=500, le=20000),
    ):
        try:
            return await facility_provider.find_nearby(GeoPoint(lat, lon), radius_m=radius_m)
        except FacilityLookupError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Nearby facility services are temporarily unavailable. You can still pick a destination on the map. Details: {exc}",
            ) from exc

    @app.post("/api/route/safest")
    async def safest_route(request: RouteRequest):
        start = GeoPoint(request.start.lat, request.start.lon)
        end = GeoPoint(request.end.lat, request.end.lon)
        straight_line_km = haversine_m(start, end) / 1000.0
        if straight_line_km > settings.max_route_distance_km:
            raise HTTPException(
                status_code=422,
                detail=f"Route is {straight_line_km:.1f} km straight-line; maximum supported live OSM request is {settings.max_route_distance_km:.0f} km.",
            )
        risk_points = [
            RiskPoint(
                point=GeoPoint(item.lat, item.lon),
                probability=item.probability,
                slope=item.slope,
                label=item.label,
            )
            for item in request.risk_points
        ]
        config = _routing_config(request.routing)
        primary_error: Exception | None = None
        try:
            margin_km = min(4.0, max(1.2, straight_line_km * 0.15 + 0.8))
            graph = await road_provider.fetch_graph(start, end, margin_km=margin_km)
            result = find_safest_route(
                graph,
                start,
                end,
                risk_points=risk_points,
                blocked_way_ids=set(request.blocked_way_ids),
                config=config,
            )
            return {
                "node_ids": result.node_ids,
                "way_ids": result.way_ids,
                "geometry": [{"lat": point.lat, "lon": point.lon} for point in result.geometry],
                "distance_m": result.distance_m,
                "distance_km": result.distance_m / 1000.0,
                "weighted_cost": result.weighted_cost,
                "average_risk": result.average_risk,
                "max_risk": result.max_risk,
                "eta_minutes": result.eta_minutes,
                "shortest_distance_m": result.shortest_distance_m,
                "shortest_distance_km": result.shortest_distance_m / 1000.0,
                "extra_distance_m": max(0.0, result.distance_m - result.shortest_distance_m),
                "avoided_high_risk_edges": result.avoided_high_risk_edges,
                "start_snap_distance_m": result.start_snap_distance_m,
                "end_snap_distance_m": result.end_snap_distance_m,
                "risk_point_count": len(risk_points),
                "routing_mode": "risk-aware-dijkstra-live-osm",
                "provider": getattr(graph, "provider", None) or "OpenStreetMap Overpass",
            }
        except (OverpassUnavailableError, RouteNotFoundError, RuntimeError) as exc:
            primary_error = exc

        try:
            return await fallback_router.find_route(start, end, risk_points, config)
        except OSRMUnavailableError as fallback_error:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Live road services are temporarily unavailable. "
                    f"Primary Dijkstra graph: {primary_error}; routing fallback: {fallback_error}"
                ),
            ) from fallback_error

    if settings.frontend_dir.exists() and (settings.frontend_dir / "index.html").exists():
        app.mount("/", StaticFiles(directory=settings.frontend_dir, html=True), name="frontend")

    return app


app = create_app()
