"""Explicit opt-in conversion of model outputs to S1/S2 planning inputs.

LOS predictions are inclusive TOTAL hospital days. Only preoperative days known
at the decision time may be subtracted. No capacities are inferred or extended.
"""
import numpy as np
import pandas as pd

from optimiseur.feasibility import FullStayPlanningProblem


def prediction_problem(patients, sessions, room_predictions, los_predictions,
                       bed_capacities, *, known_preop_days=None, los_risk="point",
                       room_risk="point", patient_options=None):
    """Return a new feasibility-first problem; preserve positional optimizer IDs.

    Conservative ceiling is explicit for minutes and inclusive days. The legacy
    bridges and default optimizer behavior are untouched. Callers must supply
    residual bed capacities after confirmed reservations through ALL discharges.
    """
    if room_risk not in ("point", "p80", "p95") or los_risk not in ("point", "upper"):
        raise ValueError("Unknown prediction risk")
    for frame in (patients, room_predictions, los_predictions):
        if not frame.index.is_unique or not frame.index.equals(patients.index):
            raise ValueError("Unique, explicitly aligned prediction indices required")
    minutes = pd.to_numeric(room_predictions[f"duration_{room_risk}_min"], errors="raise").to_numpy(float)
    total = pd.to_numeric(los_predictions[f"los_{los_risk}_days"], errors="raise").to_numpy(float)
    if known_preop_days is None:
        preop = np.zeros(len(patients))
    elif isinstance(known_preop_days, pd.Series) and known_preop_days.index.equals(patients.index):
        preop = known_preop_days.to_numpy(float)
    else:
        raise ValueError("Known preoperative days must be an aligned Series")
    if (not np.isfinite(minutes).all() or (minutes <= 0).any()
            or not np.isfinite(total).all() or (total < 1).any()
            or not np.isfinite(preop).all() or (preop < 0).any()
            or (preop != np.floor(preop)).any()):
        raise ValueError("Invalid duration, inclusive LOS or preoperative days")
    result = patients.copy()
    result["duree_operatoire"] = np.ceil(minutes)
    # Offset 0 occupies the operation day; inclusive postoperative days = offset+1.
    result["duree_sejour"] = np.maximum(1, np.ceil(total - preop)) - 1
    return FullStayPlanningProblem(result, sessions, bed_capacities,
        patient_options=patient_options, objective_mode="feasibility_first")
