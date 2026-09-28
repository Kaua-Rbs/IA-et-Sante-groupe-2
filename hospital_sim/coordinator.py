"""Single-event-loop coordinator with isolated snapshots and explicit acceptance."""

import asyncio
from copy import deepcopy
from math import isfinite
from time import monotonic
from typing import Generic, Optional

from .contracts import (
    HospitalEvent, Outcome, Proposal, ScheduleT, Scheduler, SchedulingRequest,
    Snapshot, StateAdapter, StateT, ValidationResult, Validator,
)


class Coordinator(Generic[StateT, ScheduleT]):
    def __init__(
        self,
        initial: Snapshot[StateT, ScheduleT],
        state_adapter: StateAdapter[StateT, ScheduleT],
        scheduler: Scheduler[StateT, ScheduleT],
        validator: Validator[StateT, ScheduleT],
        *,
        timeout_seconds: float = 1.0,
    ) -> None:
        if not isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("Timeout must be finite and positive")
        if initial.version < 0 or not isfinite(initial.simulation_time) or initial.simulation_time < 0:
            raise ValueError("Invalid initial version or simulation time")
        self._state = deepcopy(initial)
        self._adapter = state_adapter
        self._scheduler = scheduler
        self._validator = validator
        self._timeout = timeout_seconds
        self._proposal: Optional[Proposal[ScheduleT]] = None
        self._task: Optional[asyncio.Task[None]] = None
        self._pending = False
        self._closed = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._seen_events: set[str] = set()
        self._event_received_at = monotonic()
        self._outcomes: list[Outcome] = []
        # Even a supplied schedule must be validated before being treated as current.
        self._schedule_needs_review = initial.accepted_schedule is not None

    @property
    def snapshot(self) -> Snapshot[StateT, ScheduleT]:
        return deepcopy(self._state)

    @property
    def proposal(self) -> Optional[Proposal[ScheduleT]]:
        return deepcopy(self._proposal)

    @property
    def outcomes(self) -> tuple[Outcome, ...]:
        return tuple(self._outcomes)

    @property
    def schedule_needs_review(self) -> bool:
        return self._schedule_needs_review

    @property
    def metrics(self) -> dict[str, int]:
        return {
            "events_applied": len(self._seen_events),
            "stale_results": sum(o.status == "stale" for o in self._outcomes),
            "timeouts": sum(o.status == "timeout" for o in self._outcomes),
            "validation_rejections": sum(
                o.status in ("rejected", "acceptance_rejected") for o in self._outcomes
            ),
        }

    def _check_loop(self) -> None:
        if self._closed:
            raise RuntimeError("Coordinator is closed")
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise RuntimeError("Use the coordinator from a single event loop")
        self._loop = loop

    def submit(self, event: HospitalEvent) -> None:
        """Apply an event atomically, then request asynchronous replanning."""
        self._check_loop()
        if event.event_id in self._seen_events:
            raise ValueError("Duplicate event identifier")
        if event.simulation_time < self._state.simulation_time:
            raise ValueError("Events must arrive in nondecreasing simulation time")
        # Adapter failures cannot partially change the coordinator's state.
        domain = self._adapter.apply_event(self.snapshot, deepcopy(event))
        self._state = Snapshot(
            event.simulation_time, self._state.version + 1, deepcopy(domain),
            self._state.accepted_schedule,
        )
        self._seen_events.add(event.event_id)
        self._event_received_at = monotonic()
        self._proposal = None
        self._schedule_needs_review = self._state.accepted_schedule is not None
        self._pending = True
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="hospital-coordinator")

    def _validate(self, proposal: Proposal[ScheduleT]) -> ValidationResult:
        return self._validator.validate(self.snapshot, deepcopy(proposal))

    async def _run(self) -> None:
        while self._pending and not self._closed:
            self._pending = False
            snapshot = self.snapshot
            version = snapshot.version
            event_received_at = self._event_received_at
            started = monotonic()
            solver_seconds = 0.0
            try:
                commitments = deepcopy(self._adapter.fixed_commitments(deepcopy(snapshot)))
                request = SchedulingRequest(snapshot, commitments, started + self._timeout)
                candidate = await asyncio.wait_for(
                    self._scheduler.propose(request),
                    timeout=max(0.0, request.deadline - monotonic()),
                )
                solver_seconds = monotonic() - started
                if self._state.version != version:
                    self._record("stale", version, solver_seconds)
                    continue
                if candidate is None:
                    self._record("no_proposal", version, solver_seconds)
                    continue
                if candidate.base_version != version:
                    self._record("invalid_result", version, solver_seconds,
                                 reasons=("Solver returned a mismatched state version",))
                    continue
                # Disconnect the candidate from mutable objects owned by the solver.
                candidate = deepcopy(candidate)
                validation = self._validate(candidate)
                if not validation.feasible:
                    self._record("rejected", version, solver_seconds, reasons=validation.reasons)
                    continue
                self._proposal = candidate
                self._record("proposal_ready", version, solver_seconds,
                             latency=monotonic() - event_received_at)
            except asyncio.TimeoutError:
                self._record("timeout", version, monotonic() - started)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Exception messages may contain clinical inputs; record only the type.
                self._record("failed", version, solver_seconds or monotonic() - started,
                             reasons=(type(exc).__name__,))

    def _record(
        self, status: str, version: int, solver_seconds: float = 0.0,
        *, latency: Optional[float] = None, reasons: tuple[str, ...] = (),
    ) -> None:
        self._outcomes.append(Outcome(
            status, version, self._state.version, solver_seconds, latency, reasons,
        ))

    def accept(self, expected_version: int) -> ValidationResult:
        """Explicitly accept the current proposal; never accept caller-supplied schedules."""
        self._check_loop()
        if expected_version != self._state.version:
            result = ValidationResult(False, ("State changed; request a current proposal",))
            self._record("acceptance_stale", expected_version, reasons=result.reasons)
            return result
        if self._proposal is None:
            return ValidationResult(False, ("No validated proposal is available",))
        try:
            result = self._validate(self._proposal)
        except Exception as exc:
            result = ValidationResult(False, (type(exc).__name__,))
        if not result.feasible:
            self._record("acceptance_rejected", expected_version, reasons=result.reasons)
            self._proposal = None
            return result
        self._state = Snapshot(
            self._state.simulation_time, self._state.version + 1,
            self._state.domain, deepcopy(self._proposal.schedule),
        )
        self._proposal = None
        self._schedule_needs_review = False
        self._record("accepted", expected_version)
        return result

    async def wait_idle(self) -> None:
        """Wait for active work and any coalesced follow-up request."""
        if self._task is not None:
            await asyncio.shield(self._task)

    async def close(self) -> None:
        self._closed = True
        self._pending = False
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def __aenter__(self) -> "Coordinator[StateT, ScheduleT]":
        self._check_loop()
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()
