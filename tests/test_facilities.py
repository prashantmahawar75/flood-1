import asyncio

from backend.app.facilities import OSMFacilityProvider
from backend.app.models import GeoPoint
from backend.app.overpass_client import OverpassQueryResult


def test_osm_facilities_are_ranked_and_not_claimed_official():
    class Overpass:
        async def query(self, query, purpose="query"):
            if "school|college" in query:
                payload = {"elements": [
                    {"type": "node", "id": 2, "lat": 11.01, "lon": 76.0, "tags": {"amenity": "school", "name": "Far School"}},
                ]}
            else:
                payload = {"elements": [
                    {"type": "node", "id": 1, "lat": 11.001, "lon": 76.0, "tags": {"amenity": "community_centre", "name": "Near Centre"}},
                ]}
            return OverpassQueryResult(payload=payload, endpoint="https://example.invalid/api/interpreter")

    provider = OSMFacilityProvider(overpass_client=Overpass())
    items = asyncio.run(provider.find_nearby(GeoPoint(11.0, 76.0), radius_m=5000))
    assert [item["name"] for item in items] == ["Near Centre", "Far School"]
    assert all(item["official_shelter"] is False for item in items)
    assert all(item["source"] == "OpenStreetMap/Overpass" for item in items)
    assert all(item["provider"] == "https://example.invalid/api/interpreter" for item in items)
