import argparse

import joblib
import numpy as np
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--parquet", default="resources/model_los_dataset.parquet")
ap.add_argument("--model", default="models/los_regressor.joblib")
ap.add_argument("--q", type=float, default=1.02, help="half-width of the interval (days)")
args = ap.parse_args()

los = pd.read_parquet(args.parquet)
model = joblib.load(args.model)
targets = [c for c in los.columns if c.startswith("target_")]
print("target columns:", targets)
print(los[targets].describe().T.round(3).to_string(), "\n")

X = los.drop(columns=targets + ["split"], errors="ignore")  # same as bridge_los._predict_los
pred_log = np.asarray(model.predict(X), dtype=float)
pred_days = np.expm1(pred_log).clip(1, None)


def r2(y, p):
    return 1 - ((y - p) ** 2).sum() / ((y - y.mean()) ** 2).sum()


rows = []
for t in targets:
    y = los[t].astype(float).to_numpy()
    for reading, y_days in [("target = days", y), ("target = log1p(days)", np.expm1(y))]:
        for sp in ["train", "validation", "test"]:
            m = (los["split"] == sp).to_numpy() & np.isfinite(y_days)
            if m.sum() == 0:
                continue
            err = np.abs(y_days[m] - pred_days[m])
            rows.append({"target": t, "reading": reading, "split": sp, "n": int(m.sum()),
                         "MAE_days": err.mean(), "R2_days": r2(y_days[m], pred_days[m]),
                         "R2_log": r2(np.log1p(y_days[m]), pred_log[m]),
                         f"coverage_{args.q}": (err <= args.q).mean()})
print(pd.DataFrame(rows).round(3).to_string(index=False))
print("\nReported: test MAE 0.412 d, R2 0.789, coverage 89.4 %, interval +-1.02 d.")
print("Ignore binary / classification targets. Read the 'test' row of the (target, reading)")
print("pair that gives plausible stays in days.")