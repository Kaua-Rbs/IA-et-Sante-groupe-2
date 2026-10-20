import pandas as pd

from optimiseur import data_bridge as db
from bridge_los import _filter_eda_by_horizon, EDA_PARQUET, LOS_PARQUET

los = pd.read_parquet(LOS_PARQUET)
if "split" not in los.columns:
    raise SystemExit(f"No 'split' column in {LOS_PARQUET}. Columns: {list(los.columns)}")

print("split values in the whole LOS dataset:")
print(los["split"].value_counts(dropna=False), "\n")

los["event_date"] = pd.to_datetime(los["split_event_date"]).dt.normalize()
keys = los[["split_patient_id", "event_date", "split"]].drop_duplicates(
    ["split_patient_id", "event_date"])

eda_all = db.load_preprocessed(EDA_PARQUET)
for horizon in (5, 30):
    eda = _filter_eda_by_horizon(eda_all, horizon).copy()
    eda["event_date"] = pd.to_datetime(eda["date_inter"]).dt.normalize()
    m = eda.merge(keys, left_on=["id_patient", "event_date"],
                  right_on=["split_patient_id", "event_date"], how="left")
    print(f"Horizon {horizon} days: {len(eda)} rows, dates "
          f"{eda['event_date'].min().date()} -> {eda['event_date'].max().date()}")
    print(m["split"].value_counts(dropna=False), "\n")