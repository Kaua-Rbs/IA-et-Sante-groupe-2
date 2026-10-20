"""Replay independent validation of saved synthetic S1/S2 results, read only."""
import argparse
import csv
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd

from optimiseur.validation import validate_full_stay


def verify(output):
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "complete":
        raise ValueError("Campaign is incomplete")
    for filename, expected in manifest["outputs_sha256"].items():
        assert sha256((output / filename).read_bytes()).hexdigest() == expected, filename
    for filename, expected in manifest["source_sha256"].items():
        assert sha256((output / "source" / filename).read_bytes()).hexdigest() == expected, filename
    workloads = {w["workload_seed"]: w for w in json.loads((output / "workloads.json").read_text(encoding="utf-8"))}
    with (output / "runs.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    saved = [json.loads(line) for line in (output / "schedules.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len(saved) == 180
    index = {(int(r["workload_seed"]), int(r["solver_seed"]), r["arm"]): r for r in rows}
    assert len(index) == 180
    incumbents = 0
    for schedule in saved:
        key = (schedule["workload_seed"], schedule["solver_seed"], schedule["arm"])
        row, workload = index[key], workloads[key[0]]
        patients, sessions = pd.DataFrame(workload["patients"]), pd.DataFrame(workload["sessions"])
        def validate(solution):
            return validate_full_stay(patients, sessions, workload["bed_capacities"],
                                     {int(i): int(j) for i, j in solution.items()}, workload["patient_options"])
        result = validate(schedule["final_assignment"])
        assert result.valid and result.missing_cases == 0
        assert result.feasible == bool(int(row["feasible"]))
        assert result.or_overload_minutes == float(row["or_overload_minutes"])
        assert result.bed_overload_days == float(row["bed_overload_days"])
        assert result.tail_bed_overload_days == float(row["tail_bed_overload_days"])
        assert abs(result.balance_minutes - float(row["balance_minutes"])) < 1e-9
        assert schedule["initial_assignment"] == workload["initial_assignments"][str(key[1])]
        assert int(row["evaluations"]) == manifest["evaluations_including_initialization"]
        assert row["termination_reason"] == "evaluations"
        if row["first_feasible_evaluation"]:
            assert 1 <= int(row["first_feasible_evaluation"]) <= int(row["evaluations"])
        if schedule["best_feasible_assignment"] is not None:
            incumbent = validate(schedule["best_feasible_assignment"])
            assert incumbent.feasible
            assert abs(incumbent.balance_minutes - float(row["best_feasible_balance_minutes"])) < 1e-9
            incumbents += 1
    return {"primary_schedules_checked": len(saved), "feasible_incumbents_checked": incumbents,
            "hashes_verified": True, "equal_complete_budgets": True, "identical_starts": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.output), indent=2))
