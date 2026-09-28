"""CLI: python -m hospital_sim.experiment --help."""

import argparse
import asyncio
import csv
from dataclasses import asdict, replace
from datetime import date
from importlib.metadata import version
from hashlib import sha256
from math import isfinite
import json
from pathlib import Path
import platform
import subprocess

from .domain import Outage, SimulationConfig
from .historical_data import load_historical
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
    result.add_argument("--rooms", type=int, default=2)
    result.add_argument("--opening", type=minute, default=480)
    result.add_argument("--closing", type=minute, default=1020)
    result.add_argument("--turnover", type=int, default=15)
    result.add_argument("--outage-room", default="room-1")
    result.add_argument("--outage-start", type=minute, default=600)
    result.add_argument("--outage-end", type=minute, default=720)
    result.add_argument("--scenarios", choices=["both", "no_outage", "outage"], default="both")
    result.add_argument("--policy", choices=["both", "static", "reactive"], default="both")
    result.add_argument("--solver-budget", type=float, default=5.0)
    result.add_argument("--output", type=Path, default=Path("artifacts/mesa"))
    return result


def git_metadata():
    root = Path(__file__).resolve().parent.parent
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip())
        digest = sha256()
        paths = sorted((root / "hospital_sim").glob("*.py")) + [root / "requirements.txt"]
        for path in paths:
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
        return {"commit": commit, "dirty": dirty, "implementation_sha256": digest.hexdigest()}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


async def execute(args):
    data = load_historical(args.input)
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
    base = SimulationConfig(args.rooms, args.opening, args.closing, args.turnover)
    configs = []
    if args.scenarios in ("both", "no_outage"):
        configs.append(base)
    if args.scenarios in ("both", "outage"):
        configs.append(replace(base, outage=Outage(args.outage_room, args.outage_start, args.outage_end)))
    policies = ["static", "reactive"] if args.policy == "both" else [args.policy]
    if not isfinite(args.solver_budget) or args.solver_budget <= 0:
        raise ValueError("Solver budget must be finite and positive")
    # Refuse to overwrite a previous experiment.
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        raise ValueError("Output directory must be empty; choose a new --output path")
    manifest = {
        "dataset_sha256": data.fingerprint, "code": git_metadata(),
        "dependencies": {name: version(name) for name in ("mesa", "pandas", "numpy", "openpyxl", "networkx", "scipy")},
        "python": platform.python_version(), "data_quality": data.quality,
        "dates": [day.isoformat() for day in days], "policies": policies,
        "configurations": [asdict(config) for config in configs],
        "solver": "shortest_predicted_duration_first", "solver_budget_seconds": args.solver_budget,
        "simulation_seed": 0, "step_minutes": 1,
        "assumptions": [
            "All usable cases for each selected date are ready at opening.",
            "Rooms are synthetic and identical; no staff, beds, or clinical compatibility constraints.",
            "Observed durations stay unchanged under rescheduling and are hidden from the optimizer.",
            "Durations are rounded upward to whole minutes.",
            "Closures prohibit new starts but allow ongoing cases to finish.",
            "Closure and restoration time become known when the closure starts.",
            "Simulation time pauses during optimization.",
            "No new starts at closing; running cases and turnover may extend beyond closing.",
            "Procedure labels are assumed known when scheduling.",
        ],
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    rows = []
    for day in days:
        scenario = data.scenario(day)
        for config in configs:
            for policy in policies:
                result = await run_day(scenario, config, policy, timeout_seconds=args.solver_budget)
                stem = f"{day}-{result['scenario']}-{policy}"
                (args.output / f"{stem}.json").write_text(json.dumps(result, indent=2) + "\n")
                row = {key: result[key] for key in ("date", "scenario", "policy")}
                row.update(result["metrics"])
                rows.append(row)
                print(f"{stem}: completed={row['completed']}/{row['cases']}, "
                      f"overtime={row['overtime_minutes_including_turnover']} min, "
                      f"failures={row['failures']}")
    with (args.output / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
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
