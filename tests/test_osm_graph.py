import json
from pathlib import Path

from backend.app.geo import haversine_m, snap_to_graph
from backend.app.models import GeoPoint
from backend.app.osm import parse_overpass_roads


FIXTURE = Path(__file__).parent / "fixtures" / "osm_small.json"


def load_fixture():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_haversine_is_zero_for_same_point():
    p = GeoPoint(lat=11.0, lon=76.0)
    assert haversine_m(p, p) == 0.0


def test_parse_overpass_builds_bidirectional_and_oneway_edges():
    graph = parse_overpass_roads(load_fixture())
    assert set(graph.nodes) == {1, 2, 3, 4, 5}
    assert any(edge.to_node == 2 and edge.way_id == 100 for edge in graph.adjacency[1])
    assert any(edge.to_node == 1 and edge.way_id == 100 for edge in graph.adjacency[2])
    assert any(edge.to_node == 4 and edge.way_id == 200 for edge in graph.adjacency[2])
    assert not any(edge.to_node == 2 and edge.way_id == 200 for edge in graph.adjacency[4])


def test_parser_computes_positive_edge_distances():
    graph = parse_overpass_roads(load_fixture())
    edge = next(edge for edge in graph.adjacency[1] if edge.to_node == 2)
    assert 1000 < edge.distance_m < 1200


def test_snap_to_graph_finds_nearest_osm_node():
    graph = parse_overpass_roads(load_fixture())
    snapped = snap_to_graph(graph, GeoPoint(lat=11.0002, lon=76.0097))
    assert snapped.node_id == 2
    assert snapped.distance_m < 100


def test_overpass_provider_uses_shared_client_and_records_provider():
    import asyncio
    from backend.app.osm import OSMRoadProvider
    from backend.app.overpass_client import OverpassQueryResult

    captured = {}

    class Overpass:
        async def query(self, query, purpose="query"):
            captured["query"] = query
            captured["purpose"] = purpose
            return OverpassQueryResult(load_fixture(), "https://example.invalid/api/interpreter")

    provider = OSMRoadProvider(overpass_client=Overpass())
    graph = asyncio.run(provider.fetch_graph(GeoPoint(11.0, 76.0), GeoPoint(11.0, 76.01)))
    assert graph.edge_count > 0
    assert "highway" in captured["query"]
    assert captured["purpose"] == "road graph"
    assert graph.provider == "https://example.invalid/api/interpreter"


def test_parser_skips_private_or_motor_vehicle_prohibited_ways():
    payload = load_fixture()
    payload["elements"].append({"type":"way","id":300,"nodes":[1,3],"tags":{"highway":"service","access":"private"}})
    payload["elements"].append({"type":"way","id":301,"nodes":[1,3],"tags":{"highway":"residential","motor_vehicle":"no"}})
    graph = parse_overpass_roads(payload)
    assert not any(edge.way_id in {300, 301} for edges in graph.adjacency.values() for edge in edges)
