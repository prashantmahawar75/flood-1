from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lon: float


@dataclass(frozen=True)
class RoadEdge:
    to_node: int
    distance_m: float
    way_id: int
    highway: str
    name: str | None = None
    maxspeed_kph: float | None = None
    tags: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoadGraph:
    nodes: dict[int, GeoPoint]
    adjacency: dict[int, list[RoadEdge]]
    provider: str | None = None

    @property
    def edge_count(self) -> int:
        return sum(len(edges) for edges in self.adjacency.values())


@dataclass(frozen=True)
class SnappedPoint:
    node_id: int
    point: GeoPoint
    distance_m: float


@dataclass(frozen=True)
class RiskPoint:
    point: GeoPoint
    probability: float
    slope: float = 0.0
    label: str | None = None
