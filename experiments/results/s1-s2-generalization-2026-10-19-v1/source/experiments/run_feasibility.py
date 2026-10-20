"""Reproduce the S1/S2 controlled comparison without confidential data or ML.

Run from repository root: python -B -m experiments.run_feasibility --output PATH
The output directory must be new or empty. All runs and inputs are preserved.
"""
import argparse
import csv
from dataclasses import asdict
from hashlib import sha256
import itertools
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
from time import monotonic

import numpy as np
import pandas as pd

from optimiseur.feasibility import FullStayPlanningProblem, run_validated_sa
from optimiseur.optimizer import PlanningProblem
from optimiseur.validation import validate_full_stay

ROOT = Path(__file__).resolve().parents[1]
ARMS = ("A_legacy_weighted", "B_full_weighted", "C_full_feasibility_first")
SOURCE_FILES = ("optimiseur/optimizer.py", "optimiseur/search_control.py",
                "optimiseur/feasibility.py", "optimiseur/validation.py",
                "experiments/run_feasibility.py", "tests/test_feasibility.py",
                "tests/test_feasibility_experiment.py")


def generate_workload(seed):
    """Plant a feasible witness; generate initial assignments separately.

    Four operating days, two specialties, two patients per session. Capacity is
    constructed from a private-to-generation witness, not given to the solver.
    Tail capacity follows witness occupancy; the last four workloads have lower
    tail than operating-day supply, permitting hidden overload under truncation.
    """
    rng = random.Random(seed)
    category = ("slack" if seed < 1104 else "near_capacity" if seed < 1108 else "tail_decline")
    sessions = pd.DataFrame([
        {"vacation_id": j, "jour": j // 2, "specialite": ("X", "Y")[j % 2], "capacite_min": 0}
        for j in range(8)])
    patients, witness = [], {}
    for j in range(8):
        for _ in range(2):
            i = len(patients)
            # Include long late stays without changing the LOS offset convention.
            stay = rng.randrange(1, 4) if category == "tail_decline" else rng.randrange(3)
            patients.append({"patient_id": i, "specialite": sessions.iloc[j].specialite,
                             "duree_operatoire": rng.randrange(3, 13) * 15,
                             "duree_sejour": stay})
            witness[i] = j
    patients = pd.DataFrame(patients)
    loads = [sum(int(patients.iloc[i].duree_operatoire) for i in witness if witness[i] == j)
             for j in range(8)]
    sessions["capacite_min"] = [load + (180 if category == "slack" else 15) for load in loads]
    options = [[j for j in range(8) if sessions.iloc[j].specialite == patients.iloc[i].specialite]
               for i in range(len(patients))]
    horizon = 4 + int(patients.duree_sejour.max())
    occupancy = [sum(int(sessions.iloc[j].jour) <= day <= int(sessions.iloc[j].jour)
                     + int(patients.iloc[i].duree_sejour) for i, j in witness.items())
                 for day in range(horizon)]
    if category == "tail_decline":
        beds = [max(occupancy) + 3] * 4 + occupancy[4:]
    else:
        beds = [count + (4 if category == "slack" else 1) for count in occupancy]
    assert validate_full_stay(patients, sessions, beds, witness, options).feasible
    return {"workload_seed": seed, "category": category, "patients": patients.to_dict("records"),
            "sessions": sessions.to_dict("records"), "bed_capacities": beds,
            "patient_options": options, "feasible_witness": witness,
            "initial_assignments": {str(s): {i: random.Random(7000 + s + 101 * i).choice(options[i])
                                             for i in range(len(patients))} for s in range(5)}}


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def execute_run(workload, solver_seed, arm, budget, safety):
    patients, sessions = pd.DataFrame(workload["patients"]), pd.DataFrame(workload["sessions"])
    initial = {int(i): int(j) for i, j in workload["initial_assignments"][str(solver_seed)].items()}
    problem = FullStayPlanningProblem(patients, sessions, workload["bed_capacities"],
                patient_options=workload["patient_options"],
                objective_mode="feasibility_first" if arm == ARMS[2] else "weighted")
    started = monotonic()
    run = run_validated_sa(problem, initial_solution=initial, seed=solver_seed,
                           max_evaluations=budget, T0=50.0, alpha=0.95,
                           safety_seconds=safety, legacy_accounting=arm == ARMS[0])
    elapsed = monotonic() - started
    result, valid = run.result, run.validation
    legacy = PlanningProblem(patients, sessions, lits_capacity=workload["bed_capacities"][:problem.n_days],
                              patient_options=workload["patient_options"])
    legacy_over = legacy.violations(result.meilleure_solution)
    row = {"workload_seed": workload["workload_seed"], "category": workload["category"],
           "solver_seed": solver_seed, "arm": arm,
           "feasible": int(valid.feasible), "valid": int(valid.valid),
           "assigned_cases": valid.assigned_cases, "missing_cases": valid.missing_cases,
           "or_overload_minutes": valid.or_overload_minutes,
           "bed_overload_days": valid.bed_overload_days,
           "tail_bed_overload_days": valid.tail_bed_overload_days,
           "legacy_reports_feasible": int(legacy_over == (0.0, 0.0)),
           "balance_minutes": valid.balance_minutes,
           "full_weighted_cost": 5 * valid.or_overload_minutes + 3 * valid.bed_overload_days + 0.05 * valid.balance_minutes,
           "arm_score_cost": -result.meilleure_fitness,
           "ever_feasible": int(run.best_feasible_solution is not None),
           "best_feasible_balance_minutes": run.best_feasible_balance,
           "best_feasible_soft_cost": None if run.best_feasible_balance is None else 0.05 * run.best_feasible_balance,
           "first_feasible_evaluation": run.first_feasible_evaluation,
           "first_feasible_seconds": run.first_feasible_seconds,
           "search_seconds": result.duree_s, "run_seconds_including_final_validation": elapsed,
           "evaluations": result.evaluations, "termination_reason": result.stop_reason}
    schedule = {"workload_seed": workload["workload_seed"], "solver_seed": solver_seed, "arm": arm,
                "initial_assignment": initial, "final_assignment": result.meilleure_solution,
                "best_feasible_assignment": run.best_feasible_solution, "validation": asdict(valid)}
    return row, schedule


def analytical_and_stress(output, budget, safety):
    patients = [{"patient_id": i, "specialite": "X", "duree_operatoire": 1000, "duree_sejour": 0}
                for i in range(2)]
    sessions = [{"vacation_id": j, "jour": j, "specialite": "X", "capacite_min": 2000}
                for j in range(2)]
    w = {"patients": patients, "sessions": sessions, "bed_capacities": [2, 0],
         "patient_options": [[0], [0, 1]], "initial_assignments": {"0": {0: 0, 1: 1}},
         "workload_seed": "counterexample", "category": "analytical"}
    p, v = pd.DataFrame(patients), pd.DataFrame(sessions)
    original = PlanningProblem(p, v, lits_capacity=[2, 0], patient_options=w["patient_options"])
    corrected = FullStayPlanningProblem(p, v, [2, 0], patient_options=w["patient_options"],
                                        objective_mode="feasibility_first")
    analytical = [{"solution": s, "legacy_cost": -original.fitness(s),
                   "new_cost": -corrected.fitness(s),
                   "validation": asdict(validate_full_stay(p, v, [2, 0], s, w["patient_options"]))}
                  for s in ({0: 0, 1: 0}, {0: 0, 1: 1})]
    write_json(output / "counterexample.json", analytical)
    stress, stress_runs = [], []
    for name in ("no_specialty", "oversized_case", "aggregate_OR_deficit", "mandatory_bed_deficit"):
        case = json.loads(json.dumps(w))
        case["workload_seed"], case["category"] = name, "infeasible_stress"
        case["initial_assignments"] = {"0": {0: 0, 1: 0}}
        case["patient_options"] = [[0], [0]]
        if name == "no_specialty":
            case["patients"][0]["specialite"] = "Y"
        elif name == "oversized_case":
            case["patients"][0]["duree_operatoire"] = 2001
        elif name == "aggregate_OR_deficit":
            case["sessions"][0]["capacite_min"] = 1500
        else:
            case["bed_capacities"] = [1, 0]
        cp, cv = pd.DataFrame(case["patients"]), pd.DataFrame(case["sessions"])
        report = validate_full_stay(cp, cv, case["bed_capacities"], {0: 0, 1: 0}, case["patient_options"])
        assert not report.feasible
        record = {"name": name, "workload": case, "independent_validation": asdict(report)}
        if name == "no_specialty":
            record["proof"] = "Patient 0 has no specialty-compatible session; rejected before search."
            try:
                FullStayPlanningProblem(cp, cv, case["bed_capacities"], patient_options=case["patient_options"])
            except ValueError:
                record["rejected_before_search"] = True
            else:
                raise AssertionError("No-specialty input should fail")
        else:
            # Each patient has exactly one allowed session: enumeration is exact.
            all_choices = itertools.product(*case["patient_options"])
            assert not any(validate_full_stay(cp, cv, case["bed_capacities"], dict(enumerate(x)),
                                             case["patient_options"]).feasible for x in all_choices)
            record["proof"] = "All allowed assignments exhaustively enumerated; none feasible."
            for arm in ARMS:
                row, _ = execute_run(case, 0, arm, budget, safety)
                assert not row["feasible"]
                stress_runs.append(row)
        stress.append(record)
    write_json(output / "stress_cases.json", stress)
    write_csv(output / "stress_runs.csv", stress_runs)


def analyze(output, rows):
    summary = []
    for arm in ARMS:
        group = [r for r in rows if r["arm"] == arm]
        feasible = [r for r in group if r["feasible"]]
        best = [r["best_feasible_balance_minutes"] for r in group if r["ever_feasible"]]
        first = [r["first_feasible_evaluation"] for r in group if r["ever_feasible"]]
        summary.append({"arm": arm, "runs": len(group), "feasible_runs": len(feasible),
                        "feasible_rate": len(feasible) / len(group),
                        "ever_feasible_runs": sum(r["ever_feasible"] for r in group),
                        "mean_or_overload_minutes": statistics.mean(r["or_overload_minutes"] for r in group),
                        "mean_full_bed_overload_days": statistics.mean(r["bed_overload_days"] for r in group),
                        "mean_tail_bed_overload_days": statistics.mean(r["tail_bed_overload_days"] for r in group),
                        "mean_final_balance_when_feasible": statistics.mean(r["balance_minutes"] for r in feasible) if feasible else None,
                        "mean_best_feasible_balance_when_found": statistics.mean(best) if best else None,
                        "median_first_feasible_evaluation_when_found": statistics.median(first) if first else None,
                        "mean_search_seconds": statistics.mean(r["search_seconds"] for r in group),
                        "mean_run_seconds": statistics.mean(r["run_seconds_including_final_validation"] for r in group),
                        "invalid_runs": sum(not r["valid"] for r in group),
                        "hidden_bed_violation_runs": sum(r["legacy_reports_feasible"] and not r["feasible"] for r in group),
                        "deadline_stops": sum(r["termination_reason"] == "deadline" for r in group)})
    write_csv(output / "summary.csv", summary)
    workloads = []
    for seed in sorted(set(r["workload_seed"] for r in rows)):
        for arm in ARMS:
            group = [r for r in rows if r["workload_seed"] == seed and r["arm"] == arm]
            workloads.append({"workload_seed": seed, "category": group[0]["category"], "arm": arm,
                              "feasible_rate": statistics.mean(r["feasible"] for r in group),
                              "mean_or_overload_minutes": statistics.mean(r["or_overload_minutes"] for r in group),
                              "mean_bed_overload_days": statistics.mean(r["bed_overload_days"] for r in group)})
    write_csv(output / "workload_summary.csv", workloads)
    paired = []
    for seed in sorted(set(r["workload_seed"] for r in rows)):
        means = {r["arm"]: r for r in workloads if r["workload_seed"] == seed}
        for left, right in ((ARMS[0], ARMS[1]), (ARMS[1], ARMS[2]), (ARMS[0], ARMS[2])):
            paired.append({"workload_seed": seed, "comparison": right + " minus " + left,
                           "feasible_rate_difference": means[right]["feasible_rate"] - means[left]["feasible_rate"],
                           "bed_overload_difference": means[right]["mean_bed_overload_days"] - means[left]["mean_bed_overload_days"]})
    write_csv(output / "paired_workload_differences.csv", paired)
    common = []
    for left, right in ((ARMS[0], ARMS[1]), (ARMS[1], ARMS[2]), (ARMS[0], ARMS[2])):
        pairs = []
        for r in rows:
            if r["arm"] == left and r["feasible"]:
                other = next(x for x in rows if x["workload_seed"] == r["workload_seed"]
                             and x["solver_seed"] == r["solver_seed"] and x["arm"] == right)
                if other["feasible"]:
                    pairs.append(other["balance_minutes"] - r["balance_minutes"])
        common.append({"comparison": right + " minus " + left, "jointly_feasible_seed_pairs": len(pairs),
                       "mean_balance_difference_minutes": statistics.mean(pairs) if pairs else None,
                       "left_better_balance_pairs": sum(d > 0 for d in pairs),
                       "right_better_balance_pairs": sum(d < 0 for d in pairs)})
    write_csv(output / "jointly_feasible_quality.csv", common)
    # Noninteractive standard plots, no image generation or private data.
    os.environ.setdefault("MPLCONFIGDIR", str(output / "matplotlib-cache"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    labels = ["A: truncated weighted", "B: full weighted", "C: full feasibility-first"]
    axes[0].bar(labels, [r["feasible_rate"] for r in summary])
    axes[0].set(ylabel="Final full-stay feasible fraction", ylim=(0, 1.05))
    axes[1].bar(labels, [r["mean_full_bed_overload_days"] for r in summary])
    axes[1].set(ylabel="Mean bed overload (bed-days)")
    for ax in axes:
        ax.tick_params(axis="x", labelrotation=18)
    fig.suptitle("12 planted workloads × 5 solver seeds; deterministic synthetic requirements")
    fig.tight_layout()
    fig.savefig(output / "feasibility_and_beds.png", dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(10, 4))
    for arm, label in zip(ARMS, labels):
        subset = [r for r in workloads if r["arm"] == arm]
        ax.plot([r["workload_seed"] for r in subset], [r["feasible_rate"] for r in subset], marker="o", label=label)
    ax.set(xlabel="Independent workload seed", ylabel="Feasible fraction over 5 solver seeds", ylim=(-0.05, 1.05))
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "per_workload_feasibility.png", dpi=160)
    plt.close(fig)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evaluations", type=int, default=3000)
    parser.add_argument("--safety-seconds", type=float, default=30)
    args = parser.parse_args()
    if args.evaluations < 1 or not np.isfinite(args.safety_seconds) or args.safety_seconds <= 0:
        parser.error("Positive finite budgets required")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("Refusing to overwrite: output directory must be empty")
    source = {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES if (ROOT / name).exists()}
    manifest = {"protocol": "s1-s2-v1", "status": "running", "synthetic_only": True,
                "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
                "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                "source_sha256": source, "arms": ARMS, "workload_seeds": list(range(1100, 1112)),
                "solver_seeds": list(range(5)), "evaluations_including_initialization": args.evaluations,
                "SA": {"T0": 50, "alpha": 0.95, "safety_seconds_per_run": args.safety_seconds},
                "arm_order": "rotate by (workload_seed + solver_seed) % 3 to reduce order bias",
                "feasibility_first_cost": "feasible: .05*std(load)/(1+.05*sum(duration)); otherwise 1+5*OR_overload+3*bed_overload",
                "notes": ["Objective scaling changes acceptance: feasible balance is compressed, violation units retained.",
                          "No repair, no witness warm start, no model fitting, no hidden patient outcomes.",
                          "Identical full-stay observer work in all arms; baseline score remains the legacy objective.",
                          "Durations/LOS are exact synthetic requirements, not predicted clinical outcomes.",
                          "Clock budget is a synchronous evaluation-boundary guard, not process preemption."]}
    (output / "source").mkdir()
    for name in source:
        target = output / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    write_json(output / "manifest.json", manifest)
    workloads = [generate_workload(seed) for seed in range(1100, 1112)]
    write_json(output / "workloads.json", workloads)
    manifest["workloads_sha256"] = sha256((output / "workloads.json").read_bytes()).hexdigest()
    write_json(output / "manifest.json", manifest)
    analytical_and_stress(output, args.evaluations, args.safety_seconds)
    rows = []
    with (output / "schedules.jsonl").open("w", encoding="utf-8") as handle:
        for workload in workloads:
            for seed in range(5):
                offset = (workload["workload_seed"] + seed) % len(ARMS)
                for arm in ARMS[offset:] + ARMS[:offset]:
                    row, schedule = execute_run(workload, seed, arm, args.evaluations, args.safety_seconds)
                    rows.append(row)
                    handle.write(json.dumps(schedule, allow_nan=False) + "\n")
            write_csv(output / "runs.csv", rows)
            print(f"workload {workload['workload_seed']} complete ({len(rows)}/180 runs)", flush=True)
    summary = analyze(output, rows)
    manifest.update(status="complete", primary_runs=len(rows),
                    total_primary_evaluations=sum(r["evaluations"] for r in rows),
                    outputs_sha256={p.name: sha256(p.read_bytes()).hexdigest()
                                    for p in output.iterdir() if p.is_file() and p.name != "manifest.json"})
    write_json(output / "manifest.json", manifest)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
