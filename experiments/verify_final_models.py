"""Aggregate artifact, raw-inference and actual web-adapter smoke verification."""
import argparse
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import sys

import joblib
import numpy as np
import pandas as pd

from prediction.consultation_features import consultation_inputs
from prediction.duration_features import apply_category_mapping, engineer_features
from prediction.los_model import predict_los_loaded
from prediction.surgery_duration import predict_schedule_loaded
from prediction.prediction_planning import prediction_problem
from optimiseur.validation import validate_full_stay


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error("Output must be new or empty")
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root/"interface"))
    from api.ai.contracts import PredictionInput
    from api.ai.trained import TrainedRoomDurationPredictor, TrainedLOSPredictor
    probes = [PredictionInput(40, 1, "K40", ("LMMA009",), "GENERAL", "HERNIE"),
              PredictionInput(101, 2, "UNKNOWN", (), "GENERAL", None)]
    report = {"packages": {}, "artifacts": {}, "scope": "Real adapter classes tested; no HTTP/API database or booking integration"}
    for name in ("numpy", "pandas", "scikit-learn", "xgboost", "catboost", "joblib", "pyarrow", "mesa", "sqlmodel", "pydantic"):
        report["packages"][name] = importlib.metadata.version(name)
    for path in sorted(args.artifacts.glob("*.joblib")):
        room = path.name.startswith("room")
        saved = joblib.load(path)
        predict = predict_schedule_loaded if room else predict_los_loaded
        empty = predict(pd.DataFrame(index=[0,1]), saved, raw=True)
        if not np.isfinite(empty.to_numpy()).all():
            raise ValueError("Nonfinite all-missing inference")
        adapter = (TrainedRoomDurationPredictor if room else TrainedLOSPredictor)(path)
        adapter_results = [adapter.predict(inputs) for inputs in probes]
        if any(not np.isfinite(item.value) for item in adapter_results):
            raise ValueError("Nonfinite web adapter inference")
        report["artifacts"][path.name] = {"sha256":sha256(path.read_bytes()).hexdigest(),
            "all_missing_raw_finite":True, "actual_adapter_probes_passed":len(adapter_results),
            "unit":adapter_results[0].unit, "version":adapter.model_version}
    # Entire loaded-model -> explicit units/offsets -> S1/S2 -> independent
    # calendar validation path, using synthetic consultation inputs only.
    raw = pd.DataFrame({"age_years":[40,70], "sexe":[1,2], "interv_type":["HERNIE",None],
                        "cim_diag_pr":["K40",None], "ccam_1":["LMMA009",None]})
    room_saved = joblib.load(args.artifacts/"room_consultation_selected_2026-10-20_v1.joblib")
    los_saved = joblib.load(args.artifacts/"los_consultation_selected_2026-10-20_v1.joblib")
    room_predictions = predict_schedule_loaded(raw,room_saved,raw=True)
    los_predictions = predict_los_loaded(raw,los_saved,raw=True)
    patients = pd.DataFrame({"patient_id":["synthetic-1","synthetic-2"],"specialite":["GENERAL"]*2})
    sessions = pd.DataFrame({"vacation_id":["session-1","session-2"],"specialite":["GENERAL"]*2,
                             "jour":[0,1],"capacite_min":[1440,1440]})
    beds = [4]*60
    problem = prediction_problem(patients,sessions,room_predictions,los_predictions,beds,
                                 room_risk="p95",los_risk="upper")
    validation = validate_full_stay(problem.patients,sessions,beds,{0:0,1:1})
    if not validation.feasible:
        raise ValueError("Loaded-model S1/S2 synthetic integration failed")
    report["synthetic_s1s2_integration"] = {"valid":validation.valid,"feasible":validation.feasible,
        "patients":validation.assigned_cases,"explicit_bed_days":len(beds),
        "room_risk":"p95","los_risk":"upper","legacy_defaults_changed":False}
    # Independent calendar arithmetic verifies the learned LOS target convention.
    dataset = pd.read_parquet(args.source/"resources/model_los_dataset.parquet")
    eda = pd.read_parquet(args.source/"resources/donnees_bloc_pretraitees.parquet")
    left = dataset.assign(_patient=dataset.split_patient_id.astype("string"),
                          _day=pd.to_datetime(dataset.split_event_date).dt.normalize())
    right = eda.assign(_patient=eda.id_patient.astype("string"),
                       _day=pd.to_datetime(eda.date_inter).dt.normalize())
    keys=["_patient","_day"]
    if left.duplicated(keys).any() or right.duplicated(keys).any():
        raise ValueError("Ambiguous LOS raw-data match")
    joined=left[keys+["split","target_los_days"]].merge(right,on=keys,validate="one_to_one")
    admission=pd.to_datetime(joined.date_entree).dt.normalize()
    discharge=pd.to_datetime(joined.date_sortie).dt.normalize()
    inclusive=(discharge-admission).dt.days+1
    preop=(joined._day-admission).dt.days
    postop=(discharge-joined._day).dt.days+1
    agreement=np.isclose(joined.target_los_days,inclusive)
    identity=(inclusive-preop).eq(postop)
    if not agreement.all() or not identity.all() or (preop<0).any():
        raise ValueError("LOS inclusive/preoperative/postoperative identity failed")
    heldout=joined.loc[joined.split.eq("test")].reset_index(drop=True)
    reference=heldout[keys].merge(left,on=keys,validate="one_to_one")
    parity={}
    for name in ("los_consultation_selected_2026-10-20_v1.joblib",
                 "los_consultation_baseline_2026-10-20_v1.joblib",
                 "los_full_reproduction_2026-10-20_v1.joblib"):
        saved=joblib.load(args.artifacts/name)
        raw_point=predict_los_loaded(heldout,saved,raw=True).los_point_days.to_numpy()
        prepared_point=predict_los_loaded(reference,saved).los_point_days.to_numpy()
        difference=abs(raw_point-prepared_point)
        parity[name]={"n":len(difference),"max_abs_difference":float(difference.max())}
        if not np.allclose(raw_point,prepared_point,atol=1e-6):
            raise ValueError("LOS raw/prepared prediction mismatch")
    report["los_calendar_validation"]={"matched_rows":len(joined),
        "inclusive_target_agreement":float(agreement.mean()),"postoperative_identity_all":bool(identity.all()),
        "invalid_preoperative_rows":int((preop<0).sum()),"raw_prepared_parity":parity}
    # Tail diagnostics for fixed selected artifacts, not further model selection.
    for kind in ("room", "los"):
        frame = pd.read_parquet(args.source/f"resources/model_{'surgery_duration' if kind=='room' else 'los'}_dataset.parquet")
        test = frame.loc[frame.split.eq("test")]
        path = args.artifacts/f"{kind}_consultation_selected_2026-10-20_v1.joblib"
        saved = joblib.load(path)
        result = (predict_schedule_loaded if kind=="room" else predict_los_loaded)(test, saved)
        actual = test["target_surgery_duration_min" if kind=="room" else "target_los_days"].to_numpy(float)
        point = result["duration_point_min" if kind=="room" else "los_point_days"].to_numpy(float)
        tail = actual >= (120 if kind=="room" else 7)
        bounds = result.duration_p95_min.to_numpy() >= actual if kind=="room" else (
            (actual >= result.los_lower_days.to_numpy()) & (actual <= result.los_upper_days.to_numpy()))
        report[f"{kind}_tail"] = {"n":int(tail.sum()), "mae":float(abs(point[tail]-actual[tail]).mean()),
            "bias":float((point[tail]-actual[tail]).mean()), "coverage":float(bounds[tail].mean()),
            "underprediction_rate":float((point[tail]<actual[tail]).mean())}
    (args.output/"artifact_verification.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
