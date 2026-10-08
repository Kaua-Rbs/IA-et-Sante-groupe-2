"""Budget, solution initiale et suivi communs pour les recherches compatibles."""

from dataclasses import dataclass, field
from functools import wraps
from math import isfinite
from time import monotonic
from typing import Callable

import pandas as pd


class SearchStopped(Exception):
    """Arret normal au budget, distinct d'une erreur d'algorithme."""


@dataclass
class SearchControl:
    max_evaluations: int | None = None
    deadline: float | None = None
    on_progress: Callable | None = None
    evaluations: int = field(default=0, init=False)
    best: dict | None = field(default=None, init=False)
    best_fitness: float = field(default=float("-inf"), init=False)
    reason: str = field(default="iterations", init=False)
    history: list = field(default_factory=list, init=False)
    started: float = field(default_factory=monotonic, init=False)

    def __post_init__(self):
        if self.max_evaluations is not None and self.max_evaluations < 1:
            raise ValueError("max_evaluations doit etre positif")
        if self.deadline is not None and not isfinite(self.deadline):
            raise ValueError("deadline doit etre finie")

    def evaluate(self, problem, solution):
        if self.deadline is not None and monotonic() >= self.deadline:
            self.reason = "deadline"
            raise SearchStopped
        if self.max_evaluations is not None and self.evaluations >= self.max_evaluations:
            self.reason = "evaluations"
            raise SearchStopped
        value = problem.fitness(solution)
        if not isfinite(value):
            raise ValueError("Fitness non finie")
        self.evaluations += 1
        improved = self.best is None or value > self.best_fitness
        if improved:
            self.best, self.best_fitness = dict(solution), value
        # Historique compact des ameliorations, plus un point terminal.
        if improved:
            self.history.append((self.evaluations, monotonic() - self.started, value, self.best_fitness))
        if self.on_progress is not None:
            self.on_progress(self, improved)
        return value


class _ControlledProblem:
    def __init__(self, problem, control, initial):
        self._problem = problem
        self._control = control
        self._initial = dict(initial) if initial is not None else None

    def __getattr__(self, name):
        return getattr(self._problem, name)

    def fitness(self, solution):
        return self._control.evaluate(self._problem, solution)

    def random_solution(self, rng=None):
        if self._initial is not None:
            initial, self._initial = self._initial, None
            return initial
        return self._problem.random_solution(rng)


def controlled_search(function):
    """Les appels historiques gardent leurs parametres et leur comportement."""
    @wraps(function)
    def wrapped(problem, *args, initial_solution=None, control=None, **kwargs):
        if control is None and initial_solution is None:
            return function(problem, *args, **kwargs)
        from .optimizer import RunResult, HISTORY_COLUMNS, METHOD_NAMES
        control = control or SearchControl()
        proxy = _ControlledProblem(problem, control, initial_solution)
        try:
            if initial_solution is not None:
                control.evaluate(problem, initial_solution)
            function(proxy, *args, **kwargs)
        except SearchStopped:
            pass
        if control.best is None:
            raise SearchStopped("Aucune evaluation terminee")
        elapsed = monotonic() - control.started
        rows = control.history + [(control.evaluations, elapsed, control.best_fitness, control.best_fitness)]
        return RunResult(
            METHOD_NAMES[function.__name__], control.best, control.best_fitness,
            pd.DataFrame(rows, columns=HISTORY_COLUMNS), elapsed,
            control.evaluations, control.reason,
        )
    return wrapped
