import argparse
import random
import time
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

Q90 = 1.02
NOISES = ["floor", "symmetric"]
TRACKINGS = ["trunc", "full"]
PLANNING_MODES = ["nominal", "upper"]


def los_center(patients):
    col = "los_pred" if "los_pred" in patients.columns else "duree_sejour"
    return patients[col].to_numpy(dtype=float)


def sample_floor(center, n_scen, rng, q=Q90):
    noise = rng.uniform(-q, q, size=(n_scen, len(center)))
    return np.rint(np.maximum(1.0, center + noise)).astype(int)


def sample_symmetric(center, n_scen, rng, q=Q90):
    h = np.minimum(q, np.maximum(center - 1.0, 0.0))
    x = center + rng.uniform(-1.0, 1.0, size=(n_scen, len(center))) * h
    lo = np.floor(x)
    up = rng.random(x.shape) < (x - lo)
    return (lo + up).astype(int)


def arrays(sol):
    pids = np.fromiter(sol.keys(), dtype=int, count=len(sol))
    vacs = np.fromiter(sol.values(), dtype=int, count=len(sol))
    return pids, vacs


def block_terms(problem, pids, vacs):
    charge = np.zeros(problem.n_vacations)
    np.add.at(charge, vacs, problem._pat_duree[pids])
    ov_vac = float(np.maximum(0, charge - problem._vac_capacity).sum())
    return ov_vac, float(charge.std())


def bed_overrun(problem, pids, vacs, sejour, full):
    day0 = problem._vac_day[vacs]
    end = day0 + sejour[pids] + 1
    horizon = problem.n_days + (int(sejour.max()) + 1 if full else 0)
    delta = np.zeros(horizon + 1)
    np.add.at(delta, day0, 1)
    np.add.at(delta, np.minimum(end, horizon), -1)
    occ = np.cumsum(delta[:-1])
    return float(np.maximum(0, occ - problem.lits_capacity).sum())


def evaluate(problem, sol, nominal, scen_by_noise):
    pids, vacs = arrays(sol)
    ov_vac, bal = block_terms(problem, pids, vacs)
    fixed = problem.w_vacation * ov_vac + problem.w_balance * bal
    rows = []
    for trk in TRACKINGS:
        full = trk == "full"
        ob_nom = bed_overrun(problem, pids, vacs, nominal, full)
        c_nom = fixed + problem.w_lits * ob_nom
        for noise, scen in scen_by_noise.items():
            ob = np.array([bed_overrun(problem, pids, vacs, s, full) for s in scen])
            costs = fixed + problem.w_lits * ob
            rows.append({
                "tracking": trk, "noise": noise, "ov_vac": ov_vac, "balance": bal,
                "ov_lits": ob_nom, "nominal_cost": c_nom,
                "mc_ov_lits": ob.mean(), "mc_mean": costs.mean(),
                "mc_std": costs.std(ddof=1), "mc_p95": np.percentile(costs, 95),
                "cost_increase": costs.mean() - c_nom,
                "mean_los_nominal": float(nominal.mean()), "mean_los_scen": float(scen.mean()),
            })
    return rows


def lower_bound_vac(patients, vacations):
    D = patients.groupby("specialite")["duree_operatoire"].sum()
    K = vacations.groupby("specialite")["capacite_min"].sum().reindex(D.index).fillna(0)
    cmax = vacations.groupby("specialite")["capacite_min"].max()
    exc = (patients["duree_operatoire"] - patients["specialite"].map(cmax).fillna(0)).clip(lower=0)
    per_pat = exc.groupby(patients["specialite"]).sum().reindex(D.index).fillna(0)
    return float(np.maximum((D - K).clip(lower=0), per_pat).sum())


# resources
def make_vacations(vac, patients, k, bloc_load):
    n_days = int(vac["jour"].max()) + 1
    slots = vac[["jour", "specialite"]].drop_duplicates().reset_index(drop=True)
    if bloc_load is None:
        cap_day = float(vac.groupby(["jour", "specialite"])["capacite_min"].sum().median())
    else:
        dmax = patients.groupby("specialite")["duree_operatoire"].sum().max()
        cap_day = max(5.0, round(dmax / (n_days * bloc_load) / 5.0) * 5.0)
    out = slots.loc[slots.index.repeat(k)].reset_index(drop=True)
    out["capacite_min"] = cap_day / k
    out.insert(0, "vacation_id", range(len(out)))
    return out, cap_day


def filter_matched(patients, ctx):
    if "matched" in patients.columns:
        m = patients["matched"].to_numpy(dtype=bool)
    else:
        print("[warn] no 'matched' column: using the median-fallback heuristic")
        m = ~np.isclose(patients["los_pred"].to_numpy(), ctx["median_pred"])
    print(f"[matched-only] keeping {m.sum()} of {len(m)} patients")
    return patients[m].reset_index(drop=True)


# campaign
def make_planners(n, with_ga_default, with_aco):
    from optimiseur.optimizer import (ant_colony_optimization, genetic_algorithm,
                                      simulated_annealing, tabu_search,
                                      tabu_simulated_annealing)
    pl = {
        "SA": lambda p, s: simulated_annealing(p, seed=s),
        "Tabu": lambda p, s: tabu_search(p, seed=s),
        "Tabu+SA": lambda p, s: tabu_simulated_annealing(p, seed=s),
        "GA (p_mut=1/n)": lambda p, s: genetic_algorithm(p, seed=s, p_mut=1.0 / n),
    }
    if with_ga_default:
        pl["GA (default)"] = lambda p, s: genetic_algorithm(p, seed=s)
    if with_aco:
        pl["ACO"] = lambda p, s: ant_colony_optimization(p, seed=s)
    return pl


def run_instance(patients, vacations, meta, seeds, n_scen, beds, with_ga_default, with_aco):
    from optimiseur.optimizer import PlanningProblem

    ev = PlanningProblem(patients, vacations, lits_capacity=beds)
    nominal = patients["duree_sejour"].to_numpy(dtype=int)
    center = los_center(patients)
    n = len(patients)
    lb_min = lower_bound_vac(patients, vacations)
    planners = make_planners(n, with_ga_default, with_aco)
    rows = []
    for seed in seeds:
        scen = {"floor": sample_floor(center, n_scen, np.random.default_rng(10_000 + seed)),
                "symmetric": sample_symmetric(center, n_scen, np.random.default_rng(20_000 + seed))}
        if seed == seeds[0]:
            print(f"  mean LOS: nominal {nominal.mean():.2f} | floor {scen['floor'].mean():.2f}"
                  f" | symmetric {scen['symmetric'].mean():.2f} | OR lower bound {lb_min:.0f} min")
        base = {**meta, "seed": seed, "lb_vac_cost": ev.w_vacation * lb_min}
        rand = ev.random_solution(random.Random(seed))
        for r in evaluate(ev, rand, nominal, scen):
            rows.append({**base, "mode": "baseline", "method": "Random", "time_s": 0.0,
                         "planned_cost": np.nan, **r})
        for mode in PLANNING_MODES:
            inst = patients.copy()
            if mode == "upper":
                inst["duree_sejour"] = patients["duree_sejour_upper"]
            plan = PlanningProblem(inst, vacations, lits_capacity=beds)
            for name, fn in planners.items():
                res = fn(plan, seed)
                for r in evaluate(ev, res.meilleure_solution, nominal, scen):
                    rows.append({**base, "mode": mode, "method": name,
                                 "time_s": float(res.duree_s),
                                 "planned_cost": -float(res.meilleure_fitness), **r})
        print(f"  seed {seed} done")
    return rows


def summarize(df):
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 50)
    keys = ["scale", "regime"]
    nom = df[(df["mode"] == "nominal")]

    print("\n[1] Cost increase under LOS scenarios (planned on point LOS), mean over seeds")
    t1 = nom.groupby(keys + ["method", "noise", "tracking"])["cost_increase"].mean()
    print(t1.unstack(["noise", "tracking"]).round(0).to_string())

    print("\n[2] Mean LOS: nominal vs scenarios")
    t2 = df.drop_duplicates(keys + ["noise"]).set_index(keys + ["noise"])[["mean_los_nominal", "mean_los_scen"]]
    print(t2.round(2).to_string())

    print("\n[3] Paired change in expected cost, upper-bound minus point planning (mean +- s.e. over seeds)")
    p = df[df["mode"].isin(["nominal", "upper"])].pivot_table(
        index=keys + ["method", "noise", "tracking", "seed"], columns="mode", values="mc_mean")
    d = (p["upper"] - p["nominal"]).groupby(keys + ["method", "noise", "tracking"])
    t3 = pd.DataFrame({"delta": d.mean(), "se": d.std() / np.sqrt(d.count())}).round(1)
    print(t3.to_string())

    print("\n[4] Gap to the OR lower bound (planned on point LOS, truncated tracking)")
    g = nom[(nom["tracking"] == "trunc") & (nom["noise"] == "floor")].copy()
    g["gap_%"] = (g["nominal_cost"] / g["lb_vac_cost"] - 1) * 100
    print(g.groupby(keys + ["method"])[["nominal_cost", "ov_vac", "ov_lits", "gap_%", "time_s"]]
          .mean().round(1).to_string())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", nargs="+", default=["large"], choices=["small", "large"])
    ap.add_argument("--seeds", type=int, default=10)
    ap.add_argument("--scenarios", type=int, default=200)
    ap.add_argument("--beds", type=int, default=42)
    ap.add_argument("--vac-split", type=int, default=1, help="vacations per specialty-day (campagne v2: 2)")
    ap.add_argument("--bloc-load", type=float, nargs="*", default=None,
                    help="bottleneck-specialty demand/capacity, e.g. 0.80 0.93 0.98 1.10")
    ap.add_argument("--matched-only", action="store_true")
    ap.add_argument("--with-ga-default", action="store_true")
    ap.add_argument("--with-aco", action="store_true")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--out", default="results_los_v3.csv")
    args = ap.parse_args()

    from bridge_los import build_patients_with_uncertainty

    seeds = list(range(42, 42 + args.seeds))
    loads = args.bloc_load if args.bloc_load else [None]
    rows = []
    t0 = time.time()
    for scale in args.scales:
        horizon = {"small": 5, "large": 30}[scale]
        patients, vac0, ctx = build_patients_with_uncertainty(horizon_jours=horizon)
        if args.matched_only:
            patients = filter_matched(patients, ctx)
        for load in loads:
            vac, cap_day = make_vacations(vac0, patients, args.vac_split, load)
            regime = "base" if load is None else f"load{load:.2f}"
            print(f"\n=== {scale} | {regime} | {len(patients)} patients, {len(vac)} vacations "
                  f"({args.vac_split}/specialty-day, {cap_day:.0f} min/day), {args.beds} beds")
            meta = {"run": args.tag, "scale": scale, "regime": regime, "bloc_load": load,
                    "vac_split": args.vac_split, "beds": args.beds, "n_patients": len(patients),
                    "matched_only": args.matched_only}
            rows += run_instance(patients, vac, meta, seeds, args.scenarios, args.beds,
                                 args.with_ga_default, args.with_aco)
    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    summarize(df)
    print(f"\nSaved {args.out} ({len(df)} rows) in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()