from __future__ import annotations

from pydantic import BaseModel, Field


class PointIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class ObservationIn(BaseModel):
    rainfall_mm: float = Field(ge=0, le=2000)
    rainfall_3d_cum_mm: float = Field(ge=0, le=5000)
    river_discharge: float = Field(ge=0, le=100000)
    river_discharge_roc: float = Field(ge=-100000, le=100000)
    slope: float = Field(ge=0, le=90)
    drainage_density: float = Field(ge=0, le=20)
    discharge_sensor_outage: int = Field(ge=0, le=1)


class RiskRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    observation: ObservationIn
    label: str | None = None


class RiskPointIn(PointIn):
    probability: float = Field(ge=0, le=1)
    slope: float = Field(default=0, ge=0, le=90)
    label: str | None = None


class RoutingOptionsIn(BaseModel):
    risk_radius_m: float = Field(default=10000, ge=100, le=50000)
    baseline_risk: float = Field(default=0.0, ge=0, le=1)
    risk_penalty_multiplier: float = Field(default=10.0, ge=0, le=100)
    slope_penalty_multiplier: float = Field(default=2.5, ge=0, le=50)
    slope_reference_degrees: float = Field(default=8.0, ge=0, le=90)
    slope_scale_degrees: float = Field(default=22.0, gt=0, le=90)
    extreme_risk_block_threshold: float | None = Field(default=0.97, ge=0, le=1)
    high_risk_threshold: float = Field(default=0.60, ge=0, le=1)
    max_snap_distance_m: float = Field(default=2500, ge=50, le=10000)


class RouteRequest(BaseModel):
    start: PointIn
    end: PointIn
    risk_points: list[RiskPointIn] = Field(default_factory=list, max_length=100)
    blocked_way_ids: list[int] = Field(default_factory=list, max_length=500)
    routing: RoutingOptionsIn | None = None
