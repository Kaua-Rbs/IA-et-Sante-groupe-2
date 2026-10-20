"""Conservative consultation-time contract shared by bounded model experiments.

No actual surgery date, admission/discharge, anesthesia, staff names, secondary
diagnosis counts or additional procedure counts are consumed. Principal CCAM,
diagnosis and planned intervention type are assumed known under the project
contract; this is not confirmation of hospital-wide availability.
"""
import numpy as np
import pandas as pd

from prediction.duration_features import engineer_features

CONSULTATION_FEATURES = ["age_years", "sexe", "interv_type", "cim_diag_pr",
                         "cim_diag_family", "ccam_1", "ccam_1_family"]
RAW_CONSULTATION_FIELDS = ["age_years", "sexe", "interv_type", "cim_diag_pr", "ccam_1"]


def consultation_inputs(raw):
    """Whitelist raw available fields; preserve index and explicit missingness."""
    return pd.DataFrame({name: raw.get(name, pd.Series(
        np.nan if name == "age_years" else None, index=raw.index,
        dtype=float if name == "age_years" else object)) for name in RAW_CONSULTATION_FIELDS}, index=raw.index)


def consultation_features(raw):
    return engineer_features(consultation_inputs(raw), CONSULTATION_FEATURES)
