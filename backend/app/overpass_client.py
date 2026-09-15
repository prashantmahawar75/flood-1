from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

LOGGER = logging.getLogger(__name__)

DEFAULT_OVERPASS_ENDPOINTS = (
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)


class OverpassUnavailableError(RuntimeError):
    """Raised only after every configured Overpass provider has failed."""


@dataclass(frozen=True)
class OverpassQueryResult:
    payload: dict[str, Any]
    endpoint: str


class ResilientOverpassClient:
    """Small failover client for public Overpass instances.

    A failed provider is cooled down in-memory so repeated user clicks do not
    immediately hammer an unhealthy endpoint. Public endpoints remain best-
    effort services; callers should still provide a graceful fallback.
    """

    def __init__(
        self,
        endpoints: Iterable[str] | None = None,
        timeout_seconds: float = 12.0,
        cooldown_seconds: float = 120.0,
    ) -> None:
        normalized = []
        for endpoint in endpoints or DEFAULT_OVERPASS_ENDPOINTS:
            endpoint = str(endpoint).strip().rstrip("/")
            if endpoint and endpoint not in normalized:
                normalized.append(endpoint)
        if not normalized:
            raise ValueError("At least one Overpass endpoint is required")
        self.endpoints = tuple(normalized)
        self.timeout_seconds = max(2.0, float(timeout_seconds))
        self.cooldown_seconds = max(5.0, float(cooldown_seconds))
        self._cooldown_until: dict[str, float] = {}
        self._preferred_endpoint: str | None = None

    def _ordered_endpoints(self) -> list[str]:
        now = time.monotonic()
        healthy = [endpoint for endpoint in self.endpoints if self._cooldown_until.get(endpoint, 0.0) <= now]
        if not healthy:
            # When everything is cooling down, retry the endpoint whose cooldown
            # expires first rather than returning a permanent local failure.
            return sorted(self.endpoints, key=lambda endpoint: self._cooldown_until.get(endpoint, 0.0))
        if self._preferred_endpoint in healthy:
            healthy.remove(self._preferred_endpoint)  # type: ignore[arg-type]
            healthy.insert(0, self._preferred_endpoint)  # type: ignore[arg-type]
        return healthy

    async def query(self, query: str, purpose: str = "query") -> OverpassQueryResult:
        failures: list[str] = []
        headers = {
            "User-Agent": "PRAHARI-SIH26192/2.1 (flash-flood evacuation decision-support demo)",
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds, headers=headers, follow_redirects=True) as client:
            for endpoint in self._ordered_endpoints():
                try:
                    response = await client.post(endpoint, data={"data": query})
                    response.raise_for_status()
                    payload = response.json()
                    if not isinstance(payload, dict) or not isinstance(payload.get("elements", []), list):
                        raise RuntimeError("provider returned an invalid Overpass JSON payload")
                    self._preferred_endpoint = endpoint
                    self._cooldown_until.pop(endpoint, None)
                    return OverpassQueryResult(payload=payload, endpoint=endpoint)
                except (httpx.HTTPError, ValueError, RuntimeError) as exc:
                    self._cooldown_until[endpoint] = time.monotonic() + self.cooldown_seconds
                    failures.append(f"{endpoint}: {type(exc).__name__}: {exc}")
                    LOGGER.warning("Overpass provider failed for %s: %s (%s)", purpose, endpoint, exc)
        raise OverpassUnavailableError(
            f"All Overpass providers failed for {purpose}. " + " | ".join(failures)
        )
