import asyncio
from dataclasses import replace
import unittest

from hospital_sim import Coordinator
from hospital_sim.contracts import EventKind, HospitalEvent, Proposal, Snapshot, ValidationResult
from hospital_sim.demo import (
    DemoLOSPredictor, DemoRoomDurationPredictor, DemoSchedule, DemoScheduler,
    DemoState, DemoStateAdapter, DemoValidator, outage,
)


class CoordinationTests(unittest.IsolatedAsyncioTestCase):
    def make_coordinator(self, scheduler=None, validator=None, **kwargs):
        initial = Snapshot(0.0, 0, DemoState(frozenset({"a", "b", "c"})), DemoSchedule("a"))
        coordinator = Coordinator(
            initial, DemoStateAdapter(), scheduler or DemoScheduler(),
            validator or DemoValidator(), **kwargs,
        )
        self.addAsyncCleanup(coordinator.close)
        return coordinator

    async def idle(self, coordinator):
        await asyncio.wait_for(coordinator.wait_idle(), timeout=2.0)

    async def test_proposal_requires_explicit_acceptance_and_revalidation(self):
        class CountingValidator(DemoValidator):
            calls = 0

            def validate(self, snapshot, proposal):
                self.calls += 1
                return super().validate(snapshot, proposal)

        validator = CountingValidator()
        coordinator = self.make_coordinator(validator=validator)
        coordinator.submit(outage("1", 1.0, "a"))
        await self.idle(coordinator)
        self.assertEqual(coordinator.snapshot.accepted_schedule, DemoSchedule("a"))
        self.assertTrue(coordinator.schedule_needs_review)
        self.assertEqual(coordinator.proposal.schedule, DemoSchedule("b"))
        self.assertEqual(validator.calls, 1)
        self.assertTrue(coordinator.accept(1).feasible)
        self.assertEqual(validator.calls, 2)
        self.assertEqual(coordinator.snapshot.accepted_schedule, DemoSchedule("b"))
        self.assertEqual(coordinator.snapshot.version, 2)
        self.assertFalse(coordinator.schedule_needs_review)
        self.assertIsNone(coordinator.proposal)
        ready = next(o for o in coordinator.outcomes if o.status == "proposal_ready")
        self.assertGreaterEqual(ready.solver_seconds, 0)
        self.assertGreaterEqual(ready.event_to_proposal_seconds, ready.solver_seconds)

    async def test_events_during_computation_are_coalesced_and_stale_result_discarded(self):
        scheduler = DemoScheduler(pause_first=True)
        coordinator = self.make_coordinator(scheduler)
        coordinator.submit(outage("1", 1.0, "a"))
        await asyncio.wait_for(scheduler.started.wait(), 2.0)
        coordinator.submit(outage("2", 2.0, "b"))
        coordinator.submit(outage("3", 3.0, "c"))
        scheduler.release.set()
        await self.idle(coordinator)
        self.assertEqual(scheduler.request_versions, [1, 3])
        self.assertEqual([o.status for o in coordinator.outcomes], ["stale", "no_proposal"])
        self.assertEqual(coordinator.metrics["stale_results"], 1)
        self.assertIsNone(coordinator.proposal)
        self.assertEqual(coordinator.snapshot.accepted_schedule, DemoSchedule("a"))

    async def test_new_event_invalidates_previously_exposed_proposal(self):
        coordinator = self.make_coordinator()
        coordinator.submit(outage("1", 1.0, "a"))
        await self.idle(coordinator)
        old_version = coordinator.proposal.base_version
        coordinator.submit(outage("2", 2.0, "b"))
        self.assertIsNone(coordinator.proposal)
        self.assertFalse(coordinator.accept(old_version).feasible)
        await self.idle(coordinator)
        self.assertEqual(coordinator.proposal.schedule, DemoSchedule("c"))

    async def test_infeasible_candidate_is_not_exposed(self):
        class InvalidScheduler:
            async def propose(self, request):
                return Proposal(DemoSchedule("a"), request.snapshot.version)

        coordinator = self.make_coordinator(InvalidScheduler())
        coordinator.submit(outage("1", 1.0, "a"))
        await self.idle(coordinator)
        self.assertIsNone(coordinator.proposal)
        self.assertEqual(coordinator.outcomes[-1].status, "rejected")
        self.assertEqual(coordinator.metrics["validation_rejections"], 1)

    async def test_acceptance_can_fail_revalidation(self):
        class ChangingValidator(DemoValidator):
            allowed = True

            def validate(self, snapshot, proposal):
                return ValidationResult(self.allowed, () if self.allowed else ("Synthetic rejection",))

        validator = ChangingValidator()
        coordinator = self.make_coordinator(validator=validator)
        coordinator.submit(outage("1", 1.0, "a"))
        await self.idle(coordinator)
        validator.allowed = False
        self.assertFalse(coordinator.accept(1).feasible)
        self.assertIsNone(coordinator.proposal)
        self.assertEqual(coordinator.snapshot.accepted_schedule, DemoSchedule("a"))
        self.assertEqual(coordinator.outcomes[-1].status, "acceptance_rejected")

    async def test_wrong_solver_version_is_rejected(self):
        class WrongVersionScheduler:
            async def propose(self, request):
                return Proposal(DemoSchedule("b"), 100)

        coordinator = self.make_coordinator(WrongVersionScheduler())
        coordinator.submit(outage("1", 1.0, "a"))
        await self.idle(coordinator)
        self.assertEqual(coordinator.outcomes[-1].status, "invalid_result")
        self.assertIsNone(coordinator.proposal)

    async def test_unsupported_invalid_duplicate_and_out_of_order_events(self):
        coordinator = self.make_coordinator()
        unsupported = HospitalEvent("1", 1.0, EventKind.EMERGENCY_ARRIVAL, {})
        with self.assertRaises(NotImplementedError):
            coordinator.submit(unsupported)
        with self.assertRaises(ValueError):
            coordinator.submit(outage("1", 1.0, "unknown"))
        self.assertEqual(coordinator.snapshot.version, 0)
        coordinator.submit(outage("1", 2.0, "a"))
        with self.assertRaises(ValueError):
            coordinator.submit(outage("1", 3.0, "b"))
        with self.assertRaises(ValueError):
            coordinator.submit(outage("2", 1.0, "b"))
        await self.idle(coordinator)
        self.assertEqual(coordinator.snapshot.version, 1)
        self.assertEqual(coordinator.metrics["events_applied"], 1)

    async def test_failures_are_recorded_without_exception_payloads(self):
        class FailingScheduler:
            async def propose(self, request):
                raise RuntimeError("sensitive input must not appear in outcomes")

        coordinator = self.make_coordinator(FailingScheduler())
        coordinator.submit(outage("1", 1.0, "a"))
        await self.idle(coordinator)
        self.assertEqual(coordinator.outcomes[-1].status, "failed")
        self.assertEqual(coordinator.outcomes[-1].reasons, ("RuntimeError",))
        self.assertTrue(coordinator.schedule_needs_review)

    async def test_timeout_cancels_cooperative_solver(self):
        cancelled = asyncio.Event()

        class BlockedScheduler:
            async def propose(self, request):
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        coordinator = self.make_coordinator(BlockedScheduler(), timeout_seconds=0.01)
        coordinator.submit(outage("1", 1.0, "a"))
        await self.idle(coordinator)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(coordinator.outcomes[-1].status, "timeout")
        self.assertEqual(coordinator.metrics["timeouts"], 1)
        self.assertIsNone(coordinator.proposal)

    async def test_close_cancels_active_work_and_rejects_new_events(self):
        started, cancelled = asyncio.Event(), asyncio.Event()

        class BlockedScheduler:
            async def propose(self, request):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        coordinator = self.make_coordinator(BlockedScheduler())
        coordinator.submit(outage("1", 1.0, "a"))
        await asyncio.wait_for(started.wait(), 2.0)
        await coordinator.close()
        self.assertTrue(cancelled.is_set())
        with self.assertRaises(RuntimeError):
            coordinator.submit(outage("2", 2.0, "b"))
        await coordinator.close()  # Idempotent shutdown.

    async def test_mutable_payloads_and_schedules_cannot_leak_across_boundaries(self):
        class Adapter:
            def apply_event(self, snapshot, event):
                snapshot.domain["values"].append(event.payload["value"])
                event.payload["extra"] = "adapter mutation"
                return snapshot.domain

            def fixed_commitments(self, snapshot):
                snapshot.domain["values"].append("commitment mutation")
                return []

        class Scheduler:
            schedule = {"values": ["proposed"]}

            async def propose(self, request):
                request.snapshot.domain["values"].append("solver mutation")
                return Proposal(self.schedule, request.snapshot.version)

        class Validator:
            def validate(self, snapshot, proposal):
                snapshot.domain["values"].append("validator mutation")
                proposal.schedule["values"].append("validator mutation")
                return ValidationResult(True)

        original = Snapshot(0.0, 0, {"values": []}, {"values": ["original"]})
        scheduler = Scheduler()
        coordinator = Coordinator(original, Adapter(), scheduler, Validator())
        self.addAsyncCleanup(coordinator.close)
        original.domain["values"].append("external mutation")
        payload = {"value": "event"}
        coordinator.submit(HospitalEvent("1", 1.0, EventKind.CANCELLATION, payload))
        await self.idle(coordinator)
        coordinator.snapshot.domain["values"].append("reader mutation")
        coordinator.proposal.schedule["values"].append("reader mutation")
        scheduler.schedule["values"].append("late solver mutation")
        self.assertEqual(coordinator.snapshot.domain, {"values": ["event"]})
        self.assertEqual(coordinator.proposal.schedule, {"values": ["proposed"]})
        self.assertNotIn("extra", payload)
        self.assertTrue(coordinator.accept(1).feasible)
        self.assertEqual(coordinator.snapshot.accepted_schedule, {"values": ["proposed"]})

    async def test_event_adapter_failure_is_atomic(self):
        class BrokenAdapter(DemoStateAdapter):
            def apply_event(self, snapshot, event):
                raise ValueError("Invalid event")

        initial = Snapshot(0.0, 0, DemoState(frozenset({"a"})), DemoSchedule("a"))
        coordinator = Coordinator(initial, BrokenAdapter(), DemoScheduler(), DemoValidator())
        self.addAsyncCleanup(coordinator.close)
        with self.assertRaises(ValueError):
            coordinator.submit(outage("1", 1.0, "a"))
        self.assertEqual(coordinator.snapshot, initial)
        self.assertEqual(coordinator.outcomes, ())

    async def test_fixed_commitment_is_preserved_or_no_proposal_returned(self):
        for fixed_room, expected in (("b", "proposal_ready"), ("a", "no_proposal")):
            with self.subTest(fixed_room=fixed_room):
                initial = Snapshot(0.0, 0, DemoState(frozenset({"a", "b"}), fixed_room))
                coordinator = Coordinator(initial, DemoStateAdapter(), DemoScheduler(), DemoValidator())
                self.addAsyncCleanup(coordinator.close)
                coordinator.submit(outage("1", 1.0, "a"))
                await self.idle(coordinator)
                self.assertEqual(coordinator.outcomes[-1].status, expected)


class PredictionContractTests(unittest.TestCase):
    def test_test_doubles_label_targets_and_uncertainty(self):
        los = DemoLOSPredictor().predict(None)
        room = DemoRoomDurationPredictor().predict(None)
        self.assertEqual(los.unit, "inclusive_calendar_days")
        self.assertEqual(room.unit, "minutes")
        self.assertIsNotNone(los.interval)
        self.assertIsNotNone(room.interval)
        with self.assertRaises(ValueError):
            replace(room, value=float("nan"))
        with self.assertRaises(ValueError):
            replace(los, interval=(3.0, 1.0))


if __name__ == "__main__":
    unittest.main()
