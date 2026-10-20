"""Reproduce the concrete input bug and bounded failure/integration diagnostics."""
import argparse
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys

import pandas as pd

from experiments.diagnose_feasibility_failures import neighbors
from experiments.run_feasibility import write_json
from optimiseur.feasibility import FullStayPlanningProblem
from optimiseur.optimizer import PlanningProblem, solution_to_dataframe
from optimiseur.validation import validate_full_stay
from tests.test_feasibility import counterexample

ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "experiments/results/s1-s2-2026-10-19-v1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("Output must be new or empty")
    p, v, _, options = counterexample()
    old_path = OLD / "source/optimiseur/validation.py"
    spec = importlib.util.spec_from_file_location("archived_s1_s2_validator", old_path)
    archived = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = archived
    spec.loader.exec_module(archived)
    bad_supply = {2: 0, 3: 0}
    before = archived.validate_full_stay(p, v, bad_supply, {0: 0, 1: 0}, options)
    after = validate_full_stay(p, v, bad_supply, {0: 0, 1: 0}, options)
    assert before.feasible and not after.feasible and not after.valid
    bug = {"input": "{2: 0, 3: 0} supplied as a capacity vector",
           "before_feasible": before.feasible, "after_valid": after.valid, "after_feasible": after.feasible,
           "cause": "tuple(mapping) consumed keys as capacities; unordered sets were also accepted",
           "correction": "Reject Mapping and Set before converting an explicit ordered vector",
           "old_source_sha256": sha256(old_path.read_bytes()).hexdigest(),
           "new_source_sha256": sha256((ROOT / "optimiseur/validation.py").read_bytes()).hexdigest()}
    write_json(output / "confirmed_bug.json", bug)
    p.loc[1, "duree_sejour"] = 3
    problem = FullStayPlanningProblem(p, v, [2, 2, 0, 0, 0], patient_options=options)
    sol = {0: 0, 1: 1}
    os.environ.setdefault("MPLCONFIGDIR", str(ROOT / ".cache/matplotlib"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from optimiseur.plotting import plot_occupation_lits
    compatibility = {"solution_to_dataframe_rows": len(solution_to_dataframe(problem, sol)),
                     "legacy_bed_plot_accepts_full_stay_problem": False,
                     "legacy_reconstruction_accepts_extended_capacity": False}
    try:
        plot_occupation_lits(problem, sol)
    except ValueError as exc:
        compatibility["plot_error"] = str(exc)
    else:
        raise AssertionError("Expected legacy n_days plot horizon mismatch")
    finally:
        plt.close("all")
    try:
        clone = PlanningProblem(p, v, lits_capacity=problem._lits_capacity_arr, patient_options=options)
        clone.fitness(sol)
    except ValueError as exc:
        compatibility["reconstruction_error"] = str(exc)
    else:
        raise AssertionError("Expected legacy reconstruction horizon mismatch")
    write_json(output / "integration_probes.json", compatibility)
    workloads = {w["workload_seed"]: w for w in json.loads((OLD / "workloads.json").read_text())}
    saved = [json.loads(line) for line in (OLD / "schedules.jsonl").read_text().splitlines()]
    barriers = []
    for s in saved:
        if s["arm"] != "C_full_feasibility_first" or s["validation"]["feasible"]:
            continue
        w = workloads[s["workload_seed"]]
        problem = FullStayPlanningProblem(pd.DataFrame(w["patients"]), pd.DataFrame(w["sessions"]),
                 w["bed_capacities"], patient_options=w["patient_options"], objective_mode="feasibility_first")
        final = {int(i): j for i, j in s["final_assignment"].items()}
        score = problem.fitness(final)
        min_feasible_barrier, min_improving_barrier = None, None
        path_checks = 0
        # Count all paths (not deduplicated states) to establish the minimum
        # first-step barrier within TWO moves, not merely one found path.
        for first in neighbors(problem, final):
            first_score = problem.fitness(first)
            barrier = max(0.0, score - first_score)
            for second in neighbors(problem, first):
                path_checks += 1
                if path_checks > 20000:
                    raise AssertionError("Declared two-move path bound exceeded")
                second_score = problem.fitness(second)
                if second_score > score:
                    min_improving_barrier = barrier if min_improving_barrier is None else min(min_improving_barrier, barrier)
                if problem.violations(second) == (0.0, 0.0):
                    min_feasible_barrier = barrier if min_feasible_barrier is None else min(min_feasible_barrier, barrier)
        barriers.append({"workload_seed": s["workload_seed"], "solver_seed": s["solver_seed"],
                         "all_two_move_paths_checked": path_checks,
                         "minimum_first_step_cost_increase_for_feasible_two_move_path": min_feasible_barrier,
                         "minimum_first_step_cost_increase_for_improving_two_move_path": min_improving_barrier,
                         "scope": "Exhaustive two-move paths only; longer plateau paths may exist."})
    write_json(output / "two_move_barriers.json", barriers)
    write_json(output / "manifest.json", {"protocol": "s1-s2-review-audit-v1", "status": "complete",
        "source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "output_sha256": {p.name: sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}})
    print(json.dumps({"confirmed_bug": bug, "integration": compatibility, "barriers": barriers}, indent=2))


if __name__ == "__main__":
    main()
