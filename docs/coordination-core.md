# Coordination core for the hospital simulation

This is asynchronous coordination infrastructure for future agents, not a complete multi-agent optimizer. Clinical rules, trained prediction models, backend endpoints, and frontend integration remain unimplemented. Five metaheuristic adapters now support the room-only experiment; see [the assembly guide](metaheuristics-mesa-assembly.md). A room-only Mesa adapter and historical workload experiment are now available; see [the simulation guide](mesa-historical-simulation.md).

## Run and verify

The standalone coordinator demo requires Python 3.10 or newer, with no dependencies beyond the standard library. The Mesa historical experiment and full requirements need Python 3.12 or newer. From the repository root:

```bash
python -m hospital_sim.demo
python -m unittest discover -s tests -v
```

The demo uses one synthetic case and three rooms. Room A becomes unavailable, then room B becomes unavailable while the first scheduling request is suspended. The first result is discarded; a new request proposes room C. The original accepted schedule is retained and flagged for review until an explicit acceptance call. Output includes `stale`, `proposal_ready`, and `accepted` outcomes. Timing values vary between runs; event sequencing uses asynchronous signals rather than sleeps.

## Adapter boundaries

See [contracts.py](../hospital_sim/contracts.py), [coordinator.py](../hospital_sim/coordinator.py), and the replaceable examples in [demo.py](../hospital_sim/demo.py).

| Interface | Responsibility | Future implementation |
|---|---|---|
| `StateAdapter` | Apply events and extract fixed commitments. | Map hospital resources, patient states, availability and commitments. |
| `LOSPredictor` | Predict total inclusive calendar days with optional uncertainty bounds. | Wrap the LOS model and its preprocessing. |
| `RoomDurationPredictor` | Predict room entry-to-exit minutes, excluding turnover. | Wrap the room-duration model and its preprocessing. |
| `Scheduler` | Asynchronously propose a schedule tied to the input state version. | Adapt the other team's solver. |
| `Validator` | Return feasibility and explanatory reasons. | Delegate to the agreed shared scheduling validator. |

Domain state, schedules, prediction inputs and fixed commitments are adapter-owned. No day/session/start-time representation or hospital hierarchy is imposed. Objects crossing these boundaries must support `copy.deepcopy`. Keep models, database connections and process handles inside adapter instances, not state snapshots.

Prediction protocols are synchronous and are not called by the coordinator. The scheduling adapter decides when predictions need refreshing and must check their units. Demo prediction values and intervals are constants, not fitted or calibrated, and do not influence room selection. There is no prediction cache or emergency-demand model yet.

`SchedulingRequest` contains a snapshot with the accepted schedule, opaque fixed commitments, and an absolute `time.monotonic()` deadline. `Proposal.base_version` must match the request. A solver returns `None` when it finds no proposal; that is not a proof of infeasibility.

`DemoValidator` only checks room availability and a fixed-room commitment for one synthetic case. It does not check staffing, overlaps, beds, durations, or clinical priorities.

## Lifecycle

Use the coordinator on one running asyncio event loop. State application and validation are synchronous and must be fast and nonblocking.

1. `submit(event, replan=True)` applies an event, increments the state version, clears any exposed proposal, and marks an existing accepted schedule for review. Use `replan=False` to synchronize an observation without creating a new scheduling request; an already pending request is preserved.
2. At most one solver request runs. Further events immediately update the state and are coalesced into one pending request against the latest snapshot.
3. Outdated results are discarded before validation. Candidates bearing the wrong request version are rejected.
4. A current feasible candidate becomes available through `coordinator.proposal`, without changing the accepted schedule.
5. `accept(expected_version)` checks freshness and validates again. Success copies the proposed schedule into accepted state, clears the proposal and increments the version because commitments have changed. This explicit operation is a future approval boundary, not a modeled clinical authority.

Event kinds include emergency arrival, cancellation, surgery overrun, delayed discharge and resource unavailability. The demo only implements resource unavailability with a `resource_id` payload; other kinds raise explicitly. Event IDs must be unique per coordinator instance. Simulation timestamps must be finite, nonnegative and nondecreasing; ties follow submission order. This is not an event calendar or simulation clock.

Snapshots, proposals, event payloads and adapter inputs are isolated through deep copies. Failure while applying an event leaves the state unchanged. Ingestion errors are raised to callers; solver/validation failures are recorded as outcomes. Duplicate events are rejected rather than reapplied.

## Failures and measurements

- Outcomes include `stale`, `invalid_result`, `no_proposal`, `rejected`, `failed`, `timeout`, `proposal_ready`, `acceptance_stale`, `acceptance_rejected`, and `accepted`.
- Preserving an accepted schedule after disruption does not guarantee its feasibility. Check `schedule_needs_review` and the proposal/outcome state.
- Outcomes include request/current versions, solver-request elapsed time and validation reasons. Event-to-proposal latency starts when the latest event in that request was received and includes waiting for older work and validation; it excludes human acceptance time.
- `metrics` counts applied events, stale results, timeouts and validation rejections. Records are held in memory, with no persistence or external logging.
- Failures/timeouts are not retried indefinitely. A newer pending state still triggers its request; otherwise, the caller receives the outcome and determines the next action.
- Exception outcomes contain only the exception type. Validator reason strings must be suitable for display and free of patient/staff identifiers.
- `wait_idle()` waits for active work and coalesced follow-ups. Use an asynchronous context manager or `close()` to cancel active work and reject further submissions.

Timeouts and shutdown require cooperative asyncio cancellation. Future CPU-bound solvers must run outside the event loop. A thread alone does not guarantee termination after cancellation; this core does not provide hard process termination or production response-time guarantees. Simulation time and elapsed computation time are separate.

## Next step

Once the scheduling scope is decided, connect a real state/scheduler adapter and the shared validator, then extend the existing room-only Mesa driver with additional event handlers. The coordinator remains the sole owner of accepted state: future resource agents or cooperating optimization workers submit proposals rather than directly changing the schedule.
