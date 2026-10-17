"""Evaluate saved models on held-out rows with fields available to KYST.

This is a sensitivity check on the preprocessed 2022 test split. It masks
features missing from the current consultation form; it is not prospective
validation and does not reproduce raw web entry or clinical deployment.
Only aggregate metrics and file fingerprints are emitted.
"""

import argparse
from hashlib import sha256
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from los_model import predict_los_loaded
from surgery_duration import predict_schedule_loaded


def _fingerprint(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _web_fields(frame: pd.DataFrame, *, keep_intervention_type: bool) -> pd.DataFrame:
    result = frame.copy()
    for column in ("anesth_type", "anesth_loco_reg", "praticien", "nom_chir"):
        result[column] = None
    if not keep_intervention_type:
        result["interv_type"] = None
    result["num_secondary_diagnoses"] = 0
    result["anesth_type_missing"] = 1
    result["anesth_loco_reg_missing"] = 1
    result["num_ccam_codes"] = pd.to_numeric(
        result["num_ccam_codes"], errors="coerce").clip(lower=1, upper=4)
    return result


def _scores(actual: np.ndarray, point: np.ndarray) -> dict:
    error = np.asarray(point, dtype=float) - actual
    if not np.isfinite(error).all():
        raise ValueError("Model returned non-finite predictions")
    return {
        "mae": round(float(np.mean(np.abs(error))), 4),
        "median_absolute_error": round(float(np.median(np.abs(error))), 4),
        "bias": round(float(np.mean(error)), 4),
    }


def evaluate(data: Path, artifact: Path, kind: str) -> dict:
    if kind not in ("room", "los"):
        raise ValueError("kind must be room or los")
    frame = pd.read_parquet(data)
    target = "target_surgery_duration_min" if kind == "room" else "target_los_days"
    required = {"split", target, "num_ccam_codes", "num_secondary_diagnoses",
                "anesth_type_missing", "anesth_loco_reg_missing", "interv_type",
                "anesth_type", "anesth_loco_reg", "praticien", "nom_chir"}
    if missing := required - set(frame):
        raise ValueError(f"Missing evaluation columns: {sorted(missing)}")
    heldout = frame.loc[frame["split"].eq("test")].copy()
    if heldout.empty or not np.isfinite(heldout[target]).all():
        raise ValueError("Held-out test split is empty or has invalid targets")
    saved = joblib.load(artifact)
    predict = predict_schedule_loaded if kind == "room" else predict_los_loaded
    point_column = "duration_point_min" if kind == "room" else "los_point_days"
    actual = heldout[target].to_numpy(dtype=float)
    variants = {
        "all_model_features": heldout,
        "web_fields_with_intervention_type": _web_fields(
            heldout, keep_intervention_type=True),
        "web_fields_without_intervention_type": _web_fields(
            heldout, keep_intervention_type=False),
    }
    results = {}
    for name, inputs in variants.items():
        prediction = predict(inputs, saved)
        scores = _scores(actual, prediction[point_column].to_numpy())
        if kind == "room" and "duration_p95_min" in prediction:
            scores["p95_upper_coverage"] = round(float(np.mean(
                actual <= prediction["duration_p95_min"].to_numpy())), 4)
        if kind == "los":
            scores["interval_coverage"] = round(float(np.mean(
                (actual >= prediction["los_lower_days"].to_numpy())
                & (actual <= prediction["los_upper_days"].to_numpy()))), 4)
        results[name] = scores
    return {
        "kind": kind, "heldout_rows": len(heldout),
        "dataset_sha256": _fingerprint(data), "artifact_sha256": _fingerprint(artifact),
        "metrics": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--room-data", type=Path, required=True)
    parser.add_argument("--los-data", type=Path, required=True)
    parser.add_argument("--room-model", type=Path, required=True)
    parser.add_argument("--los-model", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = {
        "interpretation": (
            "Held-out 2022 sensitivity check on preprocessed features; masking "
            "unavailable fields approximates KYST inputs and is not prospective validation."
        ),
        "room": evaluate(args.room_data, args.room_model, "room"),
        "los": evaluate(args.los_data, args.los_model, "los"),
    }
    output = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
