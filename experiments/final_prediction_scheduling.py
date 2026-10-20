"""Bounded paired OR-prediction experiment. Aggregate outputs ONLY.

This is an OR-only static scheduling experiment, NOT a prospective trial or a
test of ward congestion. LOS is fixed to one day and 30 explicitly available
beds make the <=30-case daily cohorts nonbinding. No witness/outcomes guide SA.
"""
import argparse
import asyncio
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
from time import monotonic

import joblib
import numpy as np
import pandas as pd

from prediction.consultation_features import consultation_inputs
from prediction.surgery_duration import predict_schedule_loaded, validate_split
from hospital_sim.domain import CaseInput, SimulationConfig
from hospital_sim.historical_data import DailyScenario
from hospital_sim.instances import opening_request
from hospital_sim.room_problem import RoomAllocationProblem
from hospital_sim.simulation import run_day
from optimiseur.optimizer import simulated_annealing
from optimiseur.search_control import SearchControl


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def eligible_join(dataset, eda):
    """Unique patient/day matching; ambiguous keys are excluded, never averaged."""
    left = dataset.copy()
    right = eda.copy()
    left["_patient"] = left.split_patient_id.astype("string")
    right["_patient"] = right.id_patient.astype("string")
    left["_day"] = pd.to_datetime(left.split_event_date).dt.normalize()
    right["_day"] = pd.to_datetime(right.date_inter).dt.normalize()
    keys = ["_patient", "_day"]
    left_dup = left.duplicated(keys, keep=False)
    right_dup = right.duplicated(keys, keep=False)
    # Keep only split/target metadata on the left; raw covariates come from EDA.
    a = left.loc[~left_dup, keys + ["split", "target_surgery_duration_min"]]
    b = right.loc[~right_dup]
    merged = a.merge(b, on=keys, how="inner", validate="one_to_one")
    # Target agreement verifies matching provenance; never used to rank/select.
    agreement = np.isclose(merged.target_surgery_duration_min, merged.room_duration_min)
    if not agreement.all():
        raise ValueError("Raw/model target mismatch; do not run scheduling comparison")
    return merged, {"model_ambiguous_rows": int(left_dup.sum()),
                    "eda_ambiguous_rows": int(right_dup.sum()),
                    "matched_rows": len(merged), "target_agreement": bool(agreement.all())}


async def campaign(frame, models, output):
    # Predeclared design; dates chosen by calendar and cohort size, never outcomes.
    test = frame.loc[frame.split.eq("test")].copy()
    counts = test.groupby("_day").size()
    days = list(counts.loc[counts.ge(8)].sort_index().index[:8])
    if not days:
        raise ValueError("No eligible held-out daily cohorts")
    cohorts = []
    for day in days:
        cohort = test.loc[test._day.eq(day)].sort_values("no_cas").head(30).reset_index(drop=True)
        cohorts.append(cohort)
    raw = pd.concat(cohorts, ignore_index=True)
    raw_inputs = consultation_inputs(raw)
    predictions = {name: predict_schedule_loaded(raw_inputs, saved, raw=True).duration_point_min.to_numpy()
                   for name, saved in models.items()}
    actual = raw.room_duration_min.to_numpy(float)
    rows, offset = [], 0
    for cohort_number, cohort in enumerate(cohorts):
        count = len(cohort)
        for rooms in (1, 2):
            config = SimulationConfig(rooms=rooms, opening=480, closing=960, turnover=15)
            for seed in (7101, 7102):
                # Identical positional allocation in each arm, independent of predictions.
                initial = {i: i % rooms for i in range(count)}
                for arm in ("median", "ml"):
                    point = predictions[arm][offset:offset+count]
                    cases = tuple(CaseInput(f"case-{i:04d}", "ELIGIBLE", int(ceil(p)), 1)
                                  for i, p in enumerate(point))
                    realized = {case.case_id: float(value) for case, value in zip(cases, actual[offset:offset+count])}
                    scenario = DailyScenario(cohort._day.iloc[0].date(), cases, realized,
                                             {case.case_id: 1 for case in cases})
                    start = monotonic()
                    request = opening_request(scenario, config, monotonic()+10)
                    problem = RoomAllocationProblem(request)
                    control = SearchControl(max_evaluations=500, deadline=monotonic()+10)
                    result = simulated_annealing(problem, seed=seed, T0=1., alpha=.95,
                        n_iter=500, initial_solution=initial, control=control)
                    schedule = problem.decode(control.best)
                    elapsed = monotonic()-start
                    report = {"elapsed_seconds": elapsed, "evaluations": control.evaluations,
                              "stop_reason": control.reason}
                    outcome = await run_day(scenario, config, policy="static",
                                            initial_schedule=schedule, initial_report=report)
                    metric = outcome["metrics"]
                    if metric["failures"] or metric["cases"] != metric["completed"]+metric["unstarted"]:
                        raise ValueError("Schedule validation/execution failure")
                    # Independent interval/capacity diagnostics, not optimizer fitness.
                    predicted_over = 0
                    for room in config.room_ids:
                        assignments = sorted((a for a in schedule.assignments if a.room_id == room), key=lambda a:a.start)
                        last = config.opening
                        for assignment in assignments:
                            if assignment.start < last:
                                raise ValueError("Independent predicted room-overlap check failed")
                            last = assignment.start+assignment.duration+config.turnover
                        predicted_over += max(0, last-config.closing)
                    row = {"cohort": cohort_number, "rooms": rooms, "solver_seed": seed, "arm": arm,
                           "predicted_or_overtime_minutes": predicted_over,
                           "predicted_all_cases_no_overtime": not schedule.unassigned and predicted_over == 0,
                           "bed_capacity": 30, "fixed_inclusive_los_days": 1, "bed_overload": 0,
                           "evaluations": control.evaluations, "termination": control.reason,
                           "run_seconds": monotonic()-start, **metric}
                    rows.append(row)
        offset += count
    table = pd.DataFrame(rows)
    table.to_csv(output/"scheduling_runs.csv", index=False)
    measures = ["completed", "unstarted", "overtime_minutes_including_turnover",
                "total_start_delay_minutes", "solver_seconds", "run_seconds",
                "predicted_or_overtime_minutes", "predicted_all_cases_no_overtime"]
    summary = table.groupby(["rooms", "arm"])[measures].mean().reset_index()
    summary.to_csv(output/"scheduling_summary.csv", index=False)
    # Group search seeds within cohort before comparing; no false hospital n=64.
    grouped = table.groupby(["cohort", "rooms", "arm"])[measures].mean().unstack("arm")
    differences = pd.DataFrame({name: grouped[name]["ml"]-grouped[name]["median"] for name in measures})
    differences.reset_index().to_csv(output/"cohort_paired_differences.csv", index=False)
    evaluation = {arm: {"mae": float(np.mean(abs(p-actual))), "bias": float(np.mean(p-actual))}
                  for arm, p in predictions.items()}
    return {"cohorts": len(cohorts), "unique_cases": len(raw), "runs": len(table),
            "cohort_prediction_errors_minutes": evaluation,
            "cohort_sha256": sha256(raw[["_patient", "_day"]].to_csv(index=False).encode()).hexdigest(),
            "summary": summary.to_dict("records"),
            "paired_delta_ml_minus_median": differences.groupby(level="rooms").mean().reset_index().to_dict("records"),
            "bed_scope": "Fixed 1-day LOS and explicitly available 30 beds; nonbinding, no ward outcome claim"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error("Output must be new or empty")
    dataset_path = args.source/"resources/model_surgery_duration_dataset.parquet"
    eda_path = args.source/"resources/donnees_bloc_pretraitees.parquet"
    dataset, eda = pd.read_parquet(dataset_path), pd.read_parquet(eda_path)
    validate_split(dataset)
    joined, quality = eligible_join(dataset, eda)
    paths = {"median": args.artifacts/"room_consultation_baseline_2026-10-20_v1.joblib",
             "ml": args.artifacts/"room_consultation_selected_2026-10-20_v1.joblib"}
    models = {name: joblib.load(path) for name,path in paths.items()}
    # Verify raw preprocessing separately on the entire uniquely matched test set.
    test = joined.loc[joined.split.eq("test")].copy()
    lookup = dataset.assign(_patient=dataset.split_patient_id.astype("string"),
                            _day=pd.to_datetime(dataset.split_event_date).dt.normalize())
    prepared = test[["_patient", "_day"]].merge(lookup, on=["_patient", "_day"], validate="one_to_one")
    parity = {}
    for name, saved in models.items():
        raw_point = predict_schedule_loaded(consultation_inputs(test), saved, raw=True).duration_point_min.to_numpy()
        prepared_point = predict_schedule_loaded(prepared, saved, raw=False).duration_point_min.to_numpy()
        error = abs(raw_point-prepared_point)
        parity[name] = {"n": len(error), "max_abs_difference": float(error.max()),
                        "mean_abs_difference": float(error.mean())}
        if not np.allclose(raw_point, prepared_point, atol=1e-6):
            raise ValueError("Raw/prepared inference mismatch; experiment blocked")
    manifest = {"source_sha256": digest(__file__), "input_sha256": {"dataset": digest(dataset_path), "eda": digest(eda_path)},
                "artifact_sha256": {name:digest(path) for name,path in paths.items()},
                "design": {"cohorts": "first 8 chronological heldout dates with >=8 unique matched cases; cap30 by source ID",
                "rooms": [1,2], "opening":480, "closing":960, "turnover":15,
                "seeds":[7101,7102], "evaluations":500, "per_search_seconds":10,
                "policy":"static", "initial_allocation":"positional round robin identical between arms",
                "limitations":"Retrospective recorded codes assumed consultation-available; no prospective verification; fixed LOS"},
                "join_quality":quality, "raw_prepared_parity":parity}
    (args.output/"manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")
    report = asyncio.run(campaign(joined,models,args.output))
    (args.output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    main()
