import argparse

import numpy as np
import pandas as pd

from robustness_mc import evaluate_schedule, los_center, sample_los

CAPACITIES = [50, 42, 36, 30]     # beds; 42 is the group's default
LABEL = {50: "light", 42: "normal", 36: "overload", 30: "heavy overload"}


def run(patients, vacations, seeds, n_scen, capacities=CAPACITIES):
    from optimiseur.optimizer import (PlanningProblem, genetic_algorithm,
                                      simulated_annealing, tabu_search)

    n = len(patients)
    nominal_los = patients["duree_sejour"].to_numpy(dtype=int)
    center = los_center(patients)
    n_days = int(PlanningProblem(patients, vacations).n_days)
    rows = []
    for cap in capacities:
        prob = PlanningProblem(patients, vacations, lits_capacity=cap)
        # approximate bed-day demand / bed-day capacity (ignores end-of-horizon truncation)
        load = float((nominal_los + 1).sum() / (cap * n_days))
        planners = {
            "SA": lambda s: simulated_annealing(prob, seed=s),
            "Tabu": lambda s: tabu_search(prob, seed=s),
            "GA (p_mut=1/n)": lambda s: genetic_algorithm(prob, seed=s, p_mut=1 / n),
        }
        for seed in seeds:
            scen = sample_los(center, n_scen, np.random.default_rng(10_000 + seed))
            for name, plan in planners.items():
                sol = plan(seed).meilleure_solution
                rows.append({"capacity": cap, "regime": LABEL.get(cap, str(cap)),
                             "load_approx": round(load, 2), "seed": seed, "method": name,
                             **evaluate_schedule(prob, sol, scen, nominal_los)})
        print(f"capacity {cap} ({LABEL.get(cap, '')}) done")
    return pd.DataFrame(rows)


def make_figure(df, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    caps = sorted(df["capacity"].unique(), reverse=True)
    for m, mk in zip(df["method"].unique(), ["o", "s", "^"]):
        s = df[df.method == m].groupby("capacity")[["ov_vac", "ov_lits", "mc_ov_lits"]].mean().loc[caps]
        axes[0].plot(range(len(caps)), s["ov_vac"], marker=mk, label=m)
        axes[1].plot(range(len(caps)), s["ov_lits"], marker=mk, ls="-", label=f"{m} (point LOS)")
        axes[1].plot(range(len(caps)), s["mc_ov_lits"], marker=mk, ls="--", label=f"{m} (LOS scenarios)")
    ticks = [f"{c} beds\n{df[df.capacity == c]['regime'].iloc[0]}" for c in caps]
    for ax in axes:
        ax.set_xticks(range(len(caps)))
        ax.set_xticklabels(ticks, fontsize=8)
    axes[0].set_title("Operating-room overrun (min)")
    axes[1].set_title("Bed overrun (bed-days)")
    axes[1].legend(fontsize=7)
    plt.tight_layout()
    from pathlib import Path
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=150)
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--scenarios", type=int, default=200)
    ap.add_argument("--out", default="results_load.csv")
    ap.add_argument("--fig", default="figures/fig5_load_scenarios.png")
    args = ap.parse_args()

    from pathlib import Path
    from bridge_los import build_patients_with_uncertainty

    patients, vacations, _ = build_patients_with_uncertainty(horizon_jours=30)
    df = run(patients, vacations, list(range(42, 42 + args.seeds)), args.scenarios)
    df.to_csv(args.out, index=False)

    cols = ["load_approx", "nominal_cost", "ov_vac", "ov_lits", "mc_ov_lits", "mc_mean", "cost_increase"]
    summ = df.groupby(["capacity", "method"])[cols].mean().round(1)
    pd.set_option("display.width", 220)
    print("\n", summ)
    summ.to_csv("results_load_summary.csv")
    Path(args.fig).parent.mkdir(parents=True, exist_ok=True)
    make_figure(df, args.fig)
    print(f"\nSaved: {args.out}, results_load_summary.csv, {args.fig}")


if __name__ == "__main__":
    main()