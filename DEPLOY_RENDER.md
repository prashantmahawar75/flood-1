# Deploy PRAHARI v2.1 on Render

The full-stack application is one Docker web service: FastAPI serves both the API and `frontend/`.

## Existing Render service

If `prahari-flash-flood` already exists:

1. Push this corrected project to the GitHub branch connected to Render.
2. In **Render → Service → Environment**, set:

```text
OVERPASS_ENDPOINTS=https://overpass.private.coffee/api/interpreter,https://maps.mail.ru/osm/tools/overpass/api/interpreter,https://overpass-api.de/api/interpreter
OVERPASS_TIMEOUT_SECONDS=12
PROVIDER_COOLDOWN_SECONDS=120
ROAD_CACHE_TTL_SECONDS=900
PHOTON_URL=https://photon.komoot.io/reverse
OSRM_ENDPOINTS=https://router.project-osrm.org/route/v1/driving,https://routing.openstreetmap.de/routed-car/route/v1/driving
EXTERNAL_API_TIMEOUT_SECONDS=12
MAX_ROUTE_DISTANCE_KM=35
```

3. The old single-provider `OVERPASS_URL` can be removed. If left in place it is not required by v2.1.
4. **Health Check Path:** `/api/health`
5. Trigger **Manual Deploy → Deploy latest commit**.

Do not set `PORT`; Render injects it automatically and the Dockerfile reads it.

## Verify after deployment

Open:

```text
https://YOUR-SERVICE.onrender.com/api/health
https://YOUR-SERVICE.onrender.com/
```

`/api/health` should show version `2.1.0` and:

```json
{
  "external_services": {
    "overpass_failover_count": 3,
    "photon_fallback": true,
    "osrm_fallback_count": 2
  }
}
```

Then test in the UI:

1. Pick an origin.
2. Click **Find nearby facilities**. The panel should show which provider supplied results.
3. Pick a facility or a manual destination.
4. Add at least one ML risk point.
5. Click **Find safest route**. The route card shows either:
   - `Risk-aware Dijkstra` (primary live OSM graph), or
   - `Risk-aware real-road alternatives` (OSRM fallback if graph extraction is temporarily unavailable).

The fallback is intentionally labelled so the UI never claims Dijkstra ran when the primary road graph could not be downloaded.
