"""Capture actual child exit codes for regression/replay checks, synthetic only."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
TEST_MODULES = ["tests.test_feasibility", "tests.test_feasibility_experiment",
    "tests.test_feasibility_review", "tests.test_feasibility_generalization",
    "tests.test_optimizer", "tests.test_hybrides", "tests.test_aleas",
    "tests.test_coordination", "tests.test_coordination_bridge", "tests.test_data_bridge",
    "tests.test_prediction_ward"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        parser.error("Output must be new or empty")
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["MPLCONFIGDIR"] = str(ROOT / ".cache/matplotlib")
    env["TEMP"] = env["TMP"] = str(ROOT / ".tmp")
    (ROOT / ".tmp").mkdir(exist_ok=True)
    if (ROOT / ".deps").is_dir():
        env["PYTHONPATH"] = str(ROOT / ".deps") + os.pathsep + env.get("PYTHONPATH", "")
    commands = [
        ("regression", ["-m", "unittest", *TEST_MODULES, "-v"]),
        ("original_replay", ["-m", "experiments.verify_feasibility_results",
                              "experiments/results/s1-s2-2026-10-19-v1"]),
        ("generalization_replay", ["-m", "experiments.review_feasibility", "--verify-only", "--output",
                                    "experiments/results/s1-s2-generalization-2026-10-19-v1"]),
    ]
    record = {"runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(), "checks": []}
    for name, arguments in commands:
        print(f"starting {name}", flush=True)
        start = monotonic()
        child = subprocess.run([sys.executable, "-B", *arguments], cwd=ROOT, env=env,
                               capture_output=True, text=True, timeout=240)
        (output / f"{name}.txt").write_text(child.stdout + child.stderr, encoding="utf-8")
        record["checks"].append({"name": name, "arguments": arguments, "exit_code": child.returncode,
                                  "wall_seconds": monotonic() - start,
                                  "log_sha256": sha256((output / f"{name}.txt").read_bytes()).hexdigest()})
        (output / "verification.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        print(f"finished {name}: exit {child.returncode}", flush=True)
    if any(check["exit_code"] != 0 for check in record["checks"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
