from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .geo import haversine_m
from .models import GeoPoint
from .overpass_client import OverpassUnavailableError, ResilientOverpassClient
from .photon import PhotonFacilityProvider, PhotonUnavailableError


@dataclass
class _FacilityCacheEntry:
    expires_at: float
    facilities: list[dict[str, Any]]


class FacilityLookupError(RuntimeError):
    pass


CATEGORY_PRIORITY = {
    "shelter": 0,
    "hospital": 1,
    "community_centre": 2,
    "clinic": 3,
    "school": 4,
    "college": 5,
}


class OSMFacilityProvider:
    """Discover candidate refuge facilities with resilient OSM providers."""

    def __init__(
        self,
        endpoint: str | None = None,
        timeout_seconds: float = 12.0,
        cache_ttl_seconds: int = 600,
        overpass_client: ResilientOverpassClient | None = None,
        photon_provider: PhotonFacilityProvider | None = None,
    ):
        if overpass_client is None:
            endpoints = [endpoint] if endpoint else None
            overpass_client = ResilientOverpassClient(endpoints=endpoints, timeout_seconds=timeout_seconds)
        self.overpass_client = overpass_client
        self.photon_provider = photon_provider or PhotonFacilityProvider(timeout_seconds=min(timeout_seconds, 8.0))
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[tuple[float, float, int], _FacilityCacheEntry] = {}

    @staticmethod
    def build_primary_query(center: GeoPoint, radius_m: int) -> str:
        lat, lon = center.lat, center.lon
        return f"""
[out:json][timeout:15];
(
  nwr[\"emergency\"=\"shelter\"](around:{radius_m},{lat},{lon});
  nwr[\"social_facility\"=\"shelter\"](around:{radius_m},{lat},{lon});
  nwr[\"amenity\"=\"shelter\"](around:{radius_m},{lat},{lon});
  nwr[\"amenity\"~\"^(hospital|clinic|community_centre)$\"](around:{radius_m},{lat},{lon});
);
out center tags;
""".strip()

    @staticmethod
    def build_secondary_query(center: GeoPoint, radius_m: int) -> str:
        lat, lon = center.lat, center.lon
        return f"""
[out:json][timeout:15];
(
  nwr[\"amenity\"~\"^(school|college)$\"](around:{radius_m},{lat},{lon});
);
out center tags;
""".strip()

    @staticmethod
    def build_query(center: GeoPoint, radius_m: int) -> str:
        # Backwards-compatible alias used by older tests/docs.
        return OSMFacilityProvider.build_primary_query(center, radius_m)

    @staticmethod
    def _category(tags: dict[str, Any]) -> str:
        if tags.get("emergency") == "shelter" or tags.get("social_facility") == "shelter" or tags.get("amenity") == "shelter":
            return "shelter"
        value = str(tags.get("amenity") or tags.get("social_facility") or tags.get("emergency") or "facility")
        return value

    @classmethod
    def _parse_overpass(cls, payload: dict[str, Any], center: GeoPoint, provider: str) -> list[dict[str, Any]]:
        facilities: list[dict[str, Any]] = []
        for element in payload.get("elements", []):
            point_data = element if "lat" in element and "lon" in element else element.get("center", {})
            if "lat" not in point_data or "lon" not in point_data:
                continue
            try:
                point = GeoPoint(float(point_data["lat"]), float(point_data["lon"]))
            except (TypeError, ValueError):
                continue
            tags = element.get("tags", {}) or {}
            category = cls._category(tags)
            name = tags.get("name") or f"OSM {category.replace('_', ' ').title()}"
            facilities.append({
                "osm_id": f"{element.get('type', 'object')}/{element.get('id')}",
                "name": str(name),
                "category": category,
                "lat": point.lat,
                "lon": point.lon,
                "distance_m": round(haversine_m(center, point), 1),
                "official_shelter": False,
                "source": "OpenStreetMap/Overpass",
                "provider": provider,
            })
        return facilities

    @staticmethod
    def _rank_and_dedupe(items: list[dict[str, Any]], radius_m: int) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for item in items:
            try:
                distance_m = float(item["distance_m"])
                lat = float(item["lat"])
                lon = float(item["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            if distance_m > radius_m:
                continue
            item["lat"] = lat
            item["lon"] = lon
            item["distance_m"] = round(distance_m, 1)
            key = str(item.get("osm_id") or f"{item.get('name','')}:{lat:.5f}:{lon:.5f}")
            existing = deduped.get(key)
            if existing is None or float(existing["distance_m"]) > distance_m:
                deduped[key] = item
        ranked = list(deduped.values())
        ranked.sort(key=lambda item: (CATEGORY_PRIORITY.get(str(item.get("category")), 99), float(item["distance_m"])))
        return ranked[:25]

    async def find_nearby(self, center: GeoPoint, radius_m: int = 10_000) -> list[dict[str, Any]]:
        radius_m = max(500, min(20_000, int(radius_m)))
        key = (round(center.lat, 3), round(center.lon, 3), radius_m)
        now = time.monotonic()
        cached = self._cache.get(key)
        if cached and cached.expires_at > now:
            return cached.facilities

        facilities: list[dict[str, Any]] = []
        overpass_error: Exception | None = None
        try:
            primary = await self.overpass_client.query(self.build_primary_query(center, radius_m), purpose="facility lookup")
            facilities.extend(self._parse_overpass(primary.payload, center, primary.endpoint))
            # Schools/colleges are only fallback refuge candidates. Fetch them
            # only when higher-priority facilities are sparse.
            if len(facilities) < 8:
                try:
                    secondary = await self.overpass_client.query(self.build_secondary_query(center, radius_m), purpose="facility fallback lookup")
                    facilities.extend(self._parse_overpass(secondary.payload, center, secondary.endpoint))
                except OverpassUnavailableError:
                    pass
        except OverpassUnavailableError as exc:
            overpass_error = exc

        facilities = self._rank_and_dedupe(facilities, radius_m)
        if not facilities:
            try:
                facilities = self._rank_and_dedupe(
                    await self.photon_provider.find_nearby(center, radius_m),
                    radius_m,
                )
            except PhotonUnavailableError as photon_error:
                raise FacilityLookupError(
                    f"OSM facility providers are temporarily unavailable. Overpass: {overpass_error or 'no results'}; Photon: {photon_error}"
                ) from photon_error

        self._cache[key] = _FacilityCacheEntry(time.monotonic() + self.cache_ttl_seconds, facilities)
        return facilities
