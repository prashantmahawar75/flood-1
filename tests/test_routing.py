from backend.app.models import GeoPoint, RiskPoint, RoadEdge, RoadGraph
from backend.app.routing import RoutingConfig, find_safest_route


def add_bidir(adjacency, a, b, distance, way_id):
    adjacency[a].append(RoadEdge(to_node=b, distance_m=distance, way_id=way_id, highway="residential"))
    adjacency[b].append(RoadEdge(to_node=a, distance_m=distance, way_id=way_id, highway="residential"))


def make_graph():
    nodes = {
        1: GeoPoint(0.0, 0.0),
        2: GeoPoint(0.0, 0.001),
        3: GeoPoint(0.0, 0.002),
        4: GeoPoint(0.01, 0.001),
    }
    adjacency = {node_id: [] for node_id in nodes}
    add_bidir(adjacency, 1, 2, 100.0, 10)
    add_bidir(adjacency, 2, 3, 100.0, 10)
    add_bidir(adjacency, 1, 4, 180.0, 20)
    add_bidir(adjacency, 4, 3, 180.0, 20)
    return RoadGraph(nodes=nodes, adjacency=adjacency)


def test_risk_aware_dijkstra_prefers_longer_safer_path():
    graph = make_graph()
    risk_points = [RiskPoint(point=GeoPoint(0.0, 0.001), probability=0.85, slope=15.0)]
    config = RoutingConfig(risk_radius_m=450.0, risk_penalty_multiplier=12.0, extreme_risk_block_threshold=None)
    route = find_safest_route(graph, GeoPoint(0.0, 0.0), GeoPoint(0.0, 0.002), risk_points, config=config)
    assert route.node_ids == [1, 4, 3]
    assert route.distance_m == 360.0
    assert route.shortest_distance_m == 200.0
    assert route.average_risk < 0.3


def test_blocked_way_is_never_used():
    graph = make_graph()
    route = find_safest_route(
        graph,
        GeoPoint(0.0, 0.0),
        GeoPoint(0.0, 0.002),
        risk_points=[],
        blocked_way_ids={10},
    )
    assert route.node_ids == [1, 4, 3]
    assert 10 not in route.way_ids


def test_extreme_risk_edge_can_be_removed_from_graph():
    graph = make_graph()
    risk_points = [RiskPoint(point=GeoPoint(0.0, 0.001), probability=0.99, slope=20.0)]
    config = RoutingConfig(risk_radius_m=450.0, extreme_risk_block_threshold=0.95)
    route = find_safest_route(graph, GeoPoint(0.0, 0.0), GeoPoint(0.0, 0.002), risk_points, config=config)
    assert route.node_ids == [1, 4, 3]
    assert route.max_risk < 0.95


def test_single_risk_point_decays_toward_baseline_with_distance():
    from backend.app.routing import interpolate_edge_risk

    config = RoutingConfig(risk_radius_m=1000.0, baseline_risk=0.05)
    point = RiskPoint(point=GeoPoint(0.0, 0.0), probability=0.90, slope=20.0)
    near = interpolate_edge_risk(GeoPoint(0.0, 0.0), GeoPoint(0.0, 0.0), [point], config)
    far = interpolate_edge_risk(GeoPoint(0.0, 0.007), GeoPoint(0.0, 0.007), [point], config)
    assert near.flood_risk > far.flood_risk
    assert far.flood_risk > config.baseline_risk


def test_no_risk_points_do_not_invent_nonzero_flood_risk():
    route = find_safest_route(
        make_graph(),
        GeoPoint(0.0, 0.0),
        GeoPoint(0.0, 0.002),
        risk_points=[],
    )
    assert route.average_risk == 0.0
    assert route.max_risk == 0.0
