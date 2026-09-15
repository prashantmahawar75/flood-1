from __future__ import annotations

import math

from .models import GeoPoint, RoadGraph, SnappedPoint

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(a: GeoPoint, b: GeoPoint) -> float:
    lat1 = math.radians(a.lat)
    lat2 = math.radians(b.lat)
    dlat = lat2 - lat1
    dlon = math.radians(b.lon - a.lon)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def midpoint(a: GeoPoint, b: GeoPoint) -> GeoPoint:
    return GeoPoint(lat=(a.lat + b.lat) / 2.0, lon=(a.lon + b.lon) / 2.0)


def snap_to_graph(graph: RoadGraph, point: GeoPoint) -> SnappedPoint:
    if not graph.nodes:
        raise ValueError("Cannot snap to an empty road graph")
    node_id, node_point = min(graph.nodes.items(), key=lambda item: haversine_m(point, item[1]))
    return SnappedPoint(node_id=node_id, point=node_point, distance_m=haversine_m(point, node_point))


def bbox_for_points(a: GeoPoint, b: GeoPoint, margin_km: float = 2.0) -> tuple[float, float, float, float]:
    mid_lat = (a.lat + b.lat) / 2.0
    lat_margin = margin_km / 111.0
    lon_scale = max(0.2, math.cos(math.radians(mid_lat)))
    lon_margin = margin_km / (111.0 * lon_scale)
    south = min(a.lat, b.lat) - lat_margin
    north = max(a.lat, b.lat) + lat_margin
    west = min(a.lon, b.lon) - lon_margin
    east = max(a.lon, b.lon) + lon_margin
    return south, west, north, east
