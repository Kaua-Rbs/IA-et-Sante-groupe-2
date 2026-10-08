import numpy as np, pandas as pd
from robustness_mc import sample_los, los_center, evaluate_schedule
from bridge_los import build_patients_with_uncertainty
from optimiseur.optimizer import PlanningProblem, optimize_planning

patients, vacations, _ = build_patients_with_uncertainty(horizon_jours=30)
ev = PlanningProblem(patients, vacations)
nom = patients["duree_sejour"].to_numpy(dtype=int)
ctr = los_center(patients)
rows = []
for seed in range(42, 52):
    scen = sample_los(ctr, 200, np.random.default_rng(10_000 + seed))
    for mode in ["nominal", "upper"]:
        inst = patients.copy()
        if mode == "upper":
            inst["duree_sejour"] = patients["duree_sejour_upper"]
        res = optimize_planning(inst, vacations, seed=seed,
                                ga_kwargs={"p_mut": 1 / len(patients)})["Genetique"]
        rows.append({"seed": seed, "mode": mode, "p_mut": 1 / len(patients),
                     **evaluate_schedule(ev, res.meilleure_solution, scen, nom)})
        print(seed, mode, "done")
pd.DataFrame(rows).to_csv("results_ga_sensitivity.csv", index=False)