from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np


@dataclass(frozen=True)
class RiskPrediction:
    probability: float
    score: float
    tier: str
    feature_order: tuple[str, ...]


class FloodRiskModel:
    """Inference wrapper for the PRAHARI seven-feature flood-risk model."""

    def __init__(
        self,
        model_path: str | Path | None,
        scaling_path: str | Path,
        estimator: Any | None = None,
    ) -> None:
        self.scaling_path = Path(scaling_path)
        with self.scaling_path.open("r", encoding="utf-8") as handle:
            self.scaling = json.load(handle)
        self.feature_order = tuple(self.scaling["model_feature_order"])
        self.estimator = estimator
        if self.estimator is None and model_path is not None:
            self.estimator = joblib.load(Path(model_path))

    @staticmethod
    def tier_for_probability(probability: float) -> str:
        if probability >= 0.80:
            return "HIGH_RISK"
        if probability >= 0.40:
            return "WATCH"
        return "SAFE"

    def transform(self, raw: Mapping[str, float | int]) -> np.ndarray:
        values: list[float] = []
        for model_feature in self.feature_order:
            if model_feature == "discharge_sensor_outage":
                values.append(float(raw.get(model_feature, 0)))
                continue
            if not model_feature.endswith("_scaled"):
                raise ValueError(f"Unsupported model feature: {model_feature}")
            raw_name = model_feature[: -len("_scaled")]
            if raw_name not in raw:
                raise ValueError(f"Missing raw feature: {raw_name}")
            params = self.scaling["features"][raw_name]
            std = float(params["std"])
            if std == 0:
                raise ValueError(f"Invalid zero std for feature: {raw_name}")
            values.append((float(raw[raw_name]) - float(params["mean"])) / std)
        return np.asarray([values], dtype=float)

    def predict(self, raw: Mapping[str, float | int]) -> RiskPrediction:
        if self.estimator is None:
            raise RuntimeError("Flood-risk estimator is not loaded")
        transformed = self.transform(raw)
        probability = float(self.estimator.predict_proba(transformed)[0, 1])
        probability = min(1.0, max(0.0, probability))
        return RiskPrediction(
            probability=probability,
            score=probability * 100.0,
            tier=self.tier_for_probability(probability),
            feature_order=self.feature_order,
        )
