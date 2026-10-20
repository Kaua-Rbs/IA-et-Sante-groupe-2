"""Opt-in full-stay / feasibility-first problem for the EXISTING SA search.

No historical defaults, web interfaces or optimizer implementations are changed.
"""
from dataclasses import dataclass
from math import isfinite
from numbers import Integral
from time import monotonic

import numpy as np

from .optimizer import PlanningProblem, RunResult, simulated_annealing
from .search_control import SearchControl
from .validation import Validation, checked_inputs, validate_full_stay


class FullStayPlanningProblem(PlanningProblem):
    """Use an explicit bed horizon and strict complete assignment validation.

    objective_mode='weighted' changes accounting only. 'feasibility_first' uses
    cost b/(1 + 0.05*sum(durations)) for feasible plans, with b=0.05*std(loads),
    and 1 + 5*OR_overload + 3*bed_overload for infeasible plans. Thus feasible
    cost is strictly below 1, infeasible cost strictly above 1. Violations keep
    the legacy units/gradient; soft balance cannot compensate for a violation.
    This rescales feasible SA acceptance, so it is an objective intervention,
    not a scale-neutral comparison. All overloads use exact zero, no tolerance.
    """
    def __init__(self, patients_df, vacations_df, bed_capacities, *, patient_options=None,
                 objective_mode="weighted"):
        if objective_mode not in ("weighted", "feasibility_first"):
            raise ValueError("Unknown objective_mode")
        options, beds, _ = checked_inputs(patients_df, vacations_df, bed_capacities, patient_options)
        super().__init__(patients_df.copy(), vacations_df.copy(),
                         lits_capacity=beds[:int(vacations_df.jour.max()) + 1] if len(vacations_df) else beds[:1],
                         patient_options=options)
        self.n_bed_days = len(beds)
        self._lits_capacity_arr = np.asarray(beds, dtype=float)
        self.bed_capacities = beds
        self.objective_mode = objective_mode
        self._allowed = tuple(frozenset(x) for x in options)
        self._soft_bound = 1.0 + self.w_balance * float(self._pat_duree.sum())
        if not isfinite(self._soft_bound):
            raise ValueError("Durations exceed finite scoring range")

    def _validate_assignment(self, solution):
        if (not isinstance(solution, dict) or set(solution) != set(range(self.n_patients))
                or any(isinstance(i, bool) or not isinstance(i, Integral)
                       or isinstance(j, bool) or not isinstance(j, Integral)
                       or j not in self._allowed[i] for i, j in solution.items())):
            raise ValueError("A complete, valid, allowed integer assignment is required")

    def _occupation(self, pids, vacs):
        starts = self._vac_day[vacs]
        ends = starts + self._pat_sejour[pids] + 1
        delta = np.zeros(self.n_bed_days + 1)
        np.add.at(delta, starts, 1)
        np.add.at(delta, ends, -1)
        return np.cumsum(delta[:-1])

    def components(self, solution):
        self._validate_assignment(solution)
        pids = np.fromiter(solution.keys(), dtype=int, count=len(solution))
        vacs = np.fromiter(solution.values(), dtype=int, count=len(solution))
        loads = np.zeros(self.n_vacations)
        np.add.at(loads, vacs, self._pat_duree[pids])
        room_over = float(np.maximum(0, loads - self._vac_capacity).sum())
        beds_over = float(np.maximum(0, self._occupation(pids, vacs) - self._lits_capacity_arr).sum())
        balance = float(loads.std()) if len(loads) else 0.0
        return room_over, beds_over, balance

    def fitness(self, solution):
        room, beds, balance = self.components(solution)
        violations = self.w_vacation * room + self.w_lits * beds
        soft = self.w_balance * balance
        if self.objective_mode == "weighted":
            return -(violations + soft)
        return -(soft / self._soft_bound if room == 0 and beds == 0 else 1.0 + violations)

    def violations(self, solution):
        return self.components(solution)[:2]

    def occupation_lits(self, solution):
        self._validate_assignment(solution)
        return super().occupation_lits(solution)


@dataclass
class ValidatedSARun:
    result: RunResult
    validation: Validation
    best_feasible_solution: dict | None
    best_feasible_balance: float | None
    first_feasible_evaluation: int | None
    first_feasible_seconds: float | None


def run_validated_sa(problem: FullStayPlanningProblem, *, initial_solution, seed=0,
                     max_evaluations=3000, T0=50.0, alpha=0.95, safety_seconds=30.0,
                     legacy_accounting=False):
    """Run existing SA; retain best feasible evaluated candidate separately.

    Evaluations include initialization. Feasibility incumbents use vectorized
    components, and both final/incumbent plans pass the independent calendar
    validator before returning. No patient is dropped. Timing is descriptive.
    """
    if (isinstance(max_evaluations, bool) or not isinstance(max_evaluations, Integral)
            or max_evaluations < 1 or not isfinite(T0) or T0 <= 0
            or not 0 < alpha <= 1 or not isfinite(safety_seconds) or safety_seconds <= 0):
        raise ValueError("Invalid SA settings or safety deadline")
    problem._validate_assignment(initial_solution)
    if legacy_accounting and problem.objective_mode != "weighted":
        raise ValueError("Legacy accounting is only an unchanged weighted baseline")
    scoring_problem = (PlanningProblem(problem.patients, problem.vacations,
                        lits_capacity=problem.bed_capacities[:problem.n_days],
                        patient_options=problem._patient_options)
                       if legacy_accounting else problem)
    best_feasible, best_balance, first_eval, first_seconds = None, None, None, None

    # Monitor each actual evaluation once without touching the legacy loop.
    class ObservedProblem:
        def __getattr__(self, name):
            return getattr(problem, name)

        def fitness(self, solution):
            nonlocal best_feasible, best_balance, first_eval, first_seconds
            value = scoring_problem.fitness(solution)
            room, beds, balance = problem.components(solution)
            if room == 0 and beds == 0:
                if first_eval is None:
                    first_eval = control.evaluations + 1
                    first_seconds = monotonic() - control.started
                if best_balance is None or balance < best_balance:
                    best_feasible, best_balance = dict(solution), balance
            return value

    control = SearchControl(max_evaluations=max_evaluations, deadline=monotonic() + safety_seconds)
    result = simulated_annealing(ObservedProblem(), seed=seed, T0=T0, alpha=alpha,
                                 n_iter=max_evaluations if problem.n_patients else 0,
                                 initial_solution=initial_solution, control=control)
    report = validate_full_stay(problem.patients, problem.vacations, problem.bed_capacities,
                                result.meilleure_solution, problem._patient_options)
    if not report.valid:
        raise AssertionError(f"Invalid SA result: {report.errors}")
    if best_feasible is not None:
        checked = validate_full_stay(problem.patients, problem.vacations, problem.bed_capacities,
                                    best_feasible, problem._patient_options)
        if not checked.feasible:
            raise AssertionError("Feasible incumbent failed independent validation")
    if problem.objective_mode == "feasibility_first" and best_feasible is not None and not report.feasible:
        raise AssertionError("Feasibility-first best lost a feasible incumbent")
    return ValidatedSARun(result, report, best_feasible, best_balance, first_eval, first_seconds)
