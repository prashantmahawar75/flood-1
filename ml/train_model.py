from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

RANDOM_STATE = 42


def train(project_root: Path) -> dict[str, float | int | str]:
    data_dir = project_root / "data" / "train model yaha se"
    artifact_dir = project_root / "backend" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    with (data_dir / "scaling_parameters.json").open("r", encoding="utf-8") as handle:
        scaling = json.load(handle)

    train_df = pd.read_csv(data_dir / "train_features.csv")
    test_df = pd.read_csv(data_dir / "test_features.csv")
    features = scaling["model_feature_order"]
    target = scaling["target_column"]

    model = RandomForestClassifier(
        n_estimators=30,
        max_depth=5,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )
    x_train = train_df[features].to_numpy(dtype=float)
    x_test = test_df[features].to_numpy(dtype=float)
    model.fit(x_train, train_df[target].to_numpy())

    probabilities = model.predict_proba(x_test)[:, 1]
    threshold = 0.80
    predictions = (probabilities >= threshold).astype(int)
    metrics: dict[str, float | int | str] = {
        "model": "RandomForestClassifier",
        "n_estimators": 30,
        "max_depth": 5,
        "random_state": RANDOM_STATE,
        "threshold": threshold,
        "roc_auc": float(roc_auc_score(test_df[target], probabilities)),
        "precision": float(precision_score(test_df[target], predictions, zero_division=0)),
        "recall": float(recall_score(test_df[target], predictions, zero_division=0)),
        "f1": float(f1_score(test_df[target], predictions, zero_division=0)),
        "train_rows": int(len(train_df)),
        "test_rows": int(len(test_df)),
        "target": target,
    }

    joblib.dump(model, artifact_dir / "flood_rf.joblib")
    with (artifact_dir / "model_metrics.json").open("w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train the PRAHARI backend Random Forest model")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    metrics = train(args.project_root.resolve())
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
