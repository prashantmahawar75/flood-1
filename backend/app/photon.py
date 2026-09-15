from __future__ import annotations

from typing import Any, Iterable

import httpx

from .geo import haversine_m
from .models import GeoPoint


class PhotonUnavailableError(RuntimeError):
    pass


class PhotonFacilityProvider:
    """Low-volume fallback facility discovery using Photon/OpenStreetMap.

    Photon is intentionally a fallback, not the primary data source. Results
    are distance-filtered locally because the public API's radius is a search
    hint rather than an evacuation-safety guarantee.
    """

    CATEGORY_TAGS = (
        ("shelter", "emergency:shelter"),
        ("shelter", "amenity:shelter"),
        ("hospital", "amenity:hospital"),
        ("community_centre", "amenity:community_centre"),
        ("clinic", "amenity:clinic"),
        ("school", "amenity:school"),
        ("college", "amenity:college"),
    )

    def __init__(self, endpoint: str = "https://photon.komoot.io/reverse", timeout_seconds: float = 8.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = max(2.0, float(timeout_seconds))

    async def find_nearby(self, center: GeoPoint, radius_m: int) -> list[dict[str, Any]]:
        radius_km = max(0.5, min(20.0, radius_m / 1000.0))
        headers = {"User-Agent": "PRAHARI-SIH26192/2.1 (facility fallback)"}
        failures: list[str] = []
        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        async with httpx.AsyncClient(timeout=self.timeout_seconds, headers=headers, follow_redirects=True) as client:
            for category, osm_tag in self.CATEGORY_TAGS:
                # Avoid six/seven calls when higher-priority results already give
                # the user a useful choice list.
                if len(results) >= 12 and category in {"school", "college"}:
                    break
                try:
                    response = await client.get(
                        self.endpoint,
                        params={
                            "lat": center.lat,
                            "lon": center.lon,
                            "radius": round(radius_km, 2),
                            "osm_tag": osm_tag,
                            "limit": 5,
                            "lang": "en",
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                except (httpx.HTTPError, ValueError) as exc:
                    failures.append(f"{osm_tag}: {type(exc).__name__}: {exc}")
                    continue
                for feature in payload.get("features", []):
                    geometry = feature.get("geometry", {})
                    coords = geometry.get("coordinates", [])
                    if not isinstance(coords, list) or len(coords) < 2:
                        continue
                    try:
                        point = GeoPoint(float(coords[1]), float(coords[0]))
                    except (TypeError, ValueError):
                        continue
                    distance_m = haversine_m(center, point)
                    if distance_m > radius_m:
                        continue
                    props = feature.get("properties", {}) or {}
                    osm_type = {"N": "node", "W": "way", "R": "relation"}.get(str(props.get("osm_type", "")).upper(), "object")
                    raw_id = props.get("osm_id") or f"{point.lat:.6f},{point.lon:.6f}"
                    osm_id = f"{osm_type}/{raw_id}"
                    if osm_id in seen:
                        continue
                    seen.add(osm_id)
                    name = props.get("name") or props.get("street") or f"Nearby {category.replace('_', ' ').title()}"
                    results.append({
                        "osm_id": osm_id,
                        "name": str(name),
                        "category": category,
                        "lat": point.lat,
                        "lon": point.lon,
                        "distance_m": round(distance_m, 1),
                        "official_shelter": False,
                        "source": "OpenStreetMap/Photon",
                        "provider": "photon.komoot.io",
                    })
        if not results and failures:
            raise PhotonUnavailableError("Photon fallback failed: " + " | ".join(failures))
        return results
