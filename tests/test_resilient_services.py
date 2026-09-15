import asyncio

import httpx
import pytest

from backend.app.models import GeoPoint, RiskPoint


def test_overpass_client_fails_over_to_second_provider(monkeypatch):
    from backend.app.overpass_client import ResilientOverpassClient

    calls = []

    class Response:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {}
            self.text = "temporary failure"
        def raise_for_status(self):
            if self.status_code >= 400:
                request = httpx.Request("POST", "https://example.invalid")
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError("failed", request=request, response=response)
        def json(self):
            return self._payload

    class Client:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            calls.append(url)
            if url == "https://bad.example/api/interpreter":
                return Response(503)
            return Response(200, {"elements": [{"type": "node", "id": 1, "lat": 1.0, "lon": 2.0}]})

    monkeypatch.setattr("backend.app.overpass_client.httpx.AsyncClient", Client)
    client = ResilientOverpassClient(
        endpoints=["https://bad.example/api/interpreter", "https://good.example/api/interpreter"],
        timeout_seconds=1,
        cooldown_seconds=60,
    )
    result = asyncio.run(client.query("[out:json];node(1);out;", purpose="test"))
    assert result.endpoint == "https://good.example/api/interpreter"
    assert len(result.payload["elements"]) == 1
    assert calls == ["https://bad.example/api/interpreter", "https://good.example/api/interpreter"]


def test_facility_provider_falls_back_to_photon_and_ranks_emergency_first():
    from backend.app.facilities import OSMFacilityProvider

    class DeadOverpass:
        async def query(self, query, purpose="query"):
            from backend.app.overpass_client import OverpassUnavailableError
            raise OverpassUnavailableError("all providers failed")

    class Photon:
        async def find_nearby(self, center, radius_m):
            return [
                {
                    "osm_id": "node/2", "name": "Community Hall", "category": "community_centre",
                    "lat": center.lat + 0.001, "lon": center.lon, "distance_m": 100.0,
                    "official_shelter": False, "source": "OpenStreetMap/Photon", "provider": "photon.komoot.io",
                },
                {
                    "osm_id": "node/1", "name": "Emergency Shelter", "category": "shelter",
                    "lat": center.lat + 0.002, "lon": center.lon, "distance_m": 200.0,
                    "official_shelter": False, "source": "OpenStreetMap/Photon", "provider": "photon.komoot.io",
                },
            ]

    provider = OSMFacilityProvider(overpass_client=DeadOverpass(), photon_provider=Photon())
    items = asyncio.run(provider.find_nearby(GeoPoint(28.6, 77.2), radius_m=5000))
    assert [item["name"] for item in items][:2] == ["Emergency Shelter", "Community Hall"]
    assert items[0]["source"] == "OpenStreetMap/Photon"


def test_osrm_fallback_selects_longer_lower_risk_alternative(monkeypatch):
    from backend.app.osrm_fallback import OSRMAlternativeRouter
    from backend.app.routing import RoutingConfig

    class Response:
        status_code = 200
        def raise_for_status(self):
            return None
        def json(self):
            return {
                "code": "Ok",
                "routes": [
                    {
                        "distance": 200.0, "duration": 30.0,
                        "geometry": {"coordinates": [[76.0, 11.0], [76.001, 11.0], [76.002, 11.0]]},
                    },
                    {
                        "distance": 360.0, "duration": 55.0,
                        "geometry": {"coordinates": [[76.0, 11.0], [76.001, 11.01], [76.002, 11.0]]},
                    },
                ],
            }

    class Client:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def get(self, url, **kwargs): return Response()

    monkeypatch.setattr("backend.app.osrm_fallback.httpx.AsyncClient", Client)
    router = OSRMAlternativeRouter(endpoints=["https://router.example"])
    result = asyncio.run(router.find_route(
        GeoPoint(11.0, 76.0),
        GeoPoint(11.0, 76.002),
        [RiskPoint(GeoPoint(11.0, 76.001), 0.95, 15.0, "flood")],
        RoutingConfig(risk_radius_m=400, risk_penalty_multiplier=20, extreme_risk_block_threshold=None),
    ))
    assert result["distance_m"] == 360.0
    assert result["shortest_distance_m"] == 200.0
    assert result["routing_mode"] == "risk-aware-osrm-alternatives-fallback"
    assert result["max_risk"] < 0.95


def test_route_api_uses_osrm_fallback_when_overpass_roads_unavailable():
    from pathlib import Path
    from fastapi.testclient import TestClient
    from backend.app.main import create_app
    from backend.app.ml_service import FloodRiskModel

    root = Path(__file__).resolve().parents[1]

    class BrokenRoadProvider:
        async def fetch_graph(self, *args, **kwargs):
            from backend.app.overpass_client import OverpassUnavailableError
            raise OverpassUnavailableError("no overpass")

    class EmptyFacilityProvider:
        async def find_nearby(self, center, radius_m=10000): return []

    class Fallback:
        async def find_route(self, start, end, risk_points, config):
            return {
                "node_ids": [], "way_ids": [],
                "geometry": [{"lat": start.lat, "lon": start.lon}, {"lat": end.lat, "lon": end.lon}],
                "distance_m": 1000.0, "distance_km": 1.0, "weighted_cost": 1100.0,
                "average_risk": 0.1, "max_risk": 0.2, "eta_minutes": 3.0,
                "shortest_distance_m": 950.0, "shortest_distance_km": 0.95,
                "extra_distance_m": 50.0, "avoided_high_risk_edges": 1,
                "start_snap_distance_m": 0.0, "end_snap_distance_m": 0.0,
                "risk_point_count": len(risk_points), "routing_mode": "risk-aware-osrm-alternatives-fallback",
                "provider": "fake-osrm",
            }

    model = FloodRiskModel(root / "backend/artifacts/flood_rf.joblib", root / "data/train model yaha se/scaling_parameters.json")
    app = create_app(road_provider=BrokenRoadProvider(), facility_provider=EmptyFacilityProvider(), risk_model=model, fallback_router=Fallback())
    client = TestClient(app)
    response = client.post("/api/route/safest", json={
        "start": {"lat": 11.0, "lon": 76.0}, "end": {"lat": 11.001, "lon": 76.002}, "risk_points": []
    })
    assert response.status_code == 200, response.text
    assert response.json()["routing_mode"] == "risk-aware-osrm-alternatives-fallback"
