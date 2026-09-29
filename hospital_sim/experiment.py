"""CLI: python -m hospital_sim.experiment --help."""

import argparse
import asyncio
import csv
from dataclasses import asdict, replace
from datetime import date
from hashlib import sha256
from importlib.metadata import version
import json
from math import isfinite
from pathlib import Path
import platform
import subprocess
from time import monotonic

from .domain import Outage, Schedule, SimulationConfig
from .historical_data import load_historical
from .instances import exact_reference, opening_request, sampled_scenario, scale_rooms, small_reference, with_duration_mode
from .metaheuristics import METHODS, MetaheuristicScheduler, SearchSettings
from .room_problem import RoomAllocationProblem
from .simulation import run_day


def minute(value):
    try:
        hour, minutes = map(int, value.split(":"))
        if not (0 <= hour <= 24 and 0 <= minutes < 60 and (hour < 24 or minutes == 0)):
            raise ValueError
        return hour * 60 + minutes
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected HH:MM between 00:00 and 24:00") from exc


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--input", type=Path, default=Path("resources/donnees_bloc_nettoyees.xlsx"))
    selection = result.add_mutually_exclusive_group()
    selection.add_argument("--dates", nargs="+", type=date.fromisoformat)
    selection.add_argument("--date-range", nargs=2, type=date.fromisoformat, metavar=("START", "END"))
    selection.add_argument("--small-reference", action="store_true",
                           help="Seven synthetic cases; use --closing 11:00 --outage-start 09:00 --outage-end 10:00")
    selection.add_argument("--synthetic-cases", nargs="+", type=int,
                           help="Sample larger held-out workloads; room count scales to target load")
    result.add_argument("--duration-mode", choices=["median", "oracle"], default="median",
                        help="median: historical estimates (fixture estimates for small reference); "
                             "oracle: perfect knowledge of realized room occupancy, not an ML prediction")
    result.add_argument("--instance-seeds", nargs="+", type=int, default=[0])
    result.add_argument("--target-load", type=float, default=0.8)
    result.add_argument("--rooms", type=int, default=2, help="Room count for historical/small instances")
    result.add_argument("--opening", type=minute, default=480)
    result.add_argument("--closing", type=minute, default=1020)
    result.add_argument("--turnover", type=int, default=15)
    result.add_argument("--outage-room", default="room-1")
    result.add_argument("--outage-start", type=minute, default=600)
    result.add_argument("--outage-end", type=minute, default=720)
    result.add_argument("--scenarios", choices=["both", "no_outage", "outage"], default="both")
    result.add_argument("--policy", choices=["both", "static", "reactive"], default="both")
    result.add_argument("--methods", nargs="+", choices=METHODS, default=["baseline"])
    result.add_argument("--seeds", nargs="+", type=int, default=[0])
    result.add_argument("--max-evaluations", type=int, default=5000)
    result.add_argument("--budget-mode", choices=["evaluations", "time"], default="evaluations")
    result.add_argument("--solver-budget", type=float, default=5.0,
                       help="End-to-end seconds per request; also a safety deadline in evaluation mode")
    result.add_argument("--output", type=Path, default=Path("artifacts/mesa"))
    return result


def git_metadata():
    root = Path(__file__).resolve().parent.parent
    digest = sha256()
    paths = sorted((root / "hospital_sim").glob("*.py"))
    paths += sorted((root / "optimiseur").glob("*.py")) + [root / "requirements.txt"]
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, None
    return {"commit": commit, "dirty": dirty, "implementation_sha256": digest.hexdigest()}


def select_instances(args, data, base):
    if args.small_reference:
        return [("small-reference", small_reference(), base, {"kind": "exact_reference"})]
    if args.synthetic_cases:
        instances = []
        for count in sorted(set(args.synthetic_cases)):
            for seed in sorted(set(args.instance_seeds)):
                scenario = sampled_scenario(data, count, seed)
                config = scale_rooms(base, scenario, args.target_load)
                instances.append((f"sample-{count}-{seed}", scenario, config, {
                    "kind": "sampled_2022_cases", "instance_seed": seed, "target_load": args.target_load,
                }))
        return instances
    available = data.dates
    if not available:
        raise ValueError("No eligible cases in 2022")
    if args.dates:
        days = sorted(set(args.dates))
        if any(day not in available for day in days):
            raise ValueError("Every selected date must have eligible cases in 2022")
    elif args.date_range:
        start, end = args.date_range
        if start > end or start.year != 2022 or end.year != 2022:
            raise ValueError("Date range must be ordered and within 2022")
        days = [day for day in available if start <= day <= end]
        if not days:
            raise ValueError("No eligible cases in selected range")
    else:
        days = [available[0]]
    return [(str(day), data.scenario(day), base, {"kind": "historical_day"}) for day in days]


def configs_for(args, base):
    configs = []
    if args.scenarios in ("both", "no_outage"):
        configs.append(base)
    if args.scenarios in ("both", "outage"):
        configs.append(replace(base, outage=Outage(args.outage_room, args.outage_start, args.outage_end)))
    return configs


async def plan_initial(scenario, config, settings, seconds):
    started = monotonic()
    request = opening_request(scenario, config, started + seconds)
    scheduler = MetaheuristicScheduler(settings)
    try:
        proposal = await asyncio.wait_for(scheduler.propose(request), max(0, request.deadline - monotonic()))
    except asyncio.TimeoutError:
        proposal = None
    except Exception as exc:
        # A failed optimizer must not abort the remaining comparison runs.
        proposal = None
        if scheduler.reports:
            scheduler.reports[-1]["error_type"] = type(exc).__name__
    schedule = proposal.schedule if proposal else Schedule((), tuple(c.case_id for c in scenario.cases))
    report = dict(scheduler.reports[-1]) if scheduler.reports else {
        "method": settings.method, "seed": settings.seed, "evaluations": 0, "history": [],
    }
    if proposal is None:
        report["stop_reason"] = "initial_failure"
    report["elapsed_seconds"] = monotonic() - started
    report["objective"] = asdict(RoomAllocationProblem(request).objective(schedule))
    return schedule, report


async def execute(args):
    if not isfinite(args.solver_budget) or args.solver_budget <= 0:
        raise ValueError("Solver budget must be finite and positive")
    if args.max_evaluations < 1:
        raise ValueError("Evaluation budget must be positive")
    base = SimulationConfig(args.rooms, args.opening, args.closing, args.turnover)
    data = None if args.small_reference else load_historical(args.input)
    # Size generated resources from the original estimates in BOTH modes.
    instances = [(key, with_duration_mode(scenario, args.duration_mode), config, metadata)
                 for key, scenario, config, metadata in select_instances(args, data, base)]
    policies = ["static", "reactive"] if args.policy == "both" else [args.policy]
    methods, seeds = list(dict.fromkeys(args.methods)), sorted(set(args.seeds))
    configurations = {key: configs_for(args, config) for key, _, config, _ in instances}
    references = {}
    if args.small_reference:
        key, scenario, config, _ = instances[0]
        references[key] = exact_reference(opening_request(scenario, config, float("inf")))
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError("Output directory must be empty; choose a new --output path")
    manifest = {
        "duration_mode": args.duration_mode,
        "duration_information": (
            "Perfect knowledge: scheduling estimates equal realized room occupancy; not an ML prediction."
            if args.duration_mode == "oracle" else
            "Synthetic fixture estimates." if args.small_reference else
            "2019–2021 procedure medians with overall training-median fallback."),
        "generated_room_sizing": "Original median estimates, before applying duration mode.",
        "dataset_sha256": data.fingerprint if data else None, "code": git_metadata(),
        "dependencies": {name: version(name) for name in ("mesa", "pandas", "numpy", "openpyxl", "networkx", "scipy")},
        "python": platform.python_version(), "data_quality": data.quality if data else {"source": "synthetic reference"},
        "dates": [scenario.date.isoformat() for _, scenario, _, _ in instances],
        "policies": policies, "methods": methods, "seeds": seeds,
        "instances": {key: {**metadata, "cases": len(scenario.cases),
                           "configurations": [asdict(c) for c in configurations[key]]}
                      for key, scenario, _, metadata in instances},
        "solver_budget_seconds": args.solver_budget, "max_evaluations": args.max_evaluations,
        "budget_mode": args.budget_mode, "simulation_seed": 0, "step_minutes": 1,
        "objective": "unstarted, then predicted overtime including turnover, then changed waiting assignments",
        "exact_references": references,
        "assumptions": [
            "Cases are ready at opening; identical synthetic rooms; no staff, beds or specialty constraints.",
            ("Oracle deliberately exposes realized durations as scheduling estimates; future closures remain hidden."
             if args.duration_mode == "oracle" else
             "Fixture estimates are used; realized durations are private to execution."
             if args.small_reference else
             "Predictions use 2019–2021 medians; held-out durations are private to execution."),
            "Sampled stress instances resample complete 2022 case rows with replacement.",
            "Durations round up to whole minutes and stay unchanged under rescheduling.",
            "Closures forbid starts; ongoing cases finish. Closure and reopening are revealed at closure start.",
            "Simulation pauses during optimization; no new starts at closing.",
            "One saved initial plan per instance/method/seed is shared across all four policy/scenario combinations.",
            "Evaluation mode still has a safety deadline; truncated runs are labeled by their stopping reason.",
        ],
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    for key, scenario, config, _ in instances:
        for method in methods:
            for seed in seeds:
                settings = SearchSettings(method, seed, args.max_evaluations, args.budget_mode)
                initial, initial_report = await plan_initial(scenario, config, settings, args.solver_budget)
                initial_record = {
                    "duration_mode": args.duration_mode,
                    "schedule": asdict(initial), "report": initial_report,
                    "exact_objective_gap": (
                        initial_report["objective"]["cost"] - references[key]["objective"]["cost"]
                        if key in references else None),
                }
                (args.output / f"{key}-{method}-{seed}-initial.json").write_text(
                    json.dumps(initial_record, indent=2) + "\n")
                for execution_config in configurations[key]:
                    for policy in policies:
                        scheduler = MetaheuristicScheduler(settings)
                        result = await run_day(
                            scenario, execution_config, policy, scheduler, args.solver_budget,
                            initial_schedule=initial, initial_report=initial_report,
                        )
                        result.update(instance_id=key, method=method, seed=seed, duration_mode=args.duration_mode)
                        stem = f"{key}-{method}-{seed}-{result['scenario']}-{policy}"
                        (args.output / f"{stem}.json").write_text(json.dumps(result, indent=2) + "\n")
                        row = {k: result[k] for k in ("instance_id", "date", "method", "seed", "scenario", "policy", "duration_mode")}
                        row.update(result["metrics"])
                        row["initial_objective_gap"] = initial_record["exact_objective_gap"]
                        rows.append(row)
                        print(f"{stem}: completed={row['completed']}/{row['cases']}, "
                              f"overtime={row['overtime_minutes_including_turnover']} min, "
                              f"failures={row['failures'] + row['search_failures']}", flush=True)
    with (args.output / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    if data:
        print(f"Data: {data.quality['usable_rows']} usable; {data.quality['excluded_rows']} excluded.")
    print(f"Results: {args.output}")
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
