from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.ml_service import FloodRiskModel
from backend.app.models import GeoPoint, RoadEdge, RoadGraph


ROOT = Path(__file__).resolve().parents[1]


def _add_bidir(adjacency, a, b, distance, way_id):
    adjacency[a].append(RoadEdge(to_node=b, distance_m=distance, way_id=way_id, highway="residential"))
    adjacency[b].append(RoadEdge(to_node=a, distance_m=distance, way_id=way_id, highway="residential"))


def route_graph():
    nodes = {
        1: GeoPoint(11.0000, 76.0000),
        2: GeoPoint(11.0000, 76.0010),
        3: GeoPoint(11.0000, 76.0020),
        4: GeoPoint(11.0100, 76.0010),
    }
    adjacency = {node_id: [] for node_id in nodes}
    _add_bidir(adjacency, 1, 2, 100.0, 10)
    _add_bidir(adjacency, 2, 3, 100.0, 10)
    _add_bidir(adjacency, 1, 4, 180.0, 20)
    _add_bidir(adjacency, 4, 3, 180.0, 20)
    return RoadGraph(nodes=nodes, adjacency=adjacency)


class FakeRoadProvider:
    async def fetch_graph(self, start, end, margin_km=2.0):
        return route_graph()


class FakeFacilityProvider:
    async def find_nearby(self, center, radius_m=10000):
        return [
            {
                "osm_id": "node/900",
                "name": "Test Community Centre",
                "category": "community_centre",
                "lat": 11.002,
                "lon": 76.003,
                "distance_m": 400.0,
                "official_shelter": False,
                "source": "OpenStreetMap",
            }
        ]


def build_client():
    model = FloodRiskModel(
        model_path=ROOT / "backend" / "artifacts" / "flood_rf.joblib",
        scaling_path=ROOT / "data" / "train model yaha se" / "scaling_parameters.json",
    )
    app = create_app(road_provider=FakeRoadProvider(), facility_provider=FakeFacilityProvider(), risk_model=model)
    return TestClient(app)


def observation():
    return {
        "rainfall_mm": 100,
        "rainfall_3d_cum_mm": 220,
        "river_discharge": 350,
        "river_discharge_roc": 75,
        "slope": 15,
        "drainage_density": 2.9,
        "discharge_sensor_outage": 0,
    }


def test_health_and_stations_are_available():
    client = build_client()
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    stations = client.get("/api/stations")
    assert stations.status_code == 200
    muthankera = next(item for item in stations.json() if item["station_name"] == "MUTHANKERA")
    assert muthankera["slope"] == 14.2
    assert muthankera["drainage_density"] == 2.45


def test_risk_prediction_endpoint_returns_ml_score():
    client = build_client()
    response = client.post("/api/risk/predict", json={"lat": 11.0, "lon": 76.0, "observation": observation()})
    assert response.status_code == 200
    data = response.json()
    assert 0 <= data["probability"] <= 1
    assert data["score"] == data["probability"] * 100
    assert data["tier"] in {"SAFE", "WATCH", "HIGH_RISK"}


def test_safest_route_endpoint_uses_risk_aware_dijkstra():
    client = build_client()
    response = client.post(
        "/api/route/safest",
        json={
            "start": {"lat": 11.0, "lon": 76.0},
            "end": {"lat": 11.0, "lon": 76.002},
            "risk_points": [
                {"lat": 11.0, "lon": 76.001, "probability": 0.85, "slope": 15, "label": "sensor-a"}
            ],
            "routing": {"risk_radius_m": 450, "risk_penalty_multiplier": 12, "extreme_risk_block_threshold": None},
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["node_ids"] == [1, 4, 3]
    assert data["distance_m"] == 360.0
    assert data["shortest_distance_m"] == 200.0
    assert len(data["geometry"]) == 3


def test_nearby_facilities_are_explicitly_candidate_not_official():
    client = build_client()
    response = client.get("/api/facilities/nearby?lat=11&lon=76&radius_m=5000")
    assert response.status_code == 200
    item = response.json()[0]
    assert item["official_shelter"] is False
    assert item["source"] == "OpenStreetMap"


def test_frontend_is_served_from_same_fastapi_app():
    client = build_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "PRAHARI" in response.text
