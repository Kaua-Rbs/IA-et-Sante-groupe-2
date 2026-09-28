# Metaheuristics coupled to Mesa

The baseline and all five optimizer methods now use the same room-only simulation.
The coupling reads `donnees_bloc_nettoyees.xlsx`, estimates durations from 2019–2021,
and executes held-out cases using hidden historical durations. Mesa remains pinned
to **3.5.1**. Python **3.12+** is supported.

The native vacation/bed optimizer remains available through `optimiseur.run_demo`.
Its cost function is unchanged. Its scores and the coupled room objective below
represent different problems and must not be compared numerically.

## Run the comparison

From the repository root, with dependencies installed:

```bash
venv/bin/python -m hospital_sim.experiment \
  --dates 2022-01-03 2022-01-21 \
  --methods baseline annealing tabu genetic hybrid aco \
  --seeds 0 1 2 --max-evaluations 5000 --solver-budget 15 \
  --output artifacts/hybrid-historical
```

The default command still runs the baseline only. Both execution policies and both
closure scenarios run by default. Output directories must be empty.

For each instance, method and solver seed, the runner computes **one initial plan**
and replays it in all four combinations. It accepts this plan through the shared
validator before revealing the first closure. Replaying it avoids differences
caused by separately timed searches, even with identical random seeds.

Static execution retains the initial room queues and applies actual occupancy,
turnover and closure guards. Reactive execution requests a new plan at closure
and reopening. Simulation time pauses while optimization runs.

### Small instance with an exact reference

```bash
venv/bin/python -m hospital_sim.experiment \
  --small-reference --closing 11:00 \
  --outage-start 09:00 --outage-end 10:00 \
  --methods baseline annealing tabu genetic hybrid aco \
  --seeds 0 1 2 --max-evaluations 5000 --solver-budget 15 \
  --output artifacts/hybrid-small
```

This fixture needs no workbook. Its seven cases and two rooms give 128 allocations.
The shorter opening window makes the reference nontrivial. Enumeration uses the
same decoder and objective as the metaheuristics. `initial_objective_gap` is the
initial candidate cost minus the exact cost. It is not a retrospective execution
optimality gap. Enumeration rejects requests exceeding 100,000 allocations.

The native optimizer's small reference was also changed to seven cases and two
compatible vacations. Its objective additionally includes load balance; keep the
two exact experiments separately labeled.

### Larger generated workloads

```bash
venv/bin/python -m hospital_sim.experiment \
  --synthetic-cases 100 300 --instance-seeds 0 1 2 \
  --methods baseline annealing tabu genetic hybrid aco \
  --seeds 0 1 2 --target-load 0.8 \
  --max-evaluations 5000 --solver-budget 30 \
  --output artifacts/hybrid-large
```

Complete valid 2022 rows are sampled with replacement. Procedure and observed
occupancy therefore stay paired; predictions still come from earlier years.
IDs are regenerated locally. These are generated workloads, not historical days.

Room count is `ceil(sum(predicted duration + turnover) / (opening minutes × target load))`,
with a minimum of one. The default target is 0.8. For a separate overload study,
use e.g. `--target-load 1.1`. This separates growing instance size from increasing
resource scarcity. Integer room counts make the achieved load approximate.
`--rooms` applies to historical and small instances; generated instances derive
room counts from their workload and target load. Each generated run uses a
synthetic date anchor; its `instance_id` and manifest identify the actual workload.

These commands are reproducible experiment configurations, not recommended tuned
hyperparameters. Run a small pilot before the complete size/instance/seed matrix.

## Common allocation model

The adapter exposes only waiting-case predictions, current availability, known
closures and fixed commitments. Solver indices are mapped back to local case IDs.
There are no beds, specialties, staff constraints or future disruptions in this
interface. No realized duration is sent to the worker.

Each candidate maps waiting-case indices to room indices. A common decoder:

1. Sorts each room's assigned cases by predicted duration, then case ID.
2. Starts from the current room-availability estimate.
3. Moves proposed starts past known closures and adds turnover after each case.
4. Marks cases unable to start before closing as unassigned.
5. Restores completed/running assignments unchanged.

A closure prohibits new starts, not continuation of ongoing work. Predicted finish
may exceed closing if the start is earlier. Actual execution always guards room
occupancy, so optimistic remaining-duration estimates cannot create overlaps.
Every algorithm evaluates candidates through this decoder. This version optimizes
allocation, not an independent within-room sequence. Incomplete or malformed
allocations are rejected.

## Objective and algorithm controls

Schedules are ranked in strict order:

1. Fewest predicted unstarted waiting cases.
2. Least predicted overtime, including turnover.
3. Fewest changed waiting-case assignments.

Let U be unstarted cases, O their scheduled peers' predicted overtime, R the number
of changed room/start/assignment decisions, N the number of waiting cases, and
Omax the sum of their predicted durations plus turnover. Minimize:

    C = U + (O + R / (N + 1)) / (Omax + 1)

The algorithms maximize `-C`. Since R ≤ N and O ≤ Omax, one extra unstarted case
always dominates the other terms; one extra overtime minute dominates all changes.
R is zero for initial planning. Fixed activity's overtime is constant within a
request and is excluded from its search score. It remains in execution metrics.
Raw U/O/R components are exported alongside the numerical cost.

The initial incumbent is the baseline allocation, or the current room choices
repaired against current availability. Previously unassigned cases are inserted
greedily. Decoding may move waiting starts; running/completed work stays fixed.
Local searches start from the incumbent; the genetic population includes it; ACO
records it as an incumbent. The best evaluated candidate is never worse under
this request's objective, but hidden realized durations can still make execution
worse. Predicted improvement is not a guarantee of hospital improvement.

The standalone algorithms accept optional `initial_solution` and `control`
keywords. `SearchControl` counts fitness calls (including initialization and
repeated candidates), checks budgets, and records improvements. Calls without
these options retain their native behavior. `RunResult` adds evaluations and a
stopping reason without changing existing required fields.

For the coupled profile, both annealing methods use T0=1 on the normalized cost.
Other parameters retain their native values: cooling 0.95/0.97; tabu memory 20
and neighborhood 15; genetic population 40, crossover 0.8, mutation 0.08 and
elitism; ACO 15 ants, alpha 1, beta 2, evaporation 0.3 and deposit scale 1.
All settings are saved per request. Tune on separate training scenarios if needed.

Zero waiting cases and no room options return explicit schedules without search.
A singleton request evaluates room choices directly, subject to the same budget.
Native genetic crossover also handles singleton inputs.

## Budgets, process safety and reproducibility

`--budget-mode evaluations` uses the specified fitness-call limit. Method-specific
iteration ceilings are made high enough for this common limit to control stopping.
The elapsed-time setting still acts as a safety deadline. A truncated run is
labeled `deadline`; do not treat it as an equal-evaluation comparison.

`--budget-mode time --solver-budget 5` instead uses elapsed time and ignores the
evaluation cap for stopping. Count evaluations completed and repeat runs/seeds.
Do not expect identical results at a wall-clock cutoff on different machines.

Each nontrivial metaheuristic request runs in a spawned worker process. The deadline
includes startup and IPC. Completed incumbents are published while searching.
Cooperative stopping leaves a small margin for return/validation; hard timeout or
cancellation terminates and joins the worker. Shutdown overhead is included in
reported elapsed time; this is not a production real-time guarantee.

A deadline before search startup can return the prepared feasible incumbent with
zero search evaluations. This is explicitly distinguishable in reports. Worker
errors also retain a valid incumbent where possible and are counted. No candidate
bypasses `RoomValidator` and coordinator acceptance. Failed initial planning with
no proposal yields an all-unassigned initial plan, allowing other comparisons to
continue. The baseline has zero search fitness evaluations because it is greedy.

## Outputs for the comparison document

- Manifest: instance provenance, input hash, code hash covering both packages,
  dependencies, objective, seeds, resource assumptions, and exact reference where available.
- One initial-plan JSON per instance/method/seed, with measured planning cost.
- One execution JSON per policy/scenario, including schedules, observations,
  coordinator outcomes and search reports with U/O/R, convergence and stop reasons.
- Summary CSV: existing operational metrics plus fitness evaluations, search
  failures, deadline stops, initial planning time, replanning time and exact gap.

Initial computation is performed once but its measured cost is included consistently
in each policy's total. Stop reasons distinguish evaluations, deadline, exact,
trivial, baseline, worker error and cancellation. Progress history contains fitness
improvements and a terminal point for worker searches; it is indexed by evaluations.

Use the same instances and solver seeds for every method. Compare completed and
unstarted cases alongside overtime and delay. At light load, the baseline may
already have optimal predicted cost; a tie is a valid result. Sensitivity to load,
budgets and duration error matters more than selecting one favorable seed.

## Tests

```bash
venv/bin/python -m unittest discover -t . -s tests -v
```

The suites cover both native and coupled objectives, exact enumeration, hidden
outcomes, identifier mapping, fixed work, closures, empty/singleton requests,
shared initial plans, method budgets, deterministic evaluation-limited search,
worker deadline/cancellation cleanup, and original notebook/CLI functionality.
Private workbooks and generated reports remain outside git. Tkinter tests skip
when its optional dependency is unavailable.

## Implementation verification

Validation in this workspace completed with 90 tests (88 passed, 2 optional
Tkinter tests skipped) and no broken installed dependencies. Additional output
checks covered:

- 48 historical runs: two dates × six methods × two policies × two scenarios,
  with 500 search evaluations per nontrivial request and a 15-second safety limit.
- 12 generated stress runs: 100/300 cases × six methods, static execution without
  closures, target load 1.1 and 100 search evaluations.
- Four ACO runs with a one-second elapsed-time budget; the evaluation cap was
  intentionally set to one to verify that time mode does not use it for stopping.

The audits verified case conservation, room occupancy, turnover, closing and
closure rules, recomputed overtime, identical initial plans within each pair,
no-outage policy equivalence, evaluation limits, absence of original identifiers
in exports, and unchanged source-workbook hashes. No solver or validator failures
occurred in these runs. These are integration checks with one solver seed, not a
statistical ranking of the methods or a claim of clinical effectiveness.
