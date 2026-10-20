import argparse
import random
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

Q90 = 1.02          # conformal half-width (days), same as bridge_los.Q90
MODES = ["nominal", "upper"]   # instance used for *planning*

def los_center(patients: pd.DataFrame) -> np.ndarray:
    """Raw (unrounded) LOS prediction if available, else the rounded one."""
    col = "los_pred" if "los_pred" in patients.columns else "duree_sejour"
    return patients[col].to_numpy(dtype=float)


def sample_los(center: np.ndarray, n_scen: int, rng: np.random.Generator) -> np.ndarray:
    """(n_scen, n_patients) integer LOS matrix: symmetric uniform noise within
    the 90% conformal interval, floored at 1 day."""
    noise = rng.uniform(-Q90, Q90, size=(n_scen, len(center)))
    return np.rint(np.maximum(1.0, center + noise)).astype(int)


# Cost evaluation (mirrors PlanningProblem.fitness, but exposes components)
def cost_components(problem, solution: dict, sejour: np.ndarray | None = None) -> dict:
    """Cost and its three terms for `solution`, optionally under another LOS vector."""
    if sejour is not None:
        problem._pat_sejour = sejour
    pids = np.fromiter(solution.keys(), dtype=int, count=len(solution))
    vacs = np.fromiter(solution.values(), dtype=int, count=len(solution))

    charge = np.zeros(problem.n_vacations)
    np.add.at(charge, vacs, problem._pat_duree[pids])
    ov_vac = float(np.maximum(0, charge - problem._vac_capacity).sum())

    occ = problem._occupation(pids, vacs)
    ov_lits = float(np.maximum(0, occ - problem.lits_capacity).sum())

    balance = float(charge.std())
    cost = problem.w_vacation * ov_vac + problem.w_lits * ov_lits + problem.w_balance * balance
    return {"cost": cost, "ov_vac": ov_vac, "ov_lits": ov_lits, "balance": balance}


def evaluate_schedule(eval_problem, solution, scenarios, nominal_los) -> dict:
    """Nominal cost + Monte Carlo statistics of a frozen schedule."""
    nom = cost_components(eval_problem, solution, sejour=nominal_los)
    comps = [cost_components(eval_problem, solution, sejour=s) for s in scenarios]
    mc = np.array([c["cost"] for c in comps])
    eval_problem._pat_sejour = nominal_los  # restore
    last_days = eval_problem._vac_day[np.fromiter(solution.values(), dtype=int)]
    return {
        "nominal_cost": nom["cost"],
        "ov_vac": nom["ov_vac"],
        "ov_lits": nom["ov_lits"],
        "balance": nom["balance"],
        "mc_ov_vac": float(np.mean([c["ov_vac"] for c in comps])),
        "mc_ov_lits": float(np.mean([c["ov_lits"] for c in comps])),
        "mc_balance": float(np.mean([c["balance"] for c in comps])),
        "mc_mean": mc.mean(),
        "mc_std": mc.std(ddof=1),
        "mc_p95": np.percentile(mc, 95),
        "cost_increase": mc.mean() - nom["cost"],
        "pct_last5d": float((last_days >= eval_problem.n_days - 5).mean()),
    }


# Experiment
def run_scale(scale, patients, vacations, seeds, n_scen):
    from optimiseur.optimizer import PlanningProblem, optimize_planning

    eval_problem = PlanningProblem(patients, vacations)
    nominal_los = patients["duree_sejour"].to_numpy(dtype=int)
    center = los_center(patients)
    rows = []

    for seed in seeds:
        scen = sample_los(center, n_scen, np.random.default_rng(10_000 + seed))
        print(f"  [{scale}] seed={seed}: mean LOS nominal={nominal_los.mean():.2f} "
              f"| scenarios={scen.mean():.2f}")

        # Random-schedule baseline (is any method actually improving anything?)
        rand_sol = eval_problem.random_solution(random.Random(seed))
        rows.append({"scale": scale, "seed": seed, "mode": "baseline",
                     "method": "Random", "time_s": 0.0,
                     **evaluate_schedule(eval_problem, rand_sol, scen, nominal_los)})

        for mode in MODES:
            inst = patients.copy()
            if mode == "upper":
                inst["duree_sejour"] = patients["duree_sejour_upper"]
            results = optimize_planning(inst, vacations, seed=seed)
            plan_problem = PlanningProblem(inst, vacations)
            for name, res in results.items():
                sol = res.meilleure_solution
                rows.append({"scale": scale, "seed": seed, "mode": mode,
                             "method": name, "time_s": float(res.duree_s),
                             "planned_cost": cost_components(plan_problem, sol)["cost"],
                             **evaluate_schedule(eval_problem, sol, scen, nominal_los)})
            print(f"    {mode:8s} done")
    return rows


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["planned_cost", "nominal_cost", "mc_mean", "mc_p95", "cost_increase",
        "ov_vac", "ov_lits", "balance", "mc_ov_vac", "mc_ov_lits", "mc_balance",
        "pct_last5d", "time_s"]
    keys = ["scale", "mode", "method"]
    out = df.groupby(keys)[cols].mean().round(2)
    out["mc_mean_sd_seeds"] = df.groupby(keys)["mc_mean"].std().round(2)
    return out


def make_figure(df: pd.DataFrame, path: str):
    import matplotlib.pyplot as plt

    short = {"Recuit simule": "SA", "Tabou": "Tabu", "Genetique": "GA",
             "Tabou x Recuit": "Tabu+SA", "Fourmis (ACO)": "ACO", "Random": "Random"}
    scales = list(df["scale"].unique())
    fig, axes = plt.subplots(1, len(scales), figsize=(6.5 * len(scales), 4.5), squeeze=False)
    colors = {"baseline": "#999999", "nominal": "#4C78A8", "upper": "#F58518"}
    for ax, scale in zip(axes[0], scales):
        sub = df[df.scale == scale].copy()
        sub["m"] = sub["method"].map(short)
        order = ["Random", "SA", "Tabu", "Tabu+SA", "GA", "ACO"]
        mean = sub.groupby(["m", "mode"])["mc_mean"].mean().unstack().reindex(order)
        sd = sub.groupby(["m", "mode"])["mc_mean"].std().unstack().reindex(order)
        mean.plot(kind="bar", ax=ax, yerr=sd, capsize=3,
                  color=[colors[c] for c in mean.columns])
        ax.set_title(f"{scale}: expected cost of a frozen schedule (MC)")
        ax.set_ylabel("mean cost over LOS scenarios (lower = better)")
        ax.set_xlabel("")
        ax.legend(title="planned on")
    plt.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--scenarios", type=int, default=200)
    ap.add_argument("--out", default="results_mc.csv")
    ap.add_argument("--fig", default="figures/fig4_mc_robustness.png")
    args = ap.parse_args()

    from bridge_los import build_patients_with_uncertainty

    seeds = list(range(42, 42 + args.seeds))
    all_rows = []
    for scale, horizon in [("small", 5), ("large", 30)]:
        patients, vacations, ctx = build_patients_with_uncertainty(horizon_jours=horizon)
        print(f"\n=== {scale}: {len(patients)} patients, {len(vacations)} vacations, "
              f"match rate {ctx['match_rate']:.1%}")
        all_rows += run_scale(scale, patients, vacations, seeds, args.scenarios)

    df = pd.DataFrame(all_rows)
    df.to_csv(args.out, index=False)
    summ = summarize(df)
    summ.to_csv("results_mc_summary.csv")
    pd.set_option("display.width", 220)
    print("\n", summ)
    make_figure(df, args.fig)
    print(f"\nSaved: {args.out}, results_mc_summary.csv, {args.fig}")


if __name__ == "__main__":
    main()