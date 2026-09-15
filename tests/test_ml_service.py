from pathlib import Path

import pytest

from backend.app.ml_service import FloodRiskModel


ROOT = Path(__file__).resolve().parents[1]
SCALING = ROOT / "data" / "train model yaha se" / "scaling_parameters.json"
MODEL = ROOT / "backend" / "artifacts" / "flood_rf.joblib"


def sample_observation():
    return {
        "rainfall_mm": 6.395273,
        "rainfall_3d_cum_mm": 19.209031,
        "river_discharge": 55.561825,
        "river_discharge_roc": -0.340381,
        "slope": 12.053519,
        "drainage_density": 2.801709,
        "discharge_sensor_outage": 0,
    }


def test_transform_uses_existing_scaling_contract():
    model = FloodRiskModel(model_path=None, scaling_path=SCALING, estimator=None)
    transformed = model.transform(sample_observation())
    assert transformed.shape == (1, 7)
    assert transformed[0][:6] == pytest.approx([0, 0, 0, 0, 0, 0], abs=1e-7)
    assert transformed[0][6] == 0


def test_risk_tiers_match_operational_thresholds():
    assert FloodRiskModel.tier_for_probability(0.20) == "SAFE"
    assert FloodRiskModel.tier_for_probability(0.40) == "WATCH"
    assert FloodRiskModel.tier_for_probability(0.7999) == "WATCH"
    assert FloodRiskModel.tier_for_probability(0.80) == "HIGH_RISK"


def test_trained_model_returns_probability_and_score():
    assert MODEL.exists(), "training step must create backend/artifacts/flood_rf.joblib"
    model = FloodRiskModel(model_path=MODEL, scaling_path=SCALING)
    result = model.predict(sample_observation())
    assert 0.0 <= result.probability <= 1.0
    assert result.score == pytest.approx(result.probability * 100, abs=1e-8)
    assert result.tier in {"SAFE", "WATCH", "HIGH_RISK"}
    assert result.feature_order[-1] == "discharge_sensor_outage"
