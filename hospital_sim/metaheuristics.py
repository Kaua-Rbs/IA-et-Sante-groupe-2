"""Async scheduler adapters: five searches in killable, isolated processes."""

import asyncio
from dataclasses import asdict, dataclass
import multiprocessing as mp
from time import monotonic

from optimiseur import optimizer as op
from optimiseur.search_control import SearchControl, SearchStopped
from .contracts import Proposal
from .room_problem import RoomAllocationProblem
from .scheduling import BaselineScheduler, RoomValidator

METHODS = ("baseline", "annealing", "tabu", "genetic", "hybrid", "aco")
FUNCTIONS = {
    "annealing": op.simulated_annealing, "tabu": op.tabu_search,
    "genetic": op.genetic_algorithm, "hybrid": op.tabu_simulated_annealing,
    "aco": op.ant_colony_optimization,
}


@dataclass(frozen=True)
class SearchSettings:
    method: str = "baseline"
    seed: int = 0
    max_evaluations: int = 5000
    budget_mode: str = "evaluations"

    def __post_init__(self):
        if self.method not in METHODS:
            raise ValueError("Unknown optimization method")
        if self.max_evaluations < 1 or self.budget_mode not in ("evaluations", "time"):
            raise ValueError("Invalid search budget")

    def parameters(self):
        # The shared budget stops the search, not method-specific iteration counts.
        ceiling = self.max_evaluations + 1 if self.budget_mode == "evaluations" else 10**9
        return {
            "baseline": {},
            "annealing": {"T0": 1.0, "alpha": 0.95, "n_iter": ceiling},
            "tabu": {"tabu_size": 20, "neighborhood_size": 15, "n_iter": ceiling},
            "genetic": {"pop_size": 40, "n_gen": ceiling, "p_cross": 0.8,
                        "p_mut": 0.08, "elitisme": True},
            "hybrid": {"T0": 1.0, "alpha": 0.97, "tabu_size": 20,
                       "neighborhood_size": 15, "n_iter": ceiling},
            "aco": {"n_ants": 15, "n_iter": ceiling, "alpha": 1.0,
                    "beta": 2.0, "rho": 0.3, "Q": 1.0},
        }[self.method]


def _search_worker(connection, request, settings, deadline):
    """Top-level spawn target; only optimizer-visible request data cross the pipe."""
    try:
        problem = RoomAllocationProblem(request)
        last_sent = 0.0
        def publish(control, improved, *, final=False):
            nonlocal last_sent
            now = monotonic()
            if not final and not improved and now - last_sent < 0.1:
                return
            last_sent = now
            connection.send({
                "allocation": control.best, "evaluations": control.evaluations,
                "history": list(control.history),
                "stop_reason": control.reason if final else None,
            })
        control = SearchControl(
            settings.max_evaluations if settings.budget_mode == "evaluations" else None,
            deadline, publish,
        )
        try:
            FUNCTIONS[settings.method](
                problem, seed=settings.seed, initial_solution=problem.initial_allocation(),
                control=control, **settings.parameters(),
            )
        except SearchStopped:
            pass  # Deadline may precede the first evaluation after process startup.
        if control.best is not None:
            control.history.append((control.evaluations, monotonic() - control.started,
                                    control.best_fitness, control.best_fitness))
        publish(control, False, final=True)
    except Exception as exc:
        connection.send({"error": type(exc).__name__})
    finally:
        connection.close()


class MetaheuristicScheduler:
    def __init__(self, settings=SearchSettings()):
        self.settings = settings
        self.reports = []

    async def propose(self, request):
        started = monotonic()
        problem = RoomAllocationProblem(request)
        initial = problem.initial_allocation()
        schedule = problem.decode(initial)
        report = {
            "method": self.settings.method, "seed": self.settings.seed,
            "state_version": request.snapshot.version, "minute": problem.state.minute,
            "parameters": self.settings.parameters(), "budget_mode": self.settings.budget_mode,
            "max_evaluations": self.settings.max_evaluations,
            "evaluations": 0, "history": [], "stop_reason": "trivial",
        }
        self.reports.append(report)
        try:
            if self.settings.method == "baseline":
                proposal = await BaselineScheduler().propose(request)
                if proposal is not None:
                    schedule = proposal.schedule
                report["stop_reason"] = "baseline"
            elif problem.n_patients and problem.n_vacations:
                if problem.n_patients == 1:
                    # Exact tiny request, still honor both kinds of budget.
                    control = SearchControl(
                        self.settings.max_evaluations if self.settings.budget_mode == "evaluations" else None,
                        request.deadline,
                    )
                    try:
                        control.evaluate(problem, initial)
                        for room in range(problem.n_vacations):
                            if {0: room} != initial:
                                control.evaluate(problem, {0: room})
                        control.reason = "exact"
                    except SearchStopped:
                        pass
                    schedule = problem.decode(control.best or initial)
                    report.update(evaluations=control.evaluations, history=control.history,
                                  stop_reason=control.reason)
                else:
                    allocation = await self._run_process(request, problem, initial, report)
                    schedule = problem.decode(allocation)
            candidate = Proposal(schedule, request.snapshot.version)
            validation = RoomValidator().validate(request.snapshot, candidate)
            if not validation.feasible:
                report["stop_reason"] = "invalid_result"
                return None
            report["objective"] = asdict(problem.objective(schedule))
            return candidate
        except asyncio.CancelledError:
            report["stop_reason"] = "cancelled"
            raise
        finally:
            report["elapsed_seconds"] = monotonic() - started

    async def _run_process(self, request, problem, initial, report):
        remaining = request.deadline - monotonic()
        if remaining <= 0.02:
            report["stop_reason"] = "deadline"
            return initial
        parent, child = mp.get_context("spawn").Pipe(duplex=False)
        # Leave a little time for IPC, validation and coordinator acceptance.
        deadline = request.deadline - min(0.05, remaining / 10)
        parent_deadline = request.deadline - min(0.01, remaining / 20)
        process = mp.get_context("spawn").Process(
            target=_search_worker, args=(child, request, self.settings, deadline),
            name=f"hospital-{self.settings.method}",
        )
        best, finished = initial, False
        try:
            process.start()
            child.close()
            while monotonic() < parent_deadline:
                if parent.poll():
                    try:
                        message = parent.recv()
                    except EOFError:
                        break
                    if "error" in message:
                        report.update(stop_reason="worker_error", error_type=message["error"])
                        finished = True
                        break
                    if message["allocation"] is not None:
                        # Ensure malformed progress cannot replace a valid incumbent.
                        problem.decode(message["allocation"])
                        best = message["allocation"]
                    report.update(evaluations=message["evaluations"], history=message["history"])
                    if message["stop_reason"] is not None:
                        report["stop_reason"] = message["stop_reason"]
                        finished = True
                        break
                elif not process.is_alive():
                    break
                else:
                    await asyncio.sleep(0.002)
            if not finished:
                report["stop_reason"] = "deadline" if monotonic() >= parent_deadline else "worker_error"
            return best
        finally:
            child.close()
            # No await here: cancellation must not orphan the CPU-bound worker.
            if process.pid is not None:
                process.join(timeout=0.02)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=0.2)
                if process.is_alive():
                    process.kill()
                    process.join()
                process.close()
            parent.close()
