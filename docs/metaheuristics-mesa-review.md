# Metaheuristics and Mesa: implementation review and comparison design

This review predates assembly. See [the implementation guide](metaheuristics-mesa-assembly.md)
for the current coupled system; the findings below document the original branch.

## Reviewed versions

- Mesa implementation: commit `0725cd7`, branch `feat/mesa-historical-simulation`.
- Optimizer: remote `meta_heuristics`, commit `8a618d11c7c18434380bf17aca3024c1367b5312`.
- Remote main: `344b29c`, which integrates the original coordination core.

GitHub SSH fetch failed twice. HTTPS `ls-remote` independently confirmed the
optimizer and main tips above. The optimizer was inspected and tested in an
isolated temporary checkout. It has not been merged into the Mesa branch.
This document is a review and proposed integration design, not measured evidence
that the combined system already works or improves hospital performance.

## What the optimizer adds

The branch adds a reusable optimization package, synthetic data generator,
Parquet data bridge, Tkinter interface, convergence/planning/bed charts, a CLI
demo, an explanatory notebook and tests.

All five methods use the same `PlanningProblem` and solution representation:
patient row index -> vacation row index. These are positional indices, even if
an input table contains different patient or vacation identifiers. Conversion
back to identifiers happens in `solution_to_dataframe`.

A vacation is a day/specialty session with a minute capacity. The model does not
assign physical room IDs, start times or within-session order. Every generated
solution assigns every patient; overload is penalized rather than prohibited.

| Method | Behavior in this implementation |
|---|---|
| Simulated annealing | Starts randomly, changes one assignment or swaps two same-specialty patients, accepts improvements and sometimes deteriorations; temperature decreases geometrically. |
| Tabu search | Samples a neighborhood, chooses the best admissible move, remembers recent move tuples and overrides tabu status for a new global best. If all sampled moves are tabu it falls back to the best sampled move. |
| Genetic algorithm | Maintains a population, uses fitness-shifted roulette selection, one-point crossover, assignment mutation, and optional elitism. |
| Tabu x Annealing | Filters sampled neighbors with tabu/aspiration rules, then applies temperature-based acceptance to the selected candidate. |
| Ant colony optimization | Constructs complete assignments using patient-session pheromones and a preference for sessions with a lower load/capacity ratio; evaporates pheromones and reinforces the best ant of each iteration. |

The existing Tabu x Annealing method combines two optimization algorithms. Its
coupling with Mesa would be an additional simulation/optimization feedback loop.
The ACO construction heuristic does not guarantee capacity feasibility; candidate
fitness accounts for overload after construction.

Default cost, whose negative is maximized:

    5 * session overload minutes
  + 3 * bed overload patient-days
  + 0.05 * standard deviation of session loads

The weights combine different units. Record them and examine sensitivity before
interpreting a method's ranking. A fitness value alone is not a feasibility check.

Sources: [optimizer](https://github.com/Kaua-Rbs/IA-et-Sante-groupe-2/blob/8a618d11c7c18434380bf17aca3024c1367b5312/optimiseur/optimizer.py),
[data bridge](https://github.com/Kaua-Rbs/IA-et-Sante-groupe-2/blob/8a618d11c7c18434380bf17aca3024c1367b5312/optimiseur/data_bridge.py).

## Findings that affect the comparison

1. **Observed outcomes are used as optimizer inputs.** The current Parquet bridge
   passes observed room duration and corrected stay directly into the optimizer.
   This is useful for deterministic allocation experiments, but a prospective
   simulation must instead provide estimates available before execution. Keep
   the cleaned-XLSX loader and 2019–2021 duration estimates for the Mesa study.
2. **The stay definitions disagree.** The bridge supplies total inclusive stay;
   the optimizer counts surgery day plus `duree_sejour` days. A supplied value of
   1 occupies two days. Preoperative stay is not represented, and occupancy is
   truncated at the planning horizon. Disable the bed objective for the room-only
   coupling. A later bed model needs an agreed postoperative-duration definition,
   initial bed occupancy and a sufficiently long occupancy horizon.
3. **The small exact benchmark has no allocation choice.** Its seven cases each
   have one compatible vacation: only one complete solution exists. All five
   methods matching that optimum does not demonstrate effective search. Add a
   reference instance with multiple compatible sessions per case and competing
   capacities; retain exhaustive enumeration as the reference solver.
4. **Replanning boundary cases are missing.** Genetic crossover fails with one
   remaining patient (`randint(1, 0)`), reproduced directly. Handle zero and one
   waiting case before entering search, and reject empty room sets explicitly.
5. **Fitness is not validation.** An empty assignment currently scores zero even
   on a nonempty problem. Normal generators produce complete assignments, but an
   integration adapter must enforce full coverage and report unstarted cases.
   Specialty fallback currently permits all sessions when no matching session
   exists; a future clinical compatibility model must not silently use that rule.
6. **Compute budgets are not comparable yet.** Methods stop after iterations or
   generations, which perform different numbers of fitness evaluations. They
   have no common deadline, cancellation or warm-start interface. Their internal
   timing also excludes some initialization. Measure complete request time and
   add shared budgeting before publishing performance rankings.

Validation on Python 3.12 / the existing project environment: **47 tests ran;
43 passed, 3 skipped, 1 failed**. The failure asserts Python must equal 3.14.
Skipped tests concern the optional real Parquet in the temporary checkout and
Tkinter. The synthetic end-to-end CLI test passed. This does not establish that
all supported environments or the private-data optimizer pipeline were tested.

## Proposed assembly: first room-only version

Preserve Mesa 3.5.1 and the current cleaned-XLSX input. Import the optimizer package
and reconcile README, requirements, test initialization and environment-specific
repository guidance. Do not copy its Parquet bridge into the simulation path.

    Cleaned cases and predictions
        -> public HospitalState snapshot
        -> MetaheuristicScheduler(method, seed, budget)
        -> candidate room allocations
        -> common timed-schedule decoder and fitness
        -> RoomValidator
        -> Coordinator.accept()
        -> Mesa execution
        -> closure/reopening observation -> next request

### Adapter and decoder

- Build solver tables from waiting cases only. Map local case IDs to contiguous
  solver row indices and reverse that mapping on return.
- Treat each physical room's remaining day as a vacation-like option. Keep a
  separate mapping to room ID, opening/closing boundaries and known start
  prohibitions. Use one common specialty label for this room-only model.
- Provide predicted occupancy only. Disable the bed term. Historical realized
  durations stay private to Mesa; no future outage enters the initial snapshot.
- Reuse the algorithms' allocation moves. Within each room, use one deterministic
  order for every method: predicted duration, then case ID. This first coupling
  optimizes allocation; it does not independently optimize within-room sequence.
- Decode each room allocation into start times from current availability, advancing
  through turnover and known closures. Closures prohibit new starts, not ongoing
  occupancy. Cases without a start before closing become explicitly unstarted.
- Freeze completed/ongoing work outside the search; reserve its observed or
  estimated remaining occupancy. Add fixed assignments back before validation.
- Evaluate candidate allocations using this same decoder during search. Merely
  repairing the final winner would let the optimizer optimize a different problem
  from the schedule eventually executed. The common objective should prioritize
  avoiding unstarted cases, then operational costs such as overtime; choose and
  document the same weighting/priority rule for all methods before benchmarking.

All this fits the existing `Scheduler.propose(request)` and `Proposal(Schedule,
base_version)` boundary. Call the selected algorithm, not `optimize_planning`,
which currently launches all five methods sequentially.

### Replanning execution

Supply the current assignment as an initial candidate: initialize local search
from it, insert it into the genetic population, and evaluate it as an incumbent
for ACO. Add shared deadline/evaluation-budget checks and best-so-far returns.
Run synchronous search in a worker process so it cannot block asyncio; a timeout
must terminate and join that process. A thread timeout alone does not stop CPU
work. Keep simulation time paused during solving for this first study.

Retain current closure/reopening triggers and the validator/acceptance boundary.
Failed requests preserve the accepted plan and execution guards. A shared
no-worse-than-incumbent acceptance rule under the predicted objective is a useful
follow-on; it cannot guarantee improvement under hidden realized durations.

## Comparison document and experiments

### A. Compare the original allocation algorithms

Describe their original session/bed objective and assumptions explicitly. Use a
nontrivial small exact instance, plus progressively larger synthetic session
instances. Keep this study's results distinct from the room-only Mesa objective.
Historical outcomes used as known inputs must be labeled as such.

### B. Compare scheduling policies inside Mesa

Compare six schedulers (baseline plus five methods), each with static execution
and reactive replanning: **12 policies**. Run identical cases and hidden durations
with and without closure. Within each method/seed, reuse the exact initial plan
for the static/reactive pair. A separate common-initial-plan comparison can isolate
which method repairs a disrupted schedule best.

- Small: about 7–10 cases with multiple room choices and a tractable exact
  allocation reference under the same decoder and objective.
- Historical: complete held-out 2022 days. Current usable workloads reach 25 cases;
  describe these as historical workload tests, not large-scale evidence.
- Large: generated 100- and 300-case instances as proposed stress sizes, sampling
  case characteristics and duration realizations together. Scale room capacity
  to study size at similar load, then vary load separately. Label generated cases
  and synthetic resource assumptions. Confirm runtime feasibility in a pilot.
- Use repeated solver seeds, paired instances and equal evaluation budgets for
  reproducible search comparisons; separately assess end-to-end time limits.
  Do not use an equal iteration count as an equal work budget.
- Report exact objective gap where available, end-to-end time and convergence,
  plus completed/unstarted cases, overtime, start delay, utilization, schedule
  changes and failure rates. Report raw components alongside aggregate cost.
- Report variability across instances/seeds. Optimize/tune parameters on separate
  scenarios, not the held-out comparison set. No single best-seed run establishes
  a winner. An ACO or genetic population is not a Mesa hospital-agent simulation.

Suggested document sections: implemented problem and algorithms; data mapping and
limits; shared room model and coupling; small/large experimental protocol; static
results; disrupted static/reactive results; computation cost and limitations.

Before claiming the hybrid is validated, test singleton/empty requests, fixed
commitments, mapping and decoder coverage, closure semantics, timeouts, hidden
outcome separation, and a full run for each of the five adapters. The 30 existing
Mesa tests and the optimizer tests should remain regression checks after assembly.
