# Historical workload simulation with Mesa

This room-only experiment compares a fixed schedule with reactive rescheduling on
identical historical cases. It uses Mesa **3.5.1**, patient-episode agents, and the
existing asynchronous coordinator. It does not reconstruct the hospital's actual
rooms, waiting list, or original scheduling decisions.

The five metaheuristics are now connected through the shared room decoder.
See [the assembly guide](metaheuristics-mesa-assembly.md) for all-method commands,
budgets, generated workloads and the comparison protocol.

## Run

Use Python **3.12 or newer**, from the repository root:

```bash
python -m pip install -r requirements.txt
python -m hospital_sim.experiment
```

The default reads `resources/donnees_bloc_nettoyees.xlsx`, selects the earliest
eligible 2022 intervention date, and runs static and reactive policies with and
without an outage. Results go to the ignored `artifacts/mesa/` directory.

The input remains unchanged. The output directory must be empty to avoid replacing
a previous experiment. Choose a fresh directory for subsequent runs:

```bash
python -m hospital_sim.experiment \
  --dates 2022-01-03 2022-01-04 \
  --rooms 2 --opening 08:00 --closing 17:00 --turnover 15 \
  --outage-room room-1 --outage-start 10:00 --outage-end 12:00 \
  --output artifacts/mesa-january
```

Use `--date-range 2022-01-03 2022-01-07` for eligible dates in an inclusive range.
Dates with no usable cases are skipped for ranges; an explicitly requested date
without usable cases is an error. Each date runs independently: unstarted cases
are counted, not carried forward. Evaluation dates must be in 2022.

`--policy static|reactive|both` and `--scenarios no_outage|outage|both` select
comparisons. `--solver-budget` sets seconds per request (default: five).
Mesa's network extra is installed because Mesa 3.5.1 imports networkx; this model
has no network graph. The implementation uses one-minute steps, not Mesa's event
scheduling API, and initializes its random generator with `rng=0`.

## Data mapping

| Cleaned workbook column | Use |
|---|---|
| `no_cas` | Internal deterministic ordering; replaced by local `case-0001` identifiers |
| `date_inter` | Training/evaluation split and complete daily workload selection |
| `interv_type` | Normalized category for duration estimation |
| `heure_d_entree_en_salle_d_operation_calimed` | Start endpoint for observed duration |
| `heure_de_sortie_de_salle_d_operation_calimed` | End endpoint for observed duration |

Other columns are unused. Predictions are procedure-specific median occupancy
from valid **2019–2021** cases, requiring at least ten training observations.
Rare/unseen procedures use the overall training median. No 2022 outcomes enter
these estimates. This predicts duration, not clinical priority.

Clock strings, Excel fractional days and time objects are supported. Missing,
invalid or zero endpoints, exit before entry, and zero-duration intervals are
excluded. The current workbook gives **14,434 usable cases and 73 exclusions**.
Counts by reason and date are exported. No overnight rollover, imputation or
additional outlier trimming is applied.

Predicted and observed durations are rounded upward to whole minutes. Observed
duration belongs to the execution scenario and never enters a scheduling request.
Actual completion becomes visible only when it occurs. Changing execution durations
cannot change the initial schedule.

Episode IDs are local to each date/run. Outputs contain no patient identifiers,
source case numbers, birth dates, surgeon/practitioner names, or procedure labels.
They still describe individual simulated episodes; keep them local under artifacts.

## Resource and execution assumptions

- Two identical synthetic rooms, open 08:00–17:00 by default.
- All usable cases for the selected date are ready at opening. Recorded room-entry
  times and order are not scheduling inputs.
- No staff, beds, equipment compatibility, emergency or clinical priority rules.
- Turnover defaults to 15 minutes and is separate from recorded occupancy.
- Starts must be strictly before closing. Running cases and turnover may finish
  later. Waiting cases become the final unstarted count.
- The default outage closes room 1 to new starts from 10:00–12:00. Ongoing cases
  continue. Its expected end becomes known at 10:00, not during initial planning.
- Moving a case does not change its historical realized duration.
- Simulation time pauses during optimization; solver latency is measured separately.
- The vacations workbook is not imported. Room calendars are explicit assumptions.

Actual occupancy and turnover always prevent conflicting starts. Planned starts
are lower bounds: cases do not start early, even if the preceding case finishes
sooner than predicted.

## Scheduling and coordination

The baseline sorts waiting cases by predicted duration, then episode ID, and
assigns each to the earliest available room (room ID breaks ties). Cases without
a start before closing remain explicitly unassigned. It is a benchmark for the
metaheuristic comparisons.

**Static:** retain initial room assignments and order; shift execution later when
occupancy, turnover or closure requires it.

**Reactive:** start from the same initial plan, then replan at closure and
reopening. Only waiting cases may move. Running/completed assignments remain fixed.
Initially unassigned cases can be reconsidered. No overrun-triggered replanning yet.

Each minute: observe completions and turnover, apply availability changes,
synchronize state, optionally obtain/validate/accept a proposal, then start eligible
cases. Future start callbacks are not stored; execution reads the current plan.

`Coordinator.submit(event, replan=False)` synchronizes observations without a new
solve. Observations still increment the state version and invalidate proposals;
an already pending request is preserved. Existing callers retain their behavior
because `replan=True` is the default.

Running-case availability uses original predicted completion, or at least the
next minute if that time has passed, plus turnover. It does not reveal the hidden
actual finish. Execution guards remain authoritative when estimates are optimistic.

Rejected, failed, timed-out or absent proposals retain the previous accepted plan.
An initial failure leaves all cases unassigned. Failures are logged rather than
silently substituting a different optimizer.

### Connecting a metaheuristic

Implement `Scheduler.propose(request)` and inject it with
`run_day(..., scheduler=adapter)`. The request includes current `HospitalState`,
accepted schedule, fixed commitments, state version and monotonic deadline.
State includes case inputs/status, room availability estimates, opening hours,
turnover, and revealed outages. Hidden execution outcomes are excluded.

Return `Proposal(Schedule(assignments, unassigned), request.snapshot.version)`.
Each assignment has local case ID, room ID, integer start minute and predicted
duration. Cover each case exactly once, preserve fixed assignments and pass the
shared `RoomValidator`. Return `None` when no proposal is available.

The baseline cooperates with cancellation. CPU-bound solvers need a worker process
and deadline handling; this prototype does not provide hard process termination
or operational response-time guarantees.

## Outputs and metrics

- `manifest.json`: input SHA-256, code commit/dirty status and implementation hash,
  dependency versions, dates, quality counts, configuration and assumptions.
- `summary.csv`: one aggregate row per date/scenario/policy.
- One JSON file per run: initial/revised plans, executed schedule and event log.

Minutes are measured from the selected day's midnight. Execution may extend beyond
1440. Case outcomes are deterministic; solver latency varies. Nothing is resampled.

| Metric | Definition |
|---|---|
| Completed/unstarted | Final counts; sum equals the eligible daily workload |
| Start delay | Positive part of actual minus initial planned start, for completed cases with an initial assignment |
| Delay measured cases | Denominator; initially unassigned cases have no baseline start |
| Occupancy in hours | Actual intervention time inside opening hours; excludes turnover |
| Utilization | Occupancy divided by rooms × opening-window minutes, including closure time in the denominator |
| Overtime | Occupancy plus required turnover after closing; excludes idle time |
| Changed assignment decisions | Changes between successive plans, including assignment/unassignment; a case may count repeatedly |
| Planned start shift | Sum of absolute shifts when both plans assign the case |
| Room changes | Reassignments when both plans assign the case |
| Replanning count | Requests after initial planning, including unsuccessful requests |
| Solver seconds | Coordinator request durations, including request preparation |
| Failures/timeouts | Failed coordinator outcomes; timeouts are a subset |

Compare completion counts with delay: unstarted cases do not enter completed-case
delay statistics. Replanning is not guaranteed to improve a historical day.
Low- and high-volume dates provide workload comparisons, not evidence of
large-scale solver performance. Current 2022 days have at most 25 usable cases.

## Verification

```bash
python -m unittest discover -s tests -v
```

Synthetic fixtures cover parsing, training separation, hidden outcomes, policy
equivalence without outages, occupancy, turnover, closing, fixed activities,
failures and a crafted case where replanning improves delay. Original coordinator
tests remain intact. Run private-workbook checks locally; do not commit the data
or generated results.
