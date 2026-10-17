import numpy as np
import pandas as pd
from optimiseur import data_bridge as db
from los_model import DEFAULT_ARTIFACT as LOS_ARTIFACT, predict_los
from surgery_duration import predict_schedule

K_HIGH = 4
EDA_PARQUET = "resources/donnees_bloc_pretraitees.parquet"
LOS_PARQUET = "resources/model_los_dataset.parquet"
LOS_MODEL_PATH = LOS_ARTIFACT
ROOM_MODEL_PATH = "artifacts/ml-models/surgery_duration_model.joblib"

def _filter_eda_by_horizon(eda, horizon_jours):
    if "date_inter" not in eda.columns:
        return eda.reset_index(drop=True).copy()
    eda = eda.dropna(subset=["date_inter"]).copy()
    eda["_date_norm"] = pd.to_datetime(eda["date_inter"]).dt.normalize()
    dates = sorted(eda["_date_norm"].unique())
    keep = set(dates[-horizon_jours:])
    out = eda[eda["_date_norm"].isin(keep)].reset_index(drop=True)
    out = out.drop(columns=["_date_norm"])
    return out

def _predict_los(parquet_path, model_path):
    los_df = pd.read_parquet(parquet_path)
    return los_df, predict_los(los_df, model_path)

def _find_merge_keys(eda, los_df):
    id_candidates = [c for c in ["no_cas", "id_patient"] if c in eda.columns]
    date_candidates = [c for c in ["date_inter"] if c in eda.columns]
    los_id = "split_patient_id"
    los_date = "split_event_date"

    best = (None, None, 0.0)
    for id_col in id_candidates:
        eda_ids = set(eda[id_col].astype(str).unique())
        los_ids = set(los_df[los_id].astype(str).unique())
        m = len(eda_ids & los_ids) / max(len(eda_ids), 1)
        if m > best[2]:
            best = (id_col, None, m)
    return best[0], best[1], best[2]

def build_patients_with_uncertainty(
    parquet_path=EDA_PARQUET,
    los_parquet=LOS_PARQUET,
    los_model_path=LOS_MODEL_PATH,
    room_model_path=ROOM_MODEL_PATH,
    horizon_jours=5,
    capacite_min=480,
    max_specialites=6,
):
    # EDA + replicate bridge's horizon filter
    eda = db.load_preprocessed(parquet_path)
    eda_filt = _filter_eda_by_horizon(eda, horizon_jours)
    print(f"[diag] EDA filtered: {len(eda_filt)} rows")

    # Predict LOS on the full LOS dataset (has all engineered features)
    los_df, los_predictions = _predict_los(los_parquet, los_model_path)

    # Find merge key between EDA and LOS
    id_col, _, match = _find_merge_keys(eda_filt, los_df)
    print(f"[diag] Best EDA id key = '{id_col}' with {match:.1%} id-overlap")

    if id_col is None or match < 0.1:
        raise RuntimeError(
            "Could not find a matching key between EDA and LOS datasets. "
            f"EDA cols: {list(eda_filt.columns)} | "
            f"LOS cols: {list(los_df.columns)}"
        )

    # Build LOS lookup with the matched key
    lookup = pd.DataFrame({
        "patient_id_key": los_df["split_patient_id"].values,
        "event_date": pd.to_datetime(los_df["split_event_date"]).dt.normalize().values,
        "pred": los_predictions["los_point_days"].to_numpy(),
        "lower": los_predictions["los_lower_days"].to_numpy(),
        "upper": los_predictions["los_upper_days"].to_numpy(),
    })

    # Predict per (id, date). If multiple rows per key, aggregate mean.
    lookup_agg = lookup.groupby(["patient_id_key", "event_date"], as_index=False)[
        ["pred", "lower", "upper"]].mean()
    print(f"[diag] LOS lookup: {len(lookup_agg)} unique (id,date) pairs")

    # Merge with EDA-filtered
    eda_filt = eda_filt.copy()
    eda_filt["patient_id_key"] = eda_filt[id_col]
    if "date_inter" in eda_filt.columns:
        eda_filt["event_date"] = pd.to_datetime(eda_filt["date_inter"]).dt.normalize()
    else:
        eda_filt["event_date"] = pd.NaT

    merged = eda_filt.merge(lookup_agg, on=["patient_id_key", "event_date"], how="left")
    match_rate = merged["pred"].notna().mean()
    print(f"[diag] Row-level match rate: {match_rate:.1%}")
    if not np.isfinite(match_rate) or match_rate == 0:
        raise ValueError("No LOS predictions match the selected EDA cases")

    # Fallback for unmatched rows: use the global median
    median_pred = float(np.nanmedian(merged["pred"]))
    if np.isnan(median_pred):
        median_pred = 3.0
    for column in ("pred", "lower", "upper"):
        merged[column] = merged[column].fillna(
            float(np.nanmedian(merged[column])) if merged[column].notna().any() else median_pred)

    # The model's target is total admission-to-discharge LOS. Vacation capacity
    # starts on the operation day, so subtract days already spent in hospital.
    if "date_entree" not in merged:
        raise ValueError("Admission date is required for postoperative bed demand")
    admission = pd.to_datetime(merged["date_entree"], errors="coerce").dt.normalize()
    elapsed = (merged["event_date"] - admission).dt.days
    if elapsed.isna().any() or elapsed.lt(0).any():
        raise ValueError("Admission must be known and no later than the intervention")
    for column in ("pred", "lower", "upper"):
        merged[column] = (merged[column] - elapsed).clip(lower=1)

    # rebuild in the right order (build_patients uses the original df indices)
    # simpler: build directly
    from optimiseur.data_bridge import derive_specialite
    specialite = derive_specialite(merged, None, max_specialites)

    # Both scheduling durations are predictions. Observed room occupancy and
    # LOS in the EDA frame remain unavailable to the optimizer.
    room = predict_schedule(merged, room_model_path, raw=True)
    dur = np.ceil(room["duration_point_min"].to_numpy()).astype(int)

    patients = pd.DataFrame({
        "patient_id": np.arange(len(merged)),
        "specialite": specialite.to_numpy(),
        "duree_operatoire": dur,
        "duree_sejour": merged["pred"].round().astype(int).values,
        "duree_sejour_lower": merged["lower"].clip(lower=1).round().astype(int).values,
        "duree_sejour_upper": np.ceil(merged["upper"]).astype(int).values,
        "risk_level": np.where(merged["pred"].values > K_HIGH, "HIGH", "LOW"),
        "los_pred": merged["pred"].values,
    })

    # Vacations (same as the group)
    specialites = sorted(patients["specialite"].dropna().unique().tolist())
    vacations = db.build_vacations(specialites, n_days=horizon_jours, capacite_min=capacite_min)

    context = {
        "n_patients": len(patients),
        "n_vacations": len(vacations),
        "specialites": specialites,
        "horizon_jours": horizon_jours,
        "match_rate": float(match_rate),
        "median_pred": median_pred,
    }
    return patients, vacations, context

def sample_stochastic(patients, rng):
    out = patients.copy()
    out["duree_sejour"] = rng.integers(
        out["duree_sejour_lower"], out["duree_sejour_upper"] + 1
    )
    return out

if __name__ == "__main__":
    patients, vacations, context = build_patients_with_uncertainty()
    print(f"\nPatients: {len(patients)}, Vacations: {len(vacations)}")
    print(f"Match rate: {context['match_rate']:.1%}")
    print(patients[["duree_sejour", "duree_sejour_lower",
                    "duree_sejour_upper"]].describe().round(2))
    print("\nRisk distribution:")
    print(patients["risk_level"].value_counts())
    print("\nSpecialty distribution:")
    print(patients["specialite"].value_counts())
    patients.to_parquet("resources/patients_with_uncertainty.parquet")
    print("\nSaved: resources/patients_with_uncertainty.parquet")
