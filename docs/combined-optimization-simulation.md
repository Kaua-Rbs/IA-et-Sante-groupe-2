# Combined optimizer and Mesa simulation

This branch combines the vacation-level optimizer from `meta_heuristics` with
the historical room simulation. They share the asynchronous coordinator and
eight search algorithms, but **retain different planning models and scores**.
This is a code integration and a common room-solver comparison, not yet a
joint bloc–beds–ambulatory simulation.

| Track | Decision and objective | Data and execution |
|---|---|---|
| `optimiseur/` | Assign patients to day-level specialty vacations; penalize excess vacation minutes, bed-days and workload imbalance. | Synthetic data or the EDA Parquet. `aleas.py` generates alternatives and adapts plans after known events. Its Mesa agents collaborate as search methods. |
| `hospital_sim/` | Assign episodes to synthetic rooms and predicted minute-level starts; prioritize fewest unstarted cases, then predicted overtime, then changed decisions. | Cleaned workbook, with 2019–2021 duration estimates and held-out 2022 outcomes; Mesa patient agents execute the accepted plan minute by minute. |

The room scheduler now accepts the five original methods plus **genetic ×
tabu**, **genetic × annealing** and **ACO × tabu**. All eight use the same
room decoder, optimizer-visible state, `SearchControl` evaluation counter,
worker process, deadline, validator and coordinator acceptance. The two
vacation-level Mesa search systems remain in `optimiseur/multiagent.py`; they
are not patient or bed agents in the room simulation.

## Run the combined code

Run from the repository root after installing `requirements.txt` with Python
3.12 or later (Mesa is pinned to 3.5.1). In this workspace use `venv/bin/python`.

The seven-case fixture needs no private data. It tests all eight searches
under identical evaluation limits, with both static and reactive policies:

```bash
venv/bin/python -m hospital_sim.experiment \
  --small-reference --closing 11:00 \
  --outage-start 09:00 --outage-end 10:00 \
  --methods baseline annealing tabu genetic hybrid aco gen_tabu gen_annealing aco_tabu \
  --seeds 0 --max-evaluations 200 --solver-budget 15 \
  --output artifacts/combined-small
```

For held-out historical days, pass the cleaned workbook and a new output
directory. An oracle run requires a separate directory and the same case,
room, seed and budget settings:

```bash
venv/bin/python -m hospital_sim.experiment \
  --input resources/donnees_bloc_nettoyees.xlsx --dates 2022-01-03 \
  --methods baseline annealing tabu genetic hybrid aco gen_tabu gen_annealing aco_tabu \
  --seeds 0 --max-evaluations 500 --solver-budget 30 \
  --output artifacts/combined-historical
```

The vacation/bed track can be run independently:

```bash
venv/bin/python -m optimiseur.run_demo --toutes --budget 1 --out resultats/combined-demo
venv/bin/python -m optimiseur.run_coordination_demo
```

`optimiseur.run_benchmark` compares the ten vacation-level methods on equal
wall-clock budgets. `optimiseur.aleas.generer_plannings_alternatifs` produces
nominal, buffered, bed-safety and alternative-date proposals;
`adapter_planning` applies events known by the current day and reports both
the adjusted plan and its hard-capacity violations. If an emergency has no
compatible vacation within its deadline, adaptation raises an error instead
of silently assigning it outside the clinical window. An alternative or
adapted plan is a proposal, not a guarantee of zero overflow.

## Comparison boundaries

- The older 576-run room report covers the baseline and five original
  algorithms. It does **not** rank the three newly connected hybrids.
- `rapport/RAPPORT.md` records the vacation benchmark from the imported
  branch. Its seven-case fixture had four listed vacations but only one
  compatible option per patient, so its reported 100% exact-optimum rate
  does not demonstrate search quality. The combined code retains the
  two-compatible-vacation fixture (128 allocations) from the historical
  Mesa work. Re-run the native benchmark before quoting small-instance
  numbers for this combined revision.
- The vacation report's fitness and the room report's normalized cost are
  different quantities. Compare methods only within one track and workload.
- Room execution currently handles a temporary closure to new starts.
  Emergencies, cancellations, bed closures and vacation-capacity losses are
  implemented in the vacation track and its coordination bridge, but are not
  executed as patient events in the room model.
- The vacation optimizer accounts for beds, but neither Mesa model has
  ambulatory places or dedicated bloc/bed/ambulatory resource agents.
- Historical workloads are used under explicit synthetic room assumptions;
  the simulation does not reconstruct the hospital's actual assignments.

To make a joint resource simulator, the next step is to define a shared
episode record with predicted occupancy, length of stay, care type, and
resource availability. The room simulator could then reserve beds or
ambulatory places at an accepted start, release them at an observed discharge,
and trigger replanning when those resources change. This requires validation
of the underlying data mapping and a common multi-resource feasibility check.

## Verification

```bash
venv/bin/python -m unittest discover -t . -s tests -q
```

The combined tests cover native optimizer methods, the vacation-level Mesa
agents and disruption module, the vacation coordination bridge, the room
simulation, and all eight room search adapters. Private workbooks and run
outputs remain under ignored `resources/` and `artifacts/`.
