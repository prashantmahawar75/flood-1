from __future__ import annotations

import heapq
from dataclasses import dataclass
from math import inf
from typing import Callable, Iterable

from .geo import haversine_m, midpoint, snap_to_graph
from .models import GeoPoint, RiskPoint, RoadEdge, RoadGraph


class RouteNotFoundError(RuntimeError):
    pass


@dataclass(frozen=True)
class RoutingConfig:
    risk_radius_m: float = 10_000.0
    baseline_risk: float = 0.0
    risk_penalty_multiplier: float = 10.0
    slope_penalty_multiplier: float = 2.5
    slope_reference_degrees: float = 8.0
    slope_scale_degrees: float = 22.0
    extreme_risk_block_threshold: float | None = 0.97
    high_risk_threshold: float = 0.60
    max_snap_distance_m: float = 2_500.0


@dataclass(frozen=True)
class EdgeRisk:
    flood_risk: float
    slope: float


@dataclass(frozen=True)
class RouteResult:
    node_ids: list[int]
    way_ids: list[int]
    geometry: list[GeoPoint]
    distance_m: float
    weighted_cost: float
    average_risk: float
    max_risk: float
    eta_minutes: float
    shortest_distance_m: float
    shortest_node_ids: list[int]
    avoided_high_risk_edges: int
    start_snap_distance_m: float
    end_snap_distance_m: float


HIGHWAY_DEFAULT_SPEED_KPH = {
    "motorway": 70.0,
    "trunk": 60.0,
    "primary": 45.0,
    "secondary": 40.0,
    "tertiary": 35.0,
    "residential": 25.0,
    "unclassified": 25.0,
    "living_street": 15.0,
    "service": 15.0,
}


def interpolate_edge_risk(
    a: GeoPoint,
    b: GeoPoint,
    risk_points: Iterable[RiskPoint],
    config: RoutingConfig,
) -> EdgeRisk:
    center = midpoint(a, b)
    flood_risk = config.baseline_risk
    slope = 0.0
    influenced = False
    for risk_point in risk_points:
        distance = haversine_m(center, risk_point.point)
        if distance > config.risk_radius_m:
            continue
        normalized = distance / max(config.risk_radius_m, 1.0)
        influence = 1.0 / (1.0 + 9.0 * normalized * normalized)
        point_risk = max(0.0, min(1.0, risk_point.probability))
        decayed_risk = config.baseline_risk + (point_risk - config.baseline_risk) * influence
        flood_risk = max(flood_risk, decayed_risk)
        slope = max(slope, max(0.0, risk_point.slope) * influence)
        influenced = True
    if not influenced:
        return EdgeRisk(config.baseline_risk, 0.0)
    return EdgeRisk(flood_risk, slope)


def risk_weighted_edge_cost(edge: RoadEdge, risk: EdgeRisk, config: RoutingConfig) -> float:
    flood_penalty = config.risk_penalty_multiplier * (risk.flood_risk ** 2)
    slope_excess = max(0.0, risk.slope - config.slope_reference_degrees)
    slope_penalty = config.slope_penalty_multiplier * min(1.0, slope_excess / config.slope_scale_degrees)
    return edge.distance_m * (1.0 + flood_penalty + slope_penalty)


def _dijkstra(
    graph: RoadGraph,
    source: int,
    target: int,
    cost_fn: Callable[[int, RoadEdge], float],
    allowed_fn: Callable[[int, RoadEdge], bool],
) -> tuple[list[int], list[RoadEdge], float]:
    queue: list[tuple[float, int]] = [(0.0, source)]
    distance: dict[int, float] = {source: 0.0}
    previous: dict[int, tuple[int, RoadEdge]] = {}

    while queue:
        current_cost, node_id = heapq.heappop(queue)
        if current_cost != distance.get(node_id, inf):
            continue
        if node_id == target:
            break
        for edge in graph.adjacency.get(node_id, []):
            if not allowed_fn(node_id, edge):
                continue
            candidate = current_cost + cost_fn(node_id, edge)
            if candidate < distance.get(edge.to_node, inf):
                distance[edge.to_node] = candidate
                previous[edge.to_node] = (node_id, edge)
                heapq.heappush(queue, (candidate, edge.to_node))

    if target not in distance:
        raise RouteNotFoundError("No drivable path exists between the selected points")

    node_ids = [target]
    edges: list[RoadEdge] = []
    cursor = target
    while cursor != source:
        prev_node, edge = previous[cursor]
        edges.append(edge)
        node_ids.append(prev_node)
        cursor = prev_node
    node_ids.reverse()
    edges.reverse()
    return node_ids, edges, distance[target]


def _edge_pairs(node_ids: list[int], edges: list[RoadEdge]):
    return zip(node_ids, edges)


def _route_distance(edges: Iterable[RoadEdge]) -> float:
    return sum(edge.distance_m for edge in edges)


def _route_eta_minutes(edges: Iterable[RoadEdge]) -> float:
    hours = 0.0
    for edge in edges:
        speed = edge.maxspeed_kph or HIGHWAY_DEFAULT_SPEED_KPH.get(edge.highway, 25.0)
        speed = max(5.0, min(100.0, speed))
        hours += (edge.distance_m / 1000.0) / speed
    return hours * 60.0


def find_safest_route(
    graph: RoadGraph,
    start: GeoPoint,
    end: GeoPoint,
    risk_points: list[RiskPoint],
    blocked_way_ids: set[int] | None = None,
    config: RoutingConfig | None = None,
) -> RouteResult:
    config = config or RoutingConfig()
    blocked_way_ids = blocked_way_ids or set()
    start_snap = snap_to_graph(graph, start)
    end_snap = snap_to_graph(graph, end)
    if start_snap.distance_m > config.max_snap_distance_m:
        raise RouteNotFoundError(f"Start point is {start_snap.distance_m:.0f} m from the fetched road network")
    if end_snap.distance_m > config.max_snap_distance_m:
        raise RouteNotFoundError(f"Destination is {end_snap.distance_m:.0f} m from the fetched road network")

    risk_cache: dict[tuple[int, int, int], EdgeRisk] = {}

    def edge_risk(from_node: int, edge: RoadEdge) -> EdgeRisk:
        key = (from_node, edge.to_node, edge.way_id)
        if key not in risk_cache:
            risk_cache[key] = interpolate_edge_risk(
                graph.nodes[from_node], graph.nodes[edge.to_node], risk_points, config
            )
        return risk_cache[key]

    def base_allowed(_from_node: int, edge: RoadEdge) -> bool:
        return edge.way_id not in blocked_way_ids

    shortest_nodes, shortest_edges, _ = _dijkstra(
        graph,
        start_snap.node_id,
        end_snap.node_id,
        cost_fn=lambda _from_node, edge: edge.distance_m,
        allowed_fn=base_allowed,
    )
    shortest_distance = _route_distance(shortest_edges)

    def safe_allowed(from_node: int, edge: RoadEdge) -> bool:
        if edge.way_id in blocked_way_ids:
            return False
        threshold = config.extreme_risk_block_threshold
        return threshold is None or edge_risk(from_node, edge).flood_risk < threshold

    route_nodes, route_edges, weighted_cost = _dijkstra(
        graph,
        start_snap.node_id,
        end_snap.node_id,
        cost_fn=lambda from_node, edge: risk_weighted_edge_cost(edge, edge_risk(from_node, edge), config),
        allowed_fn=safe_allowed,
    )

    route_risks = [edge_risk(from_node, edge).flood_risk for from_node, edge in _edge_pairs(route_nodes, route_edges)]
    weighted_risk_sum = sum(risk * edge.distance_m for risk, edge in zip(route_risks, route_edges))
    route_distance = _route_distance(route_edges)
    average_risk = weighted_risk_sum / route_distance if route_distance else 0.0
    max_risk = max(route_risks, default=0.0)

    safe_way_ids = {edge.way_id for edge in route_edges}
    avoided_high_risk_edges = 0
    for from_node, edge in _edge_pairs(shortest_nodes, shortest_edges):
        if edge.way_id not in safe_way_ids and edge_risk(from_node, edge).flood_risk >= config.high_risk_threshold:
            avoided_high_risk_edges += 1

    return RouteResult(
        node_ids=route_nodes,
        way_ids=[edge.way_id for edge in route_edges],
        geometry=[graph.nodes[node_id] for node_id in route_nodes],
        distance_m=route_distance,
        weighted_cost=weighted_cost,
        average_risk=average_risk,
        max_risk=max_risk,
        eta_minutes=_route_eta_minutes(route_edges),
        shortest_distance_m=shortest_distance,
        shortest_node_ids=shortest_nodes,
        avoided_high_risk_edges=avoided_high_risk_edges,
        start_snap_distance_m=start_snap.distance_m,
        end_snap_distance_m=end_snap.distance_m,
    )
