"""Instrument original five failures at unchanged settings; no tuning or repair.

Record SA proposals/current states by wrapping the EXISTING neighbor and fitness
calls. No additional RNG draws. Enumerate one/two-move neighborhoods off-line.
"""
import argparse
from dataclasses import asdict
from hashlib import sha256
import itertools
import json
import math
import os
from pathlib import Path

import pandas as pd

from experiments.run_feasibility import ARMS, write_csv, write_json
from optimiseur.feasibility import FullStayPlanningProblem
from optimiseur.optimizer import simulated_annealing
from optimiseur.search_control import SearchControl
from optimiseur.validation import validate_full_stay

ROOT = Path(__file__).resolve().parents[1]
ORIGINAL = ROOT / "experiments/results/s1-s2-2026-10-19-v1"


def neighbors(problem, solution):
    """All nontrivial legal elementary moves, with no random sampling."""
    seen = set()
    for i in range(problem.n_patients):
        for j in problem._patient_options[i]:
            if j == solution[i]:
                continue
            other = dict(solution)
            other[i] = int(j)
            key = tuple(other[i] for i in range(problem.n_patients))
            if key not in seen:
                seen.add(key)
                yield other
    for i, j in itertools.combinations(range(problem.n_patients), 2):
        if (problem._pat_specialite[i] == problem._pat_specialite[j] and solution[i] != solution[j]
                and solution[j] in problem._patient_options[i] and solution[i] in problem._patient_options[j]):
            other = dict(solution)
            other[i], other[j] = other[j], other[i]
            key = tuple(other[i] for i in range(problem.n_patients))
            if key not in seen:
                seen.add(key)
                yield other


def neighborhood_diagnostic(problem, final, max_checks=20000):
    baseline = problem.fitness(final)
    direct = [(other, problem.fitness(other)) for other in neighbors(problem, final)]
    feasible_direct = sum(problem.violations(other) == (0.0, 0.0) for other, _ in direct)
    examined, feasible_two, best_two, best_path = 0, 0, baseline, None
    seen = {tuple(final[i] for i in range(problem.n_patients))}
    # Full two-move enumeration at n=16 is bounded; label truncation explicitly.
    for first, first_score in direct:
        for second in neighbors(problem, first):
            key = tuple(second[i] for i in range(problem.n_patients))
            if key in seen:
                continue
            seen.add(key)
            score = problem.fitness(second)
            examined += 1
            if score > best_two:
                best_two, best_path = score, {"first_score": first_score, "first": first, "second": second}
            if problem.violations(second) == (0.0, 0.0):
                feasible_two += 1
            if examined >= max_checks:
                break
        if examined >= max_checks:
            break
    return {"one_move_neighbors": len(direct),
            "one_move_improvements": sum(score > baseline for _, score in direct),
            "one_move_equal": sum(score == baseline for _, score in direct),
            "one_move_worse": sum(score < baseline for _, score in direct),
            "one_move_feasible": feasible_direct,
            "two_move_unique_states_checked": examined, "two_move_limit": max_checks,
            "two_move_truncated": examined >= max_checks,
            "two_move_feasible_states": feasible_two, "best_two_move_score": best_two,
            "best_two_move_path": best_path,
            "scope": "Local one/two-move reachability only; not a global reachability or infeasibility proof."}


def trace_failure(workload, saved):
    p, v = pd.DataFrame(workload["patients"]), pd.DataFrame(workload["sessions"])
    problem = FullStayPlanningProblem(p, v, workload["bed_capacities"],
                                      patient_options=workload["patient_options"], objective_mode="feasibility_first")
    initial = {int(i): j for i, j in saved["initial_assignment"].items()}
    rows, checkpoints, evals, pending = [], [], 0, None

    class TraceProblem:
        def __getattr__(self, name):
            return getattr(problem, name)

        def neighbor(self, current, rng):
            nonlocal pending
            if pending is not None:
                pending["accepted_next_state"] = int(current == pending.pop("_candidate"))
                pending["acceptance_observed"] = 1
            other, move = problem.neighbor(current, rng)
            room, beds, balance = problem.components(current)
            pending = {"iteration": len(rows), "current_score": problem.fitness(current),
                       "current_OR_overload": room, "current_bed_overload": beds,
                       "current_balance": balance, "move_type": move[0],
                       "nontrivial": int(other != current), "acceptance_observed": 0,
                       "accepted_next_state": None, "_candidate": dict(other),
                       "temperature": 50 * .95 ** len(rows)}
            return other, move

        def fitness(self, solution):
            nonlocal evals
            evals += 1
            score = problem.fitness(solution)
            if pending is not None:
                room, beds, balance = problem.components(solution)
                pending.update(evaluation=evals, candidate_score=score,
                               candidate_OR_overload=room, candidate_bed_overload=beds,
                               candidate_balance=balance,
                               delta_score=score - pending["current_score"])
                rows.append(pending)
            if evals in (1, 50, 100, 250, 500, 1000, 2000, 3000):
                checkpoints.append({"evaluation": evals, "candidate": dict(solution), "score": score})
            return score

    result = simulated_annealing(TraceProblem(), seed=saved["solver_seed"], initial_solution=initial,
                                 control=SearchControl(max_evaluations=3000), n_iter=3000,
                                 T0=50.0, alpha=.95)
    # No additional random draws: diagnostic replay must match saved final best.
    expected = {int(i): j for i, j in saved["final_assignment"].items()}
    assert result.meilleure_solution == expected
    assert result.evaluations == 3000
    assert not validate_full_stay(p, v, workload["bed_capacities"], expected,
                                  workload["patient_options"]).feasible
    for row in rows:
        row.pop("_candidate", None)
    # The final unevaluated proposal also reveals the last evaluated acceptance.
    last_improvement = max((r["evaluation"] for r in rows if r["candidate_score"]
                            == result.meilleure_fitness), default=1)
    # Earliest hit of returned best is more useful than its last repetition.
    first_best = min((r["evaluation"] for r in rows if r["candidate_score"]
                      == result.meilleure_fitness), default=1)
    initial_components = problem.components(initial)
    report = {"workload_seed": saved["workload_seed"], "solver_seed": saved["solver_seed"],
              "same_final_best_as_original": True, "evaluations": result.evaluations,
              "initial_OR_overload": initial_components[0], "initial_bed_overload": initial_components[1],
              "final_score": result.meilleure_fitness,
              "final_components": problem.components(expected),
              "first_evaluation_at_final_best_score": first_best,
              "last_evaluation_at_final_best_score": last_improvement,
              "nontrivial_proposals": sum(r["nontrivial"] for r in rows),
              "self_loop_proposals": sum(not r["nontrivial"] for r in rows),
              "accepted_nontrivial_worsenings_after_eval_250": sum(r["evaluation"] > 250
                    and r["nontrivial"] and r["delta_score"] < 0 and r["accepted_next_state"] == 1 for r in rows),
              "accepted_nontrivial_worsenings_before_eval_250": sum(r["evaluation"] <= 250
                    and r["nontrivial"] and r["delta_score"] < 0 and r["accepted_next_state"] == 1 for r in rows),
              "best_neighborhood": neighborhood_diagnostic(problem, expected),
              "checkpoints": checkpoints}
    return rows, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("Output must be new or empty")
    manifest = {"protocol": "s1-s2-failure-diagnostics-v1", "settings_changed": False,
        "source_sha256": {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest()
            for p in (Path(__file__), ROOT / "optimiseur/feasibility.py", ROOT / "optimiseur/validation.py",
                      ROOT / "optimiseur/optimizer.py", ROOT / "optimiseur/search_control.py")},
        "input_sha256": {name: sha256((ORIGINAL / name).read_bytes()).hexdigest()
                         for name in ("workloads.json", "schedules.jsonl", "manifest.json")},
        "one_two_move_diagnostic_limit_per_failure": 20000,
        "notes": ["One/two move enumeration is off-line diagnosis, not additional solver effort.",
                  "No extra random draws or tuned parameters; exact final-best replay required."]}
    write_json(output / "manifest.json", manifest)
    workloads = {w["workload_seed"]: w for w in json.loads((ORIGINAL / "workloads.json").read_text())}
    schedules = [json.loads(line) for line in (ORIGINAL / "schedules.jsonl").read_text().splitlines()]
    failures = [r for r in schedules if r["arm"] == ARMS[2] and not r["validation"]["feasible"]]
    assert len(failures) == 5
    reports = []
    for saved in failures:
        rows, report = trace_failure(workloads[saved["workload_seed"]], saved)
        name = f"trace-{saved['workload_seed']}-{saved['solver_seed']}.csv"
        write_csv(output / name, rows)
        reports.append(report)
        print(f"diagnosed {saved['workload_seed']}/{saved['solver_seed']}", flush=True)
    write_json(output / "diagnostics.json", reports)
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache" / "matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for saved in failures:
        import csv
        with (output / f"trace-{saved['workload_seed']}-{saved['solver_seed']}.csv").open(newline="") as handle:
            trace = list(csv.DictReader(handle))
        axes[0].plot([int(r["evaluation"]) for r in trace], [-float(r["current_score"]) for r in trace],
                     label=f"{saved['workload_seed']}/{saved['solver_seed']}")
    axes[0].set(xlabel="Scored evaluation", ylabel="Current cost", title="Frozen-setting failure trajectories")
    axes[0].legend()
    axes[1].semilogy(range(3000), [max(50 * .95 ** k, 1e-9) for k in range(3000)])
    axes[1].set(xlabel="SA iteration", ylabel="Effective temperature (floor 1e-9)", title="Unchanged alpha=0.95, T0=50")
    fig.tight_layout()
    fig.savefig(output / "failure_trajectories.png", dpi=160)
    plt.close(fig)
    manifest.update(status="complete", failures=len(reports), exact_replays=sum(r["same_final_best_as_original"] for r in reports),
        output_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in output.iterdir()
                       if p.is_file() and p.name != "manifest.json"})
    write_json(output / "manifest.json", manifest)


if __name__ == "__main__":
    main()
