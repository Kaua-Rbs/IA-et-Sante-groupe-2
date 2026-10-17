"""Common allocation decoder and lexicographic room objective; no outcomes."""

from dataclasses import asdict, dataclass
from numbers import Integral

import numpy as np

from optimiseur.optimizer import PlanningProblem
from .domain import Assignment, Schedule
from .scheduling import next_start


@dataclass(frozen=True)
class Objective:
    unstarted: int
    overtime: int
    changes: int
    cost: float


class RoomAllocationProblem:
    """Duck-typed PlanningProblem: reuse moves, replace the native objective."""

    random_solution = PlanningProblem.random_solution
    neighbor = PlanningProblem.neighbor
    _options_for = PlanningProblem._options_for

    def __init__(self, request):
        self.state = request.snapshot.domain
        self.cases = tuple(sorted((c.case for c in self.state.cases if c.status == "waiting"),
                                  key=lambda c: c.case_id))
        self.rooms = tuple(sorted(self.state.rooms, key=lambda r: r.room_id))
        self.fixed = tuple(request.fixed_commitments)
        self.accepted = request.snapshot.accepted_schedule
        self.n_patients, self.n_vacations = len(self.cases), len(self.rooms)
        self._pat_duree = np.array([c.predicted_minutes for c in self.cases], dtype=float)
        self._vac_capacity = np.array([max(1, self.state.closing - max(
            self.state.minute, self.state.opening, r.available_at)) for r in self.rooms], dtype=float)
        self._patient_options = [np.arange(self.n_vacations) for _ in self.cases]
        self._patients_par_specialite = {"all": np.arange(self.n_patients)}
        self._order = sorted(range(self.n_patients),
                             key=lambda i: (self.cases[i].predicted_minutes, self.cases[i].case_id))
        self.overtime_bound = sum(c.predicted_minutes + self.state.turnover for c in self.cases)

    def initial_allocation(self):
        """Preserve known room choices; place previously unassigned cases greedily."""
        if not self.rooms:
            return {}
        old = {a.case_id: a.room_id for a in (self.accepted or Schedule()).assignments}
        room_indices = {room.room_id: i for i, room in enumerate(self.rooms)}
        available = [max(self.state.minute, self.state.opening, room.available_at) for room in self.rooms]
        allocation = {}
        for i in self._order:
            case = self.cases[i]
            if old.get(case.case_id) in room_indices:
                room_index = room_indices[old[case.case_id]]
            else:
                room_index = min(range(self.n_vacations), key=lambda j: (
                    next_start(self.state, self.rooms[j].room_id, available[j]), self.rooms[j].room_id))
            start = next_start(self.state, self.rooms[room_index].room_id, available[room_index])
            allocation[i] = room_index
            if start < self.state.closing:
                available[room_index] = start + case.predicted_minutes + self.state.turnover
        return allocation

    def decode(self, solution):
        if not self.rooms and not solution:
            return Schedule(self.fixed, tuple(c.case_id for c in self.cases))
        if set(solution) != set(range(self.n_patients)):
            raise ValueError("Allocation must cover every waiting case")
        if any(not isinstance(i, Integral) or isinstance(i, bool) for i in solution):
            raise ValueError("Case indices must be integers")
        if any(not isinstance(v, Integral) or isinstance(v, bool) or not 0 <= v < self.n_vacations
               for v in solution.values()):
            raise ValueError("Unknown room index")
        available = [max(self.state.minute, self.state.opening, room.available_at) for room in self.rooms]
        assignments, unassigned = list(self.fixed), []
        for i in self._order:
            case = self.cases[i]
            j = solution[i]
            room = self.rooms[j].room_id
            start = next_start(self.state, room, available[j])
            if start >= self.state.closing:
                unassigned.append(case.case_id)
                continue
            assignments.append(Assignment(case.case_id, room, start, case.predicted_minutes))
            available[j] = start + case.predicted_minutes + self.state.turnover
        return Schedule(tuple(assignments), tuple(sorted(unassigned)))

    def objective(self, schedule):
        waiting = {c.case_id for c in self.cases}
        current = {a.case_id: a for a in schedule.assignments if a.case_id in waiting}
        overtime = sum(max(0, a.start + a.duration + self.state.turnover
                           - max(a.start, self.state.closing)) for a in current.values())
        old = {a.case_id: a for a in (self.accepted or Schedule()).assignments}
        changes = sum(current.get(key) != old.get(key) for key in waiting) if self.accepted is not None else 0
        unstarted = len(schedule.unassigned)
        cost = unstarted + (overtime + changes / (self.n_patients + 1)) / (self.overtime_bound + 1)
        return Objective(unstarted, overtime, changes, cost)

    def fitness(self, solution):
        return -self.objective(self.decode(solution)).cost

    def describe(self, solution):
        return asdict(self.objective(self.decode(solution)))
