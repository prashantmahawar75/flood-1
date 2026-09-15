from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from .geo import haversine_m
from .models import GeoPoint, RiskPoint, RoadEdge
from .routing import RoutingConfig, interpolate_edge_risk, risk_weighted_edge_cost

DEFAULT_OSRM_ENDPOINTS = (
    "https://router.project-osrm.org/route/v1/driving",
    "https://routing.openstreetmap.de/routed-car/route/v1/driving",
)


class OSRMUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class _ScoredRoute:
    route: dict[str, Any]
    geometry: list[GeoPoint]
    weighted_cost: float
    average_risk: float
    max_risk: float
    high_risk_segments: int


class OSRMAlternativeRouter:
    """Graceful routing fallback when live Overpass graph extraction fails.

    The primary system still runs project-owned risk-aware Dijkstra on an OSM
    graph. This fallback asks OSRM for real-road alternatives, then applies the
    same PRAHARI spatial risk cost to those alternatives and selects the lowest
    risk-weighted candidate. This keeps the button operational without falsely
    labelling the fallback as project-owned Dijkstra.
    """

    def __init__(self, endpoints: Iterable[str] | None = None, timeout_seconds: float = 12.0) -> None:
        normalized = []
        for endpoint in endpoints or DEFAULT_OSRM_ENDPOINTS:
            endpoint = str(endpoint).strip().rstrip("/")
            if endpoint and endpoint not in normalized:
                normalized.append(endpoint)
        self.endpoints = tuple(normalized)
        self.timeout_seconds = max(2.0, float(timeout_seconds))

    @staticmethod
    def _geometry(route: dict[str, Any]) -> list[GeoPoint]:
        coordinates = route.get("geometry", {}).get("coordinates", [])
        geometry: list[GeoPoint] = []
        for coord in coordinates:
            if not isinstance(coord, (list, tuple)) or len(coord) < 2:
                continue
            geometry.append(GeoPoint(lat=float(coord[1]), lon=float(coord[0])))
        return geometry

    @staticmethod
    def _score(route: dict[str, Any], risk_points: list[RiskPoint], config: RoutingConfig) -> _ScoredRoute | None:
        geometry = OSRMAlternativeRouter._geometry(route)
        if len(geometry) < 2:
            return None
        weighted_cost = 0.0
        weighted_risk = 0.0
        geometry_distance = 0.0
        max_risk = 0.0
        high_risk_segments = 0
        for index, (a, b) in enumerate(zip(geometry, geometry[1:]), start=1):
            distance = haversine_m(a, b)
            if distance <= 0:
                continue
            edge = RoadEdge(to_node=index, distance_m=distance, way_id=-index, highway="residential")
            risk = interpolate_edge_risk(a, b, risk_points, config)
            weighted_cost += risk_weighted_edge_cost(edge, risk, config)
            weighted_risk += risk.flood_risk * distance
            geometry_distance += distance
            max_risk = max(max_risk, risk.flood_risk)
            if risk.flood_risk >= config.high_risk_threshold:
                high_risk_segments += 1
        if geometry_distance <= 0:
            return None
        return _ScoredRoute(
            route=route,
            geometry=geometry,
            weighted_cost=weighted_cost,
            average_risk=weighted_risk / geometry_distance,
            max_risk=max_risk,
            high_risk_segments=high_risk_segments,
        )

    async def find_route(
        self,
        start: GeoPoint,
        end: GeoPoint,
        risk_points: list[RiskPoint],
        config: RoutingConfig,
    ) -> dict[str, Any]:
        failures: list[str] = []
        headers = {"User-Agent": "PRAHARI-SIH26192/2.1 (routing fallback)"}
        coords = f"{start.lon:.7f},{start.lat:.7f};{end.lon:.7f},{end.lat:.7f}"
        payload = None
        provider = None
        async with httpx.AsyncClient(timeout=self.timeout_seconds, headers=headers, follow_redirects=True) as client:
            for endpoint in self.endpoints:
                try:
                    response = await client.get(
                        f"{endpoint}/{coords}",
                        params={
                            "alternatives": "3",
                            "steps": "false",
                            "geometries": "geojson",
                            "overview": "full",
                        },
                    )
                    response.raise_for_status()
                    candidate = response.json()
                    if candidate.get("code") != "Ok" or not candidate.get("routes"):
                        raise RuntimeError(candidate.get("message") or candidate.get("code") or "NoRoute")
                    payload = candidate
                    provider = endpoint
                    break
                except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                    failures.append(f"{endpoint}: {type(exc).__name__}: {exc}")
        if payload is None or provider is None:
            raise OSRMUnavailableError("All OSRM fallback providers failed. " + " | ".join(failures))

        scored = [self._score(route, risk_points, config) for route in payload.get("routes", [])]
        scored = [route for route in scored if route is not None]
        if not scored:
            raise OSRMUnavailableError("OSRM returned routes without usable geometry")

        shortest = min(scored, key=lambda item: float(item.route.get("distance", float("inf"))))
        threshold = config.extreme_risk_block_threshold
        allowed = [item for item in scored if threshold is None or item.max_risk < threshold]
        if not allowed:
            raise OSRMUnavailableError(
                "Every available real-road alternative crosses the configured extreme-risk threshold; choose another destination or relax the hard-block threshold."
            )
        chosen = min(allowed, key=lambda item: (item.weighted_cost, item.max_risk, float(item.route.get("distance", 0))))
        distance_m = float(chosen.route.get("distance", 0.0))
        shortest_distance_m = float(shortest.route.get("distance", distance_m))
        duration_seconds = float(chosen.route.get("duration", 0.0))
        return {
            "node_ids": [],
            "way_ids": [],
            "geometry": [{"lat": point.lat, "lon": point.lon} for point in chosen.geometry],
            "distance_m": distance_m,
            "distance_km": distance_m / 1000.0,
            "weighted_cost": chosen.weighted_cost,
            "average_risk": chosen.average_risk,
            "max_risk": chosen.max_risk,
            "eta_minutes": duration_seconds / 60.0,
            "shortest_distance_m": shortest_distance_m,
            "shortest_distance_km": shortest_distance_m / 1000.0,
            "extra_distance_m": max(0.0, distance_m - shortest_distance_m),
            "avoided_high_risk_edges": max(0, shortest.high_risk_segments - chosen.high_risk_segments),
            "start_snap_distance_m": 0.0,
            "end_snap_distance_m": 0.0,
            "risk_point_count": len(risk_points),
            "routing_mode": "risk-aware-osrm-alternatives-fallback",
            "provider": provider,
        }
