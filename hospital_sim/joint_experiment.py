"""Compare median, learned and oracle durations with rooms plus cross-day beds.

Run from the repository root. Historical episodes become available on their
recorded day; waiting episodes carry to the next operating day. A bed is
reserved only when a case actually starts. Discharges use hidden observed LOS.
"""

import argparse
import asyncio
import csv
from dataclasses import asdict, replace
from datetime import date
from importlib.metadata import version
import json
from pathlib import Path
import platform

import pandas as pd

from .domain import Outage, SimulationConfig
from .experiment import git_metadata, minute, plan_initial
from .historical_data import DailyScenario, load_historical
from .instances import with_duration_mode
from .metaheuristics import METHODS, MetaheuristicScheduler, SearchSettings
from .predictions import load_model_predictions
from .simulation import run_day
from .ward import HospitalWardModel, WardDay


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--input", type=Path, default=Path("resources/donnees_bloc_nettoyees.xlsx"))
    cli.add_argument("--eda-input", type=Path, default=Path("resources/donnees_bloc_pretraitees.parquet"))
    cli.add_argument("--surgery-data", type=Path, default=Path("resources/model_surgery_duration_dataset.parquet"))
    cli.add_argument("--room-model", type=Path, default=Path("artifacts/ml-models/surgery_duration_model.joblib"))
    cli.add_argument("--los-model", type=Path, default=Path("artifacts/ml-models/los_regressor.joblib"))
    cli.add_argument("--date-range", nargs=2, required=True, type=date.fromisoformat, metavar=("START", "END"))
    cli.add_argument("--cohort", choices=["model_test", "all_2022"], default="model_test")
    cli.add_argument("--bed-capacity", type=int, default=10)
    cli.add_argument("--rooms", type=int, default=2)
    cli.add_argument("--opening", type=minute, default=480)
    cli.add_argument("--closing", type=minute, default=1020)
    cli.add_argument("--turnover", type=int, default=15)
    cli.add_argument("--scenario", choices=["no_outage", "outage"], default="outage")
    cli.add_argument("--outage-room", default="room-1")
    cli.add_argument("--outage-start", type=minute, default=600)
    cli.add_argument("--outage-end", type=minute, default=720)
    cli.add_argument("--policies", nargs="+", choices=["static", "reactive"], default=["reactive"])
    cli.add_argument("--modes", nargs="+", choices=["median", "model", "oracle"],
                     default=["median", "model", "oracle"])
    cli.add_argument("--methods", nargs="+", choices=METHODS, default=["baseline"])
    cli.add_argument("--seeds", nargs="+", type=int, default=[0])
    cli.add_argument("--room-risk", choices=["point", "p80", "p95"], default="point")
    cli.add_argument("--los-risk", choices=["point", "upper"], default="point")
    cli.add_argument("--max-evaluations", type=int, default=500)
    cli.add_argument("--solver-budget", type=float, default=30.0)
    cli.add_argument("--output", type=Path, default=Path("artifacts/joint-mesa"))
    return cli


def _heldout_source_keys(eda_path: Path, surgery_data: Path) -> set[int]:
    """Restrict all modes to the same patient-disjoint 2022 model test cohort."""
    eda = pd.read_parquet(eda_path, columns=["no_cas", "id_patient", "date_inter"])
    surgery = pd.read_parquet(surgery_data,
                              columns=["split", "split_patient_id", "split_event_date"])
    test = surgery.loc[surgery["split"].eq("test"),
                       ["split_patient_id", "split_event_date"]].drop_duplicates()
    merged = eda.merge(test, left_on=["id_patient", "date_inter"],
                       right_on=["split_patient_id", "split_event_date"], how="inner")
    if merged.empty or not merged["no_cas"].is_unique:
        raise ValueError("The model test cohort cannot be mapped uniquely to EDA cases")
    return set(merged["no_cas"].astype(int))


def _daily_scenarios(data, days, eligible) -> list[DailyScenario]:
    scenarios, serial = [], 0
    for day in days:
        source = data.scenario(day)
        cases, room, los, source_ids, preop_days = [], {}, {}, {}, {}
        for case in source.cases:
            if eligible is not None and source.source_ids[case.case_id] not in eligible:
                continue
            serial += 1
            identifier = f"episode-{serial:05d}"
            cases.append(replace(case, case_id=identifier))
            room[identifier] = source.realized_minutes[case.case_id]
            los[identifier] = source.realized_los_days[case.case_id]
            source_ids[identifier] = source.source_ids[case.case_id]
            preop_days[identifier] = source.preop_days[case.case_id]
        scenarios.append(DailyScenario(day, tuple(cases), room, los, source_ids, preop_days))
    if not any(scenario.cases for scenario in scenarios):
        raise ValueError("Selected period has no cases in the chosen cohort")
    return scenarios


async def _run_one(args, days, originals, predictions, mode, policy, method, seed, config):
    scenarios = [
        predictions.apply(item, args.room_risk, args.los_risk)
        if mode == "model" else with_duration_mode(item, mode)
        for item in originals
    ]
    ward = HospitalWardModel(scenarios, args.bed_capacity)
    daily, room_details = [], []
    for day in days:
        arrivals, discharged, occupied_before = ward.advance_day(day)
        offered = ward.offer()
        room_result = None
        if offered:
            day_scenario = ward.daily_scenario(day, offered)
            settings = SearchSettings(method, seed, args.max_evaluations, "evaluations")
            initial, initial_report = await plan_initial(day_scenario, config, settings, args.solver_budget)
            room_result = await run_day(day_scenario, config, policy,
                                        MetaheuristicScheduler(settings), args.solver_budget,
                                        initial_schedule=initial, initial_report=initial_report)
            started = ward.accept_execution(day, offered, room_result["executed_schedule"])
            metrics = room_result["metrics"]
            room_details.append(room_result)
        else:
            started = 0
            metrics = {"overtime_minutes_including_turnover": 0,
                       "replanning_count": 0, "failures": 0, "search_failures": 0}
        daily.append(WardDay(
            day, arrivals, discharged, occupied_before,
            args.bed_capacity - occupied_before, len(offered), started,
            sum(agent.status == "waiting" for agent in ward.episodes.values()),
            ward.occupied, metrics["overtime_minutes_including_turnover"],
            metrics["replanning_count"], metrics["failures"] + metrics.get("search_failures", 0),
        ))
    summary = ward.summary(days[-1])
    summary.update(mode=mode, policy=policy, method=method, seed=seed,
                   scenario=args.scenario, operating_days=len(days), bed_capacity=args.bed_capacity,
                   overtime_minutes=sum(day.overtime_minutes for day in daily),
                   room_replans=sum(day.room_replans for day in daily),
                   room_failures=sum(day.room_failures for day in daily))
    return summary, {"daily": [asdict(day) for day in daily], "room_runs": room_details}


async def execute(args):
    if args.bed_capacity < 1 or args.max_evaluations < 1 or args.solver_budget <= 0:
        raise ValueError("Bed capacity, evaluation budget and solver budget must be positive")
    start, end = args.date_range
    if start > end or start.year != 2022 or end.year != 2022:
        raise ValueError("Choose an ordered date range within held-out 2022")
    data = load_historical(args.input)
    if data.quality["missing_or_invalid_postop_los_rows"]:
        raise ValueError("Cross-day bed evaluation requires admission and discharge dates")
    days = [day for day in data.dates if start <= day <= end]
    if not days:
        raise ValueError("Selected range has no operating dates")
    eligible = (_heldout_source_keys(args.eda_input, args.surgery_data)
                if args.cohort == "model_test" else None)
    originals = _daily_scenarios(data, days, eligible)
    predictions = load_model_predictions(args.eda_input, args.room_model, args.los_model)
    outage = (Outage(args.outage_room, args.outage_start, args.outage_end)
              if args.scenario == "outage" else None)
    config = SimulationConfig(args.rooms, args.opening, args.closing, args.turnover, outage)
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError("Output directory must be empty")
    manifest = {
        "dataset_sha256": data.fingerprint,
        "prediction_artifacts_sha256": predictions.fingerprints,
        "code": git_metadata(),
        "python": platform.python_version(),
        "dependencies": {name: version(name) for name in (
            "mesa", "pandas", "numpy", "scikit-learn", "xgboost", "catboost", "joblib")},
        "data_quality": data.quality,
        "cohort": args.cohort, "date_range": [start.isoformat(), end.isoformat()],
        "operating_dates": len(days), "cases": sum(len(item.cases) for item in originals),
        "config": asdict(config), "bed_capacity": args.bed_capacity,
        "room_risk": args.room_risk, "los_risk": args.los_risk,
        "methods": args.methods, "seeds": args.seeds, "modes": args.modes, "policies": args.policies,
        "assumptions": [
            "Every historical case is ready on its recorded date; unstarted cases carry to the next operating day.",
            "The ward starts empty; no prior admissions are reconstructed.",
            "Every surgery consumes one bed from its start day through inclusive observed postoperative stay; discharge occurs on the following date.",
            "The LOS model predicts total admission-to-discharge days; known preoperative days are subtracted for postoperative bed planning.",
            "Only current occupancy and predicted LOS order waiting cases; actual LOS is revealed through discharge.",
            "Earlier arrivals have priority; within an arrival cohort shorter predicted LOS is offered first.",
            "Daily room planning uses the existing coordinator and search methods; the ward offers at most currently free beds.",
            "Operating rooms open only on dates with recorded interventions; weekends and missing dates still count toward LOS.",
            "2022 outcomes never enter model features or optimizer-visible case inputs, except in the labeled oracle mode.",
            "The oracle is an information benchmark, not a guaranteed optimum of the room/bed admission policy.",
        ],
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    for method in dict.fromkeys(args.methods):
        for seed in sorted(set(args.seeds)):
            for policy in dict.fromkeys(args.policies):
                for mode in dict.fromkeys(args.modes):
                    row, details = await _run_one(args, days, originals, predictions,
                                                  mode, policy, method, seed, config)
                    rows.append(row)
                    stem = f"{method}-{seed}-{policy}-{mode}"
                    (args.output / f"{stem}.json").write_text(json.dumps(details, indent=2, default=str) + "\n")
                    print(f"{stem}: {row['surgeries_completed']}/{row['cases']} surgeries, "
                          f"{row['never_started']} waiting, {row['overtime_minutes']} overtime min", flush=True)
    oracle = {(row["method"], row["seed"], row["policy"]): row
              for row in rows if row["mode"] == "oracle"}
    for row in rows:
        reference = oracle.get((row["method"], row["seed"], row["policy"]))
        row["completed_gap_to_oracle"] = (reference["surgeries_completed"] - row["surgeries_completed"]
                                            if reference else None)
        row["overtime_difference_to_oracle"] = (row["overtime_minutes"] - reference["overtime_minutes"]
                                                  if reference else None)
    with (args.output / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main():
    cli = parser()
    args = cli.parse_args()
    try:
        asyncio.run(execute(args))
    except (ValueError, OSError) as exc:
        cli.error(str(exc))


if __name__ == "__main__":
    main()
