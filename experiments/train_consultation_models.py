"""Bounded final models: fixed candidates, validation-only choice, aggregate output.

Reads authorized original Parquets without copying/exporting patient records.
New artifacts are private/untracked; existing models/results are never replaced.
"""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
from time import monotonic

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

from prediction.consultation_features import CONSULTATION_FEATURES, consultation_inputs
from prediction.duration_features import fit_category_mapping
from prediction.los_model import (_partitions, fit_los_model, predict_los_loaded)
from prediction.surgery_duration import (CAT, NUM, MedianBaseline, validate_split, prepared,
    preprocessing, calibration_split, conformal_offset, predict_schedule_loaded)

ROOT = Path(__file__).resolve().parents[1]


def fingerprint(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def metrics(actual, predicted, *, long_threshold):
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if not np.isfinite(predicted).all() or not np.isfinite(actual).all():
        raise ValueError("Nonfinite evaluation")
    error = predicted - actual
    long = actual >= long_threshold
    return {"n": len(actual), "mae": float(np.mean(abs(error))),
            "rmse": float(np.sqrt(np.mean(error ** 2))), "bias": float(np.mean(error)),
            "underprediction_rate": float(np.mean(error < 0)),
            "absolute_error_p95": float(np.quantile(abs(error), .95)),
            "long_threshold": long_threshold, "long_n": int(long.sum()),
            "long_mae": float(np.mean(abs(error[long]))) if long.any() else None,
            "long_bias": float(np.mean(error[long])) if long.any() else None,
            "long_underprediction_rate": float(np.mean(error[long] < 0)) if long.any() else None}


def masked_legacy(frame):
    # Match the deployed form's absent inputs, not a full-feature retrospective frame.
    out = frame.copy()
    for column in ("anesth_type", "anesth_loco_reg", "praticien", "nom_chir"):
        out[column] = None
    out["num_secondary_diagnoses"] = 0
    out["anesth_type_missing"] = out["anesth_loco_reg_missing"] = 1
    out["num_ccam_codes"] = pd.to_numeric(out["num_ccam_codes"]).clip(lower=1, upper=4)
    return out


def fit_task(kind, data_path, output, artifacts, rows):
    frame = pd.read_parquet(data_path)
    target = "target_surgery_duration_min" if kind == "room" else "target_los_days"
    train, validation, test = validate_split(frame) if kind == "room" else _partitions(frame)
    selection, calibration = calibration_split(validation)
    columns = CONSULTATION_FEATURES
    frames = [prepared(part, columns) for part in (train, selection, calibration, test)]
    X, V, C, T = frames
    y, vy = train[target].to_numpy(float), selection[target].to_numpy(float)
    candidates = []
    for name, group in (("global_median", ()), ("intervention_median", ("interv_type",)),
                         ("procedure_median", ("ccam_1",))):
        model = MedianBaseline(group).fit(X, y)
        candidates.append((name, model, False, 0.0))
    if kind == "room":
        for name, loss, log in (("consult_HGB_log", "squared_error", True),
                                 ("consult_HGB_absolute", "absolute_error", False)):
            start = monotonic()
            model = make_pipeline(preprocessing(columns=columns, ordinal=True),
                HistGradientBoostingRegressor(loss=loss, max_iter=200, max_leaf_nodes=15,
                    categorical_features=list(range(1, len(columns))), early_stopping=False, random_state=42))
            model.fit(X, np.log1p(y) if log else y)
            candidates.append((name, model, log, monotonic() - start))
    else:
        start = monotonic()
        prep = ColumnTransformer([
            ("numeric", SimpleImputer(strategy="median"), ["age_years"]),
            ("categorical", OneHotEncoder(handle_unknown="ignore", min_frequency=10), [c for c in columns if c in CAT])])
        model = make_pipeline(prep, XGBRegressor(objective="reg:squarederror", n_estimators=400,
            max_depth=5, learning_rate=.04, subsample=.9, colsample_bytree=.9, reg_lambda=5,
            n_jobs=4, random_state=42, tree_method="hist"))
        model.fit(X, np.log1p(y))
        candidates.append(("consult_XGB_log", model, True, monotonic() - start))
    def point(model, features, log):
        prediction = model.predict(features)
        return np.maximum(1.0, np.expm1(prediction) if log else prediction)
    # Freeze both ML and baseline choices before examining the test outcomes.
    scores = {name: float(mean_absolute_error(vy, point(model, V, log)))
              for name, model, log, _ in candidates}
    ml = min((c for c in candidates if c[0].startswith("consult_")), key=lambda c: (scores[c[0]], c[0]))
    baseline = min((c for c in candidates if not c[0].startswith("consult_")), key=lambda c: (scores[c[0]], c[0]))
    mapping = fit_category_mapping(X, [c for c in columns if c in CAT], min_count=1)
    selected_artifacts = {}
    for choice, (name, model, log, seconds) in (("selected", ml), ("baseline", baseline)):
        saved = {"model": model, "features": columns, "category_mapping": mapping,
                 "artifact_version": 3, "name": name, "log_target": log, "calendar": False,
                 "dataset_sha256": fingerprint(data_path), "feature_contract": "consultation-v1",
                 "protocol": "train only fit; early 2021 selection; disjoint later 2021 calibration; 2022 report"}
        cp = point(model, C, log)
        actual_c = calibration[target].to_numpy(float)
        if kind == "room":
            saved["bounds"] = {label: {"base": "point", "offset": conformal_offset(actual_c, cp, level),
                "coverage": level, "method": "one_sided_split_conformal"}
                for label, level in (("p80", .8), ("p95", .95))}
        else:
            rank = int(np.ceil((len(cp) + 1) * .9))
            if rank > len(cp):
                raise ValueError("Insufficient LOS calibration")
            saved["interval_half_width_days"] = float(np.sort(abs(actual_c - cp))[rank - 1])
        artifact = artifacts / f"{kind}_consultation_{choice}_2026-10-20_v1.joblib"
        if artifact.exists():
            raise FileExistsError("Refusing to overwrite model")
        joblib.dump(saved, artifact)
        loaded = joblib.load(artifact)
        predict = predict_schedule_loaded if kind == "room" else predict_los_loaded
        final = predict(T, loaded)
        expected = point(model, T, log)
        col = "duration_point_min" if kind == "room" else "los_point_days"
        if not np.allclose(final[col], expected, rtol=1e-6):
            raise RuntimeError("Artifact reload changed predictions; no patient values are logged")
        selected_artifacts[choice] = {"filename": artifact.name, "sha256": fingerprint(artifact), "name": name}
        if choice == "selected":
            if kind == "room":
                coverage = {label: float(np.mean(test[target].to_numpy() <= final[f"duration_{label}_min"])) for label in ("p80", "p95")}
            else:
                coverage = {"interval_90": float(np.mean((test[target].to_numpy() >= final.los_lower_days)
                                               & (test[target].to_numpy() <= final.los_upper_days)))}
    for name, model, log, seconds in candidates:
        for partition, features, actual in (("selection", V, vy), ("test", T, test[target].to_numpy(float))):
            rows.append({"kind": kind, "model": name, "partition": partition,
                "selected_ML": name == ml[0], "selected_baseline": name == baseline[0],
                "training_seconds": seconds, **metrics(actual, point(model, features, log),
                    long_threshold=120 if kind == "room" else 7)})
    return {"kind": kind, "splits": {n: len(p) for n, p in zip(("train", "selection", "calibration", "test"),
                 (train, selection, calibration, test))}, "selection_mae": scores,
            "selected_model": ml[0], "selected_baseline": baseline[0],
            "artifact": selected_artifacts, "test_coverage_selected": coverage,
            "features": columns, "fit_patient_disjointness_checked": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    for directory in (args.output, args.artifacts):
        directory.mkdir(parents=True, exist_ok=True)
        if any(directory.iterdir()):
            raise ValueError("New/empty output and artifact directories required")
    source = args.source
    paths = {"room_data": source / "resources/model_surgery_duration_dataset.parquet",
             "los_data": source / "resources/model_los_dataset.parquet",
             "old_room": source / "results/surgery_duration_model.joblib"}
    manifest = {"protocol": "final-consultation-v1", "python": platform.python_version(),
                "input_sha256": {name: fingerprint(path) for name, path in paths.items()},
                "source_sha256": {name: fingerprint(ROOT / name) for name in ("prediction/surgery_duration.py",
                    "prediction/duration_features.py", "prediction/los_model.py", "prediction/consultation_features.py", "experiments/train_consultation_models.py")},
                "candidate_policy": "Two fixed existing HGB loss variants for room, fixed existing XGB recipe for LOS; validation-only selection; no test-driven iterations",
                "confidentiality": "No patient rows, identifiers, per-case predictions or real schedules are exported"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    rows, reports = [], {}
    for kind in ("room", "los"):
        print(f"training {kind}", flush=True)
        reports[kind] = fit_task(kind, paths[f"{kind}_data"], args.output, args.artifacts, rows)
        pd.DataFrame(rows).to_csv(args.output / "model_metrics.csv", index=False)
        (args.output / "report.json").write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
        print(f"finished {kind}: {reports[kind]['selected_model']}", flush=True)
    # Reproduce the supplied newer full-feature LOS implementation, not the old legacy bridge model.
    legacy_los_path = args.artifacts / "los_full_reproduction_2026-10-20_v1.joblib"
    full_los = fit_los_model(paths["los_data"], legacy_los_path)
    reports["los_full_reproduction"] = full_los
    old_room = joblib.load(paths["old_room"])
    frame = pd.read_parquet(paths["room_data"])
    heldout = frame.loc[frame.split.eq("test")]
    for name, inputs in (("existing_full_features", heldout), ("existing_web_masked", masked_legacy(heldout))):
        prediction = predict_schedule_loaded(inputs, old_room)
        score = metrics(heldout.target_surgery_duration_min, prediction.duration_point_min, long_threshold=120)
        score["p95_coverage"] = float(np.mean(heldout.target_surgery_duration_min.to_numpy() <= prediction.duration_p95_min))
        reports[name] = score
    los_frame = pd.read_parquet(paths["los_data"])
    los_test = los_frame.loc[los_frame.split.eq("test")]
    full_saved = joblib.load(legacy_los_path)
    los_masked = predict_los_loaded(masked_legacy(los_test), full_saved)
    reports["los_full_web_masked"] = metrics(los_test.target_los_days, los_masked.los_point_days, long_threshold=7)
    reports["los_full_web_masked"]["interval_coverage"] = float(np.mean((los_test.target_los_days.to_numpy() >= los_masked.los_lower_days)
                                                                         & (los_test.target_los_days.to_numpy() <= los_masked.los_upper_days)))
    # Probe realistic missing consultation input without refitting or selecting on the test.
    for kind in ("room", "los"):
        test = pd.read_parquet(paths[f"{kind}_data"])
        test = test.loc[test.split.eq("test")].copy()
        test["interv_type"] = "__MISSING__"
        model = joblib.load(args.artifacts / reports[kind]["artifact"]["selected"]["filename"])
        pred = predict_schedule_loaded(test, model) if kind == "room" else predict_los_loaded(test, model)
        reports[f"{kind}_consultation_no_intervention_type"] = metrics(
            test["target_surgery_duration_min" if kind == "room" else "target_los_days"],
            pred["duration_point_min" if kind == "room" else "los_point_days"], long_threshold=120 if kind == "room" else 7)
    (args.output / "report.json").write_text(json.dumps(reports, indent=2) + "\n", encoding="utf-8")
    manifest.update(status="complete", artifact_sha256={p.name: fingerprint(p) for p in args.artifacts.iterdir() if p.is_file()},
                    output_sha256={p.name: fingerprint(p) for p in args.output.iterdir() if p.is_file() and p.name != "manifest.json"})
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(reports, indent=2), flush=True)


if __name__ == "__main__":
    main()
