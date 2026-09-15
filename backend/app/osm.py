from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from .overpass_client import ResilientOverpassClient

from .geo import bbox_for_points, haversine_m
from .models import GeoPoint, RoadEdge, RoadGraph

DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DRIVABLE_HIGHWAYS = {
    "motorway", "trunk", "primary", "secondary", "tertiary", "unclassified",
    "residential", "living_street", "service", "motorway_link", "trunk_link",
    "primary_link", "secondary_link", "tertiary_link",
}


def _parse_maxspeed(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).lower().strip()
    try:
        if "mph" in text:
            return float(text.split()[0]) * 1.609344
        return float(text.split()[0])
    except (ValueError, IndexError):
        return None


def parse_overpass_roads(payload: dict[str, Any]) -> RoadGraph:
    nodes: dict[int, GeoPoint] = {}
    ways: list[dict[str, Any]] = []
    for element in payload.get("elements", []):
        if element.get("type") == "node" and "lat" in element and "lon" in element:
            nodes[int(element["id"])] = GeoPoint(lat=float(element["lat"]), lon=float(element["lon"]))
        elif element.get("type") == "way":
            ways.append(element)

    adjacency: dict[int, list[RoadEdge]] = {node_id: [] for node_id in nodes}
    for way in ways:
        tags = dict(way.get("tags", {}))
        highway = tags.get("highway")
        if highway not in DRIVABLE_HIGHWAYS:
            continue
        if str(tags.get("access", "")).lower() in {"no", "private"}:
            continue
        if str(tags.get("motor_vehicle", "")).lower() in {"no", "private"}:
            continue
        way_nodes = [int(node_id) for node_id in way.get("nodes", []) if int(node_id) in nodes]
        if len(way_nodes) < 2:
            continue
        oneway_value = str(tags.get("oneway", "")).lower()
        is_oneway = oneway_value in {"yes", "1", "true"} or tags.get("junction") == "roundabout"
        reverse_oneway = oneway_value == "-1"
        way_id = int(way["id"])
        name = tags.get("name")
        maxspeed = _parse_maxspeed(tags.get("maxspeed"))
        for left, right in zip(way_nodes, way_nodes[1:]):
            distance = haversine_m(nodes[left], nodes[right])
            if reverse_oneway:
                adjacency[right].append(RoadEdge(left, distance, way_id, highway, name, maxspeed, tags))
            else:
                adjacency[left].append(RoadEdge(right, distance, way_id, highway, name, maxspeed, tags))
                if not is_oneway:
                    adjacency[right].append(RoadEdge(left, distance, way_id, highway, name, maxspeed, tags))
    return RoadGraph(nodes=nodes, adjacency=adjacency)


@dataclass
class _CacheEntry:
    expires_at: float
    graph: RoadGraph


class OSMRoadProvider:
    def __init__(
        self,
        endpoint: str | None = None,
        timeout_seconds: float = 12.0,
        cache_ttl_seconds: int = 600,
        overpass_client: ResilientOverpassClient | None = None,
    ) -> None:
        endpoints = [endpoint] if endpoint else None
        self.overpass_client = overpass_client or ResilientOverpassClient(
            endpoints=endpoints, timeout_seconds=timeout_seconds
        )
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[tuple[float, float, float, float], _CacheEntry] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _cache_key(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
        return tuple(round(value, 4) for value in bbox)  # type: ignore[return-value]

    @staticmethod
    def build_query(bbox: tuple[float, float, float, float]) -> str:
        south, west, north, east = bbox
        highway_regex = "|".join(sorted(DRIVABLE_HIGHWAYS))
        return (
            "[out:json][timeout:18];"
            f"way[\"highway\"~\"^({highway_regex})$\"]({south},{west},{north},{east});"
            "(._;>;);out body;"
        )

    async def fetch_graph(self, start: GeoPoint, end: GeoPoint, margin_km: float = 2.0) -> RoadGraph:
        bbox = bbox_for_points(start, end, margin_km=margin_km)
        key = self._cache_key(bbox)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and cached.expires_at > now:
            return cached.graph
        query = self.build_query(bbox)
        async with self._lock:
            cached = self._cache.get(key)
            if cached and cached.expires_at > time.monotonic():
                return cached.graph
            result = await self.overpass_client.query(query, purpose="road graph")
            graph = parse_overpass_roads(result.payload)
            if not graph.nodes or graph.edge_count == 0:
                raise RuntimeError("OpenStreetMap returned no drivable roads for this area")
            graph.provider = result.endpoint
            self._cache[key] = _CacheEntry(time.monotonic() + self.cache_ttl_seconds, graph)
            return graph

