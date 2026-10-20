"""Train and use a length-of-stay predictor for planning experiments.

The LOS bridge branch supplied an inference hook but no saved model. This
module creates a reproducible local artifact from the existing split Parquet.
Only 2019–2020 rows fit the model; 2021 calibrates its interval, and 2022 is
reserved for reporting. Source identifiers are never model features.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

from duration_features import apply_category_mapping, engineer_features, fit_category_mapping
from surgery_duration import CAT, FIXED_FEATURES, NUM, prepared

TARGET = "target_los_days"
DEFAULT_DATA = Path("resources/model_los_dataset.parquet")
DEFAULT_ARTIFACT = Path("artifacts/ml-models/los_regressor.joblib")
CALIBRATION_MIN_ROWS = 9  # smallest n with ceil(0.9 (n + 1)) <= n


def _partitions(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required = {"split", "split_patient_id", "split_event_date", TARGET, *FIXED_FEATURES}
    if missing := required - set(frame.columns):
        raise ValueError(f"LOS dataset missing columns: {sorted(missing)}")
    if not frame.index.is_unique or not frame["split"].isin(("train", "validation", "test")).all():
        raise ValueError("LOS dataset has invalid indices or split labels")
    parts = tuple(frame.loc[frame["split"].eq(name)].copy() for name in ("train", "validation", "test"))
    keys = []
    for part in parts:
        if part.empty or part["split_patient_id"].isna().any() or part["split_event_date"].isna().any():
            raise ValueError("LOS split is empty or has missing identifiers/dates")
        if not np.isfinite(part[TARGET]).all() or not part[TARGET].ge(1).all():
            raise ValueError("LOS target must be finite inclusive days >= 1")
        keys.append(set(part["split_patient_id"]))
    if any(keys[i] & keys[j] for i in range(3) for j in range(i + 1, 3)):
        raise ValueError("LOS patients are shared across splits")
    if not (parts[0]["split_event_date"].max() < parts[1]["split_event_date"].min()
            and parts[1]["split_event_date"].max() < parts[2]["split_event_date"].min()):
        raise ValueError("LOS splits must be chronological")
    if len(parts[1]) < CALIBRATION_MIN_ROWS:
        raise ValueError(f"LOS calibration requires at least {CALIBRATION_MIN_ROWS} "
                         "validation rows for 90% coverage")
    return parts


def _point(model, features: pd.DataFrame, *, log_target: bool = True) -> np.ndarray:
    prediction = model.predict(features)
    return np.maximum(1.0, np.expm1(prediction) if log_target else prediction)


def fit_los_model(data: Path = DEFAULT_DATA, artifact: Path = DEFAULT_ARTIFACT) -> dict:
    frame = pd.read_parquet(data)
    train, validation, test = _partitions(frame)
    columns = list(FIXED_FEATURES)  # no proposed-date or post-operative fields
    x_train, x_validation, x_test = (prepared(part, columns) for part in (train, validation, test))
    nums, cats = [c for c in columns if c in NUM], [c for c in columns if c in CAT]
    preprocessing = ColumnTransformer([
        ("numeric", SimpleImputer(strategy="median"), nums),
        ("categorical", OneHotEncoder(handle_unknown="ignore", min_frequency=10), cats),
    ])
    model = make_pipeline(preprocessing, XGBRegressor(
        objective="reg:squarederror", n_estimators=400, max_depth=5,
        learning_rate=0.04, subsample=0.9, colsample_bytree=0.9,
        reg_lambda=5, n_jobs=4, random_state=42, tree_method="hist",
    ))
    model.fit(x_train, np.log1p(train[TARGET].to_numpy(dtype=float)))
    validation_prediction = _point(model, x_validation)
    scores = np.abs(validation[TARGET].to_numpy(dtype=float) - validation_prediction)
    rank = int(np.ceil((len(scores) + 1) * 0.9))
    half_width = float(np.sort(scores)[rank - 1])
    test_prediction = _point(model, x_test)
    actual = test[TARGET].to_numpy(dtype=float)
    report = {
        "train_rows": len(train), "calibration_rows": len(validation), "test_rows": len(test),
        "test_mae_days": float(mean_absolute_error(actual, test_prediction)),
        "test_rmse_days": float(np.sqrt(mean_squared_error(actual, test_prediction))),
        "test_r2": float(r2_score(actual, test_prediction)),
        "interval_coverage_test": float(np.mean(np.abs(actual - test_prediction) <= half_width)),
        "interval_half_width_days": half_width,
        "dataset_sha256": sha256(data.read_bytes()).hexdigest(),
        "features": columns,
        "protocol": "2019-2020 train; 2021 absolute-residual conformal calibration; 2022 test",
    }
    mapping = fit_category_mapping(x_train, cats, min_count=1)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": model, "features": columns, "category_mapping": mapping,
                 "interval_half_width_days": half_width, "dataset_sha256": report["dataset_sha256"]}, artifact)
    artifact.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def predict_los(frame: pd.DataFrame, artifact: Path = DEFAULT_ARTIFACT, *, raw: bool = False) -> pd.DataFrame:
    return predict_los_loaded(frame, joblib.load(artifact), raw=raw)


def predict_los_loaded(frame: pd.DataFrame, saved: dict, *, raw: bool = False) -> pd.DataFrame:
    """Inferer avec un artefact deja charge (service web / prediction en lot)."""
    columns = saved["features"]
    if raw:
        frame = apply_category_mapping(engineer_features(frame, columns), saved["category_mapping"])
    features = prepared(frame, columns)
    # Historical LOS artifacts are log-target models. Versioned baseline/direct
    # target artifacts explicitly declare False and must not be exponentiated.
    point = _point(saved["model"], features, log_target=saved.get("log_target", True))
    width = saved["interval_half_width_days"]
    if (not np.isscalar(width) or not isinstance(width, (int, float, np.number))
            or not np.isfinite(width) or width < 0):
        raise ValueError("LOS interval half-width must be a finite nonnegative scalar")
    if not np.isfinite(point).all():
        raise ValueError("LOS model returned non-finite predictions")
    return pd.DataFrame({"los_point_days": point,
                         "los_lower_days": np.maximum(1.0, point - width),
                         "los_upper_days": point + width}, index=frame.index)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    args = parser.parse_args()
    print(json.dumps(fit_los_model(args.data, args.artifact), indent=2))
