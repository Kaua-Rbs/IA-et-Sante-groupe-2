import numpy as np
from bridge_los import build_patients_with_uncertainty
from optimiseur.optimizer import PlanningProblem
import pandas as pd
from robustness_mc import sample_los, los_center

patients, vacations, _ = build_patients_with_uncertainty(horizon_jours=30)
p = PlanningProblem(patients, vacations)
D, K = p._pat_duree.sum(), p._vac_capacity.sum()
print("demanda total:", D, "| capacidad total:", K, "| cota global ov_vac >=", max(0, D - K))
D = patients.groupby("specialite")["duree_operatoire"].sum()
K = vacations.groupby("specialite")["capacite_min"].sum().reindex(D.index)
lb = (D - K).clip(lower=0)
print(pd.DataFrame({"demand": D, "capacity": K, "overflow_lb": lb}))
print("per-specialty lower bound on ov_vac:", lb.sum(), "| SA/Tabu ov_vac ~ 1038")
print("per-patient excess (>480 min):",
      (patients["duree_operatoire"] - 480).clip(lower=0).sum())

nom = patients["duree_sejour"].to_numpy()
scen = sample_los(los_center(patients), 200, np.random.default_rng(10_042))
print("bed-days nominal:", (nom + 1).sum(), "| MC mean:", (scen + 1).sum(axis=1).mean(),
      "| capacity:", p.lits_capacity * p.n_days)