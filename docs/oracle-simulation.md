# Perfect-duration (oracle) simulation

The experiment runner accepts `--duration-mode median|oracle`. The default remains
`median`: historical 2019-2021 procedure medians (or the fixture's estimates for
`--small-reference`). In `oracle` mode, the scheduler receives the episode's
realized **room occupancy duration**, rounded upward to whole minutes, as its
scheduling estimate. This is an explicit perfect-information experiment, not an
ML prediction or a clinically deployable predictor.

## Paired comparison

Run both modes with the same cases, resource settings, method seeds and budgets,
using separate empty output directories:

```bash
for mode in median oracle; do
  venv/bin/python -m hospital_sim.experiment \
    --dates 2022-01-03 2022-02-02 2022-10-20 \
    --duration-mode "$mode" \
    --methods baseline annealing tabu genetic hybrid aco \
    --seeds 0 1 2 --max-evaluations 1000 --solver-budget 60 \
    --output "artifacts/duration-comparison/$mode"
done
```

Each mode supports historical dates, generated workloads and the exact small
reference, both policies, and both closure scenarios. For a workbook-free run:

```bash
venv/bin/python -m hospital_sim.experiment \
  --small-reference --duration-mode oracle --closing 11:00 \
  --outage-start 09:00 --outage-end 10:00 \
  --methods baseline annealing tabu genetic hybrid aco \
  --output artifacts/oracle-small
```

For generated workloads use `--synthetic-cases 100 300 --instance-seeds 0 1`.
Room counts are **always calculated from the original median estimates before
applying the duration mode**. Thus the same sample and target-load settings use
identical rooms and realized outcomes in both modes. The realized/predicted
load in oracle mode may differ from the median-based sizing target.

## What changes and what stays fixed

`instances.with_duration_mode` replaces only each case's `predicted_minutes`
input in oracle mode. IDs, procedures and realized execution durations remain
identical. The input scenario and workbook are not modified. Existing scheduler
adapters and execution guards are reused; no solver-specific oracle logic is
needed. Every initial solve and subsequent replan sees the selected estimates.

The scheduler knows durations, not the hospital's historical entry/exit clock
times. It still cannot see a future closure before it begins. Ongoing cases
continue normally during a closure. In oracle mode their original duration
estimate is exact; future actual-finish fields remain absent until completion.
The simulator still enforces opening, closing, occupancy and turnover rules.

Within each mode, each initial plan is shared across the static/reactive and
closure/no-closure conditions. Across modes, initial plans are recomputed:
changing duration knowledge is intended to change scheduling decisions. The
small-instance exact reference is also recomputed for the selected mode.

## Outputs and interpretation

`duration_mode` is recorded in the manifest, initial-plan JSON, execution JSON
and every summary CSV row. The manifest explains the duration information and
room-sizing rule. Match comparison rows using instance, method, solver seed,
scenario and policy; keep the duration mode as a separate comparison dimension.
Use completed/unstarted cases, realized overtime and delay to compare modes.
Do not directly compare normalized costs across modes: changing the scheduling
durations also changes the objective's normalization.

Oracle results measure scheduling with perfect room-duration information under
the present rules. They are an optimistic information reference, not a certified
operational upper bound: finite search budgets, the fixed within-room ordering,
the objective and reactive policy can still produce worse realized metrics.
The difference from median mode does not predict a future ML model's exact gain.
That requires held-out ML predictions for the **same room-occupancy target**.

The existing September 28 comparison reports remain records of median-mode
experiments. This feature does not regenerate those reports or mix oracle runs
into their results. Future report aggregation should retain the mode label.
