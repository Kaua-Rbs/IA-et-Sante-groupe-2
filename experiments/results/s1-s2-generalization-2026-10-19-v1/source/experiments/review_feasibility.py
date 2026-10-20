"""Frozen-setting generalization experiment on fresh 60/300-patient workloads.

Synthetic only. New/empty output directory required. No algorithm tuning.
"""
import argparse
import csv
from dataclasses import asdict
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
from time import monotonic

import numpy as np
import pandas as pd

from experiments.run_feasibility import ARMS, execute_run, write_csv, write_json
from optimiseur.validation import validate_full_stay

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ("optimiseur/optimizer.py", "optimiseur/search_control.py", "optimiseur/feasibility.py",
           "optimiseur/validation.py", "experiments/run_feasibility.py", "experiments/review_feasibility.py",
           "experiments/diagnose_feasibility_failures.py", "tests/test_feasibility_review.py",
           "tests/test_feasibility_generalization.py")


def generate_large_workload(n, seed, pressure):
    """Generate capacities from a witness, never use it to initialize search.

    60 patients: 5 days x 3 specialty sessions, 4 patients per witness session.
    300 patients: 20 days x 3 sessions, 5 patients per witness session.
    Variable lognormal room durations, mixed same-day/1-7-day offsets. About
    25% of cases have 3-day eligibility windows containing the witness date.
    These are plausible synthetic variations, not fitted hospital distributions.
    """
    if n not in (60, 300) or pressure not in ("moderate", "near_capacity"):
        raise ValueError("Unsupported declared experiment cell")
    rng = random.Random(seed)
    days, specialties = (5 if n == 60 else 20), ("X", "Y", "Z")
    sessions = [{"vacation_id": j, "jour": j // 3, "specialite": specialties[j % 3],
                 "capacite_min": 0} for j in range(days * 3)]
    patients, options, witness = [], [], {}
    per_session = n // len(sessions)
    for j, session in enumerate(sessions):
        for _ in range(per_session):
            i = len(patients)
            duration = int(max(15, min(180, 5 * round(rng.lognormvariate(math.log(65), 0.5) / 5))))
            offset = rng.choices((0, 1, 2, 3, 5, 7), weights=(35, 25, 18, 12, 7, 3), k=1)[0]
            patients.append({"patient_id": i, "specialite": session["specialite"],
                             "duree_operatoire": duration, "duree_sejour": offset})
            witness[i] = j
            window = (max(0, session["jour"] - 1), min(days - 1, session["jour"] + 1))
            restricted = rng.random() < 0.25
            options.append([k for k, s in enumerate(sessions) if s["specialite"] == session["specialite"]
                            and (not restricted or window[0] <= s["jour"] <= window[1])])
    target = 0.80 if pressure == "moderate" else 0.95
    for j, session in enumerate(sessions):
        load = sum(patients[i]["duree_operatoire"] for i in range(n) if witness[i] == j)
        session["capacite_min"] = int(15 * math.ceil(load / target / 15))
    horizon = max([days] + [max(sessions[j]["jour"] for j in options[i])
                            + patients[i]["duree_sejour"] + 1 for i in range(n)])
    occupancy = [0] * horizon
    for i, j in witness.items():
        for day in range(sessions[j]["jour"], sessions[j]["jour"] + patients[i]["duree_sejour"] + 1):
            occupancy[day] += 1
    beds = [int(math.ceil(x / target)) + (1 if pressure == "moderate" else 0) for x in occupancy]
    initial = {}
    for solver_seed in range(5 if n == 60 else 2):
        initial_rng = random.Random(900000 + seed * 100 + solver_seed)
        initial[str(solver_seed)] = {i: initial_rng.choice(options[i]) for i in range(n)}
    workload = {"workload_seed": seed, "category": pressure, "n_patients": n,
                "patients": patients, "sessions": sessions, "bed_capacities": beds,
                "patient_options": options, "feasible_witness": witness,
                "initial_assignments": initial,
                "generation": {"target_witness_OR_utilization_before_15_min_rounding": target,
                               "target_witness_bed_utilization_before_integer_rounding": target,
                               "witness_session_load_max_minutes": max(sum(patients[i]["duree_operatoire"]
                                    for i in range(n) if witness[i] == j) for j in range(len(sessions))),
                               "restrictive_patient_count": sum(len(o) < days for o in options)}}
    report = validate_full_stay(pd.DataFrame(patients), pd.DataFrame(sessions), beds, witness, options)
    if not report.feasible:
        raise AssertionError("Generator did not produce a feasible witness")
    return workload


def summarize(output, rows):
    summary = []
    for n, pressure in sorted({(r["n_patients"], r["category"]) for r in rows}):
        for arm in ARMS:
            group = [r for r in rows if r["n_patients"] == n and r["category"] == pressure and r["arm"] == arm]
            if not group:
                continue
            feasible = [r for r in group if r["feasible"]]
            summary.append({"n_patients": n, "pressure": pressure, "arm": arm,
                "workloads": len({r["workload_seed"] for r in group}), "runs": len(group),
                "feasible_returned": sum(r["feasible"] for r in group),
                "feasible_rate": statistics.mean(r["feasible"] for r in group),
                "feasible_discovered": sum(r["ever_feasible"] for r in group),
                "mean_OR_overload_minutes": statistics.mean(r["or_overload_minutes"] for r in group),
                "mean_full_bed_overload_days": statistics.mean(r["bed_overload_days"] for r in group),
                "mean_tail_bed_overload_days": statistics.mean(r["tail_bed_overload_days"] for r in group),
                "mean_balance_when_feasible": statistics.mean(r["balance_minutes"] for r in feasible) if feasible else None,
                "mean_search_seconds": statistics.mean(r["search_seconds"] for r in group),
                "mean_run_seconds_with_validation": statistics.mean(r["run_seconds_including_final_validation"] for r in group),
                "min_evaluations": min(r["evaluations"] for r in group),
                "max_evaluations": max(r["evaluations"] for r in group),
                "deadline_stops": sum(r["termination_reason"] == "deadline" for r in group),
                "invalid_assignments": sum(not r["valid"] or r["missing_cases"] > 0 for r in group),
                "hidden_violations": sum(r["legacy_reports_feasible"] and not r["feasible"] for r in group)})
    write_csv(output / "summary_by_size_pressure.csv", summary)
    workloads = []
    for seed in sorted({r["workload_seed"] for r in rows}):
        for arm in ARMS:
            group = [r for r in rows if r["workload_seed"] == seed and r["arm"] == arm]
            workloads.append({"workload_seed": seed, "n_patients": group[0]["n_patients"],
                "pressure": group[0]["category"], "arm": arm, "runs": len(group),
                "feasible_rate": statistics.mean(r["feasible"] for r in group),
                "discovery_rate": statistics.mean(r["ever_feasible"] for r in group),
                "mean_OR_overload_minutes": statistics.mean(r["or_overload_minutes"] for r in group),
                "mean_bed_overload_days": statistics.mean(r["bed_overload_days"] for r in group)})
    write_csv(output / "workload_summary.csv", workloads)
    comparisons, quality = [], []
    for seed in sorted({r["workload_seed"] for r in rows}):
        means = {r["arm"]: r for r in workloads if r["workload_seed"] == seed}
        for left, right in ((ARMS[0], ARMS[1]), (ARMS[1], ARMS[2]), (ARMS[0], ARMS[2])):
            comparisons.append({"workload_seed": seed, "n_patients": means[left]["n_patients"],
                "pressure": means[left]["pressure"], "comparison": right + " minus " + left,
                "feasibility_rate_difference": means[right]["feasible_rate"] - means[left]["feasible_rate"],
                "bed_overload_difference": means[right]["mean_bed_overload_days"] - means[left]["mean_bed_overload_days"]})
    write_csv(output / "paired_workload_differences.csv", comparisons)
    for n, pressure in sorted({(r["n_patients"], r["category"]) for r in rows}):
        for left, right in ((ARMS[0], ARMS[1]), (ARMS[1], ARMS[2]), (ARMS[0], ARMS[2])):
            differences = []
            for row in rows:
                if row["n_patients"] == n and row["category"] == pressure and row["arm"] == left and row["feasible"]:
                    other = next(r for r in rows if r["workload_seed"] == row["workload_seed"]
                                 and r["solver_seed"] == row["solver_seed"] and r["arm"] == right)
                    if other["feasible"]:
                        differences.append(other["balance_minutes"] - row["balance_minutes"])
            quality.append({"n_patients": n, "pressure": pressure, "comparison": right + " minus " + left,
                            "jointly_feasible_pairs": len(differences),
                            "mean_balance_difference_minutes": statistics.mean(differences) if differences else None})
    write_csv(output / "jointly_feasible_quality.csv", quality)
    failures = [r for r in rows if not r["feasible"]]
    if failures:
        write_csv(output / "failure_runs.csv", failures)
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cells = sorted({(r["n_patients"], r["pressure"]) for r in summary})
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    x = np.arange(len(cells))
    for j, arm in enumerate(ARMS):
        selected = [next(r for r in summary if (r["n_patients"], r["pressure"]) == cell and r["arm"] == arm) for cell in cells]
        for ax, column in zip(axes, ("feasible_rate", "mean_OR_overload_minutes", "mean_full_bed_overload_days")):
            ax.bar(x + (j - 1) * .25, [r[column] for r in selected], width=.25, label=arm.split('_')[0])
    for ax, title in zip(axes, ("Full-stay feasible fraction", "OR overload (min/run)", "Full-stay bed overload (bed-days/run)")):
        ax.set(title=title, xticks=x, xticklabels=[f"{n}\n{p.replace('_', ' ')}" for n, p in cells])
        ax.legend(title="Arm")
    axes[0].set_ylim(0, 1.05)
    fig.suptitle("Fresh synthetic workloads; 6,000 scored evaluations per run; 300-patient cells are pilots")
    fig.tight_layout()
    fig.savefig(output / "generalization_comparison.png", dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(11, 4))
    for arm in ARMS:
        selected = [r for r in workloads if r["n_patients"] == 60 and r["arm"] == arm]
        ax.plot([r["workload_seed"] for r in selected], [r["feasible_rate"] for r in selected], marker="o", label=arm)
    ax.set(xlabel="Independent 60-patient workload seed", ylabel="Feasible fraction over 5 solver seeds", ylim=(-.05, 1.05))
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "per_workload_60.png", dpi=160)
    plt.close(fig)
    return summary


def verify(output):
    """Read-only independent replay; deadline-censored runs remain labeled."""
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["output_sha256"].items():
        assert sha256((output / name).read_bytes()).hexdigest() == expected, name
    for name, expected in manifest["source_sha256"].items():
        assert sha256((output / "source" / name).read_bytes()).hexdigest() == expected, name
    data = {w["workload_seed"]: w for w in json.loads((output / "workloads.json").read_text(encoding="utf-8"))}
    with (output / "runs.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    index = {(int(r["workload_seed"]), int(r["solver_seed"]), r["arm"]): r for r in rows}
    schedules = [json.loads(line) for line in (output / "schedules.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(index) == len(rows) == len(schedules) == manifest["completed_runs"]
    incumbents, checked = 0, 0
    for saved in schedules:
        key = saved["workload_seed"], saved["solver_seed"], saved["arm"]
        w, row = data[key[0]], index[key]
        p, v = pd.DataFrame(w["patients"]), pd.DataFrame(w["sessions"])
        def check(solution):
            return validate_full_stay(p, v, w["bed_capacities"], {int(i): j for i, j in solution.items()}, w["patient_options"])
        result = check(saved["final_assignment"])
        assert result.valid and result.missing_cases == 0
        assert result.feasible == bool(int(row["feasible"]))
        for field, value in (("or_overload_minutes", result.or_overload_minutes),
                              ("bed_overload_days", result.bed_overload_days),
                              ("tail_bed_overload_days", result.tail_bed_overload_days),
                              ("balance_minutes", result.balance_minutes)):
            assert abs(float(row[field]) - value) < 1e-9
        assert saved["initial_assignment"] == w["initial_assignments"][str(key[1])]
        if row["termination_reason"] == "evaluations":
            assert int(row["evaluations"]) == manifest["evaluations_per_run"]
        else:
            assert row["termination_reason"] == "deadline" and int(row["evaluations"]) <= manifest["evaluations_per_run"]
        if saved["best_feasible_assignment"] is not None:
            incumbent = check(saved["best_feasible_assignment"])
            assert incumbent.feasible
            assert abs(incumbent.balance_minutes - float(row["best_feasible_balance_minutes"])) < 1e-9
            incumbents += 1
        checked += 1
    for seed in {key[0] for key in index}:
        for solver in {key[1] for key in index if key[0] == seed}:
            assert {key[2] for key in index if key[:2] == (seed, solver)} == set(ARMS)
    return {"schedules_checked": checked, "incumbents_checked": incumbents,
            "hashes_verified": True, "matched_arm_blocks": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if args.verify_only:
        print(json.dumps(verify(output), indent=2))
        return
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("Output must be new or empty; old results are never overwritten")
    started = monotonic()
    manifest = {"protocol": "s1-s2-generalization-v1", "status": "running", "synthetic_only": True,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
        "source_sha256": {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES if (ROOT / name).exists()},
        "arms": ARMS, "evaluations_per_run": 6000, "SA": {"T0": 50, "alpha": .95},
        "planned_60_seeds": list(range(2200, 2208)), "planned_300_seeds": [3300, 3301],
        "solver_seeds_60": list(range(5)), "solver_seeds_300": [0, 1],
        "per_run_search_guard_seconds_60": 15, "per_run_search_guard_seconds_300": 20,
        "total_guard_seconds": 900,
        "pilot_stop_rule": "Stop remaining 300-patient blocks if any first-block deadline stop or mean first-block end-to-end run time > 10 seconds; no replacement seeds or tuning.",
        "arm_order": "rotate by (workload_seed + solver_seed) % 3",
        "comparability": "6,000 evaluations across all arms/sizes; 100 evaluations/patient at 60, 20 at 300. No size-scaled convergence guarantee.",
        "initialization": "Uniform eligible choices using independent initialization RNG; witness excluded from solver inputs.",
        "objective": "Unchanged S1/S2 float objective and default cooling; only Mapping/Set capacity-vector validation hardened.",
        "skipped_blocks": []}
    (output / "source").mkdir()
    for name in manifest["source_sha256"]:
        dest = output / "source" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT / name).read_bytes())
    write_json(output / "manifest.json", manifest)
    workloads = [generate_large_workload(60, seed, "moderate" if seed < 2204 else "near_capacity") for seed in range(2200, 2208)]
    workloads += [generate_large_workload(300, seed, "moderate" if seed == 3300 else "near_capacity") for seed in (3300, 3301)]
    write_json(output / "workloads.json", workloads)
    rows, pilot_stopped = [], False
    with (output / "schedules.jsonl").open("w", encoding="utf-8") as handle:
        for w in workloads:
            n, seed = w["n_patients"], w["workload_seed"]
            for solver in range(5 if n == 60 else 2):
                cap = 15 if n == 60 else 20
                if (n == 300 and pilot_stopped) or monotonic() - started + 3 * (cap + 5) >= 900:
                    manifest["skipped_blocks"].append({"workload_seed": seed, "solver_seed": solver,
                        "reason": "pilot guard" if pilot_stopped else "total time guard"})
                    continue
                offset = (seed + solver) % 3
                block = []
                for arm in ARMS[offset:] + ARMS[:offset]:
                    row, saved = execute_run(w, solver, arm, 6000, cap)
                    row["n_patients"] = n
                    rows.append(row)
                    block.append(row)
                    handle.write(json.dumps(saved, allow_nan=False) + "\n")
                    handle.flush()
                write_csv(output / "runs.csv", rows)
                if n == 300 and (any(r["termination_reason"] == "deadline" for r in block)
                                  or statistics.mean(r["run_seconds_including_final_validation"] for r in block) > 10):
                    pilot_stopped = True
            print(f"workload {seed}, n={n}, {w['category']}: {len(rows)} runs saved", flush=True)
    if not rows:
        raise RuntimeError("No complete matched block finished")
    summary = summarize(output, rows)
    manifest.update(status="complete_with_skips" if manifest["skipped_blocks"] else "complete",
                    completed_runs=len(rows), wall_seconds=monotonic() - started,
                    total_evaluations=sum(r["evaluations"] for r in rows),
                    output_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in output.iterdir()
                                   if p.is_file() and p.name != "manifest.json"})
    write_json(output / "manifest.json", manifest)
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
