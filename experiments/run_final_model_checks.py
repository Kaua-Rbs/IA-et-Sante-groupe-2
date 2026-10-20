"""Record child exit codes and reproducible test logs without private records."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic

from experiments.run_feasibility_checks import TEST_MODULES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error("Output must be new or empty")
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", MPLCONFIGDIR=str(root/".cache/matplotlib"),
               TEMP=str(root/".tmp"), TMP=str(root/".tmp"))
    env["PYTHONPATH"] = str(root/".deps")+os.pathsep+env.get("PYTHONPATH", "")
    (root/".tmp").mkdir(exist_ok=True)
    modules = TEST_MODULES + ["tests.test_surgery_duration", "tests.test_final_models",
                             "tests.test_historical_simulation", "tests.test_oracle_simulation", "tests.test_integration"]
    commands = [("regression", ["-m", "unittest", *modules, "-v"]),
        ("original_s1s2_replay", ["-m", "experiments.verify_feasibility_results", "experiments/results/s1-s2-2026-10-19-v1"]),
        ("larger_s1s2_replay", ["-m", "experiments.review_feasibility", "--verify-only", "--output", "experiments/results/s1-s2-generalization-2026-10-19-v1"])]
    record = {"runner_sha256":sha256(Path(__file__).read_bytes()).hexdigest(), "checks":[]}
    for name, arguments in commands:
        print(f"starting {name}", flush=True)
        start = monotonic()
        result = subprocess.run([sys.executable, "-B", *arguments], cwd=root, env=env,
                                capture_output=True, text=True, timeout=180)
        path = args.output/f"{name}.txt"
        path.write_text(result.stdout+result.stderr, encoding="utf-8")
        record["checks"].append({"name":name, "arguments":arguments, "exit_code":result.returncode,
            "seconds":monotonic()-start, "log_sha256":sha256(path.read_bytes()).hexdigest()})
        (args.output/"verification.json").write_text(json.dumps(record, indent=2)+"\n")
        print(f"finished {name}: {result.returncode}", flush=True)
    if any(item["exit_code"] for item in record["checks"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
