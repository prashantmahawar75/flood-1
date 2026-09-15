from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .overpass_client import DEFAULT_OVERPASS_ENDPOINTS
from .osrm_fallback import DEFAULT_OSRM_ENDPOINTS


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _csv_env(name: str, defaults: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name, "").strip()
    values = [item.strip().rstrip("/") for item in raw.split(",") if item.strip()] if raw else list(defaults)
    legacy = os.getenv("OVERPASS_URL", "").strip().rstrip("/") if name == "OVERPASS_ENDPOINTS" else ""
    # Preserve the old Render variable, but don't force an overloaded legacy
    # endpoint ahead of the resilient defaults if it is already present.
    if legacy and legacy not in values:
        values.insert(0, legacy)
    return tuple(dict.fromkeys(values))


@dataclass(frozen=True)
class Settings:
    project_root: Path = PROJECT_ROOT
    overpass_timeout_seconds: float = float(os.getenv("OVERPASS_TIMEOUT_SECONDS", "12"))
    road_cache_ttl_seconds: int = int(os.getenv("ROAD_CACHE_TTL_SECONDS", "900"))
    max_route_distance_km: float = float(os.getenv("MAX_ROUTE_DISTANCE_KM", "35"))
    provider_cooldown_seconds: float = float(os.getenv("PROVIDER_COOLDOWN_SECONDS", "120"))
    photon_url: str = os.getenv("PHOTON_URL", "https://photon.komoot.io/reverse")
    external_api_timeout_seconds: float = float(os.getenv("EXTERNAL_API_TIMEOUT_SECONDS", "12"))

    @property
    def overpass_endpoints(self) -> tuple[str, ...]:
        return _csv_env("OVERPASS_ENDPOINTS", DEFAULT_OVERPASS_ENDPOINTS)

    @property
    def osrm_endpoints(self) -> tuple[str, ...]:
        return _csv_env("OSRM_ENDPOINTS", DEFAULT_OSRM_ENDPOINTS)

    @property
    def model_path(self) -> Path:
        return self.project_root / "backend" / "artifacts" / "flood_rf.joblib"

    @property
    def scaling_path(self) -> Path:
        return self.project_root / "data" / "train model yaha se" / "scaling_parameters.json"

    @property
    def station_inventory_path(self) -> Path:
        return self.project_root / "data" / "STATION_INVENTORY.csv"

    @property
    def terrain_path(self) -> Path:
        return self.project_root / "data" / "TERRAIN_DATA.csv"

    @property
    def frontend_dir(self) -> Path:
        return self.project_root / "frontend"
