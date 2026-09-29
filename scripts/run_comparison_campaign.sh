#!/usr/bin/env bash
# Run from the repository root. Output directories must not already contain files.
set -euo pipefail
out=${1:-artifacts/comparison-2026-09-28}
common=(--methods baseline annealing tabu genetic hybrid aco --seeds 0 1 2 --max-evaluations 1000 --solver-budget 60)
venv/bin/python -m hospital_sim.experiment --small-reference --closing 11:00 --outage-start 09:00 --outage-end 10:00 "${common[@]}" --output "$out/small"
venv/bin/python -m hospital_sim.experiment --dates 2022-01-03 2022-02-02 2022-10-20 "${common[@]}" --output "$out/historical"
venv/bin/python scripts/run_large_comparison.py "$out"
