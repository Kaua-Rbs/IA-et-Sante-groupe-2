"""
optimizer.py
------------
Coeur du moteur d'optimisation du bloc operatoire.

Entree  : deux tables pandas (patients, vacations)
Sortie  : un planning optimise (dict patient_id -> vacation_id) pour
          chacune des metaheuristiques (recuit simule, tabou, genetique,
          hybride tabou x recuit, fourmis/ACO), accompagne de l'historique
          de convergence.

Aucune dependance autre que pandas / numpy pour le calcul. matplotlib
n'est utilise que dans plotting.py.
"""

from __future__ import annotations

import itertools
import random
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
import pandas as pd

# Noms des methodes : source de verite unique, reutilisee par plotting.py,
# app_gui.py et run_demo.py.
METHODE_RECUIT = "Recuit simule"
METHODE_TABOU = "Tabou"
METHODE_GENETIQUE = "Genetique"
METHODE_HYBRIDE = "Tabou x Recuit"
METHODE_FOURMIS = "Fourmis (ACO)"

HISTORY_COLUMNS = ["iteration", "time_s", "fitness_courante", "meilleure_fitness"]

# --------------------------------------------------------------------------
# 1. Generation d'un jeu de donnees de test
# --------------------------------------------------------------------------

DEFAULT_SPECIALITES = ["Orthopedie", "Digestif", "Cardio", "ORL"]


def generate_test_data(
    n_patients: int = 40,
    n_days: int = 5,
    specialites=None,
    vacations_par_jour_par_specialite: int = 1,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Genere un jeu de donnees synthetique (patients, vacations).

    patients_df  : patient_id, specialite, duree_operatoire (min), duree_sejour (jours)
    vacations_df : vacation_id, jour, specialite, capacite_min
    """
    rng = np.random.default_rng(seed)
    specialites = list(specialites or DEFAULT_SPECIALITES)

    vac_rows = []
    vac_id = 0
    for jour in range(n_days):
        for spec in specialites:
            for _ in range(vacations_par_jour_par_specialite):
                vac_rows.append(
                    {"vacation_id": vac_id, "jour": jour, "specialite": spec, "capacite_min": 240}
                )
                vac_id += 1
    vacations_df = pd.DataFrame(vac_rows)

    pat_rows = []
    for i in range(n_patients):
        pat_rows.append(
            {
                "patient_id": i,
                "specialite": rng.choice(specialites),
                "duree_operatoire": int(rng.integers(30, 150)),
                "duree_sejour": int(rng.integers(0, 5)),
            }
        )
    patients_df = pd.DataFrame(pat_rows)

    return patients_df, vacations_df


# --------------------------------------------------------------------------
# 2. Modele du probleme : fonction de qualite + generation de voisins
# --------------------------------------------------------------------------

# Une solution est un dict {patient_id (int) -> indice positionnel de vacation}.
# On utilise l'INDICE (0..n-1) et non vacation_id : c'est la convention interne
# utilisee par fitness(), neighbor() et exact_bruteforce().
Solution = dict


class PlanningProblem:
    """Represente une instance du probleme d'affectation patients -> vacations."""

    def __init__(
        self,
        patients_df: pd.DataFrame,
        vacations_df: pd.DataFrame,
        lits_capacity: int | Sequence[int] | np.ndarray = 42,
        vacation_delays: Sequence[float] | np.ndarray | None = None,
        w_vacation: float = 5.0,
        w_lits: float = 3.0,
        w_balance: float = 0.05,
    ):
        self.patients = patients_df.reset_index(drop=True)
        self.vacations = vacations_df.reset_index(drop=True)
        self.lits_capacity = lits_capacity
        self.w_vacation = w_vacation
        self.w_lits = w_lits
        self.w_balance = w_balance
        self.n_days = (
            int(self.vacations["jour"].max()) + 1 if len(self.vacations) > 0 else 1
        )
        self.n_vacations = len(self.vacations)
        self.n_patients = len(self.patients)

        # Tableaux numpy precalcules : evite les acces pandas .loc dans la
        # boucle chaude de fitness() (gain de vitesse important).
        self._pat_duree = self.patients["duree_operatoire"].to_numpy(dtype=float)
        self._pat_sejour = self.patients["duree_sejour"].to_numpy(dtype=int)
        self._pat_specialite = self.patients["specialite"].to_numpy()

        # Prise en compte de retards bloc imprevus (reduction de capacite utile)
        if vacation_delays is not None:
            self.vacation_delays = np.asarray(vacation_delays, dtype=float)
        else:
            self.vacation_delays = np.zeros(self.n_vacations, dtype=float)
        self._vac_capacity = np.maximum(
            0.0, self.vacations["capacite_min"].to_numpy(dtype=float) - self.vacation_delays
        )
        self._vac_day = self.vacations["jour"].to_numpy(dtype=int)

        # Prise en compte de capacite en lits vectorielle (par jour) ou scalaire
        if isinstance(lits_capacity, (int, float, np.integer, np.floating)):
            self._lits_capacity_arr = np.full(self.n_days, float(lits_capacity))
        else:
            self._lits_capacity_arr = np.asarray(lits_capacity, dtype=float)

        self.compatible = {
            spec: self.vacations.index[self.vacations["specialite"] == spec].tolist()
            for spec in self.vacations["specialite"].unique()
        }
        # secours si une specialite patient n'a aucune vacation dediee
        self._all_vac_idx = list(self.vacations.index)

        # Indices de patients par specialite (pour le mouvement de permutation)
        self._patients_par_specialite: dict[object, np.ndarray] = {
            spec: np.flatnonzero(self._pat_specialite == spec) for spec in self.compatible
        }
        # Options de vacation par patient, sous forme de tableaux numpy
        self._patient_options = [
            np.asarray(self.compatible.get(spec, self._all_vac_idx), dtype=int)
            for spec in self._pat_specialite
        ]

    def _options_for(self, pid: int):
        return self._patient_options[pid]

    # ---- solutions --------------------------------------------------
    def random_solution(self, rng: random.Random | None = None) -> Solution:
        rng = rng or random
        return {pid: int(rng.choice(self._patient_options[pid])) for pid in range(self.n_patients)}

    def neighbor(self, solution: Solution, rng: random.Random | None = None):
        """Renvoie (voisin, mouvement) — mouvement est un tuple hashable,
        utilise par la recherche tabou pour la liste taboue."""
        rng = rng or random
        sol2 = dict(solution)

        if rng.random() < 0.5 or self.n_patients < 2:
            pid = rng.randrange(self.n_patients)
            new_vac = int(rng.choice(self._patient_options[pid]))
            sol2[pid] = new_vac
            return sol2, ("reassign", pid, new_vac)

        spec = rng.choice(list(self._patients_par_specialite.keys()))
        same_spec = self._patients_par_specialite[spec]
        if len(same_spec) >= 2:
            p1, p2 = (int(p) for p in rng.sample(list(same_spec), 2))
            sol2[p1], sol2[p2] = sol2[p2], sol2[p1]
            return sol2, ("swap", min(p1, p2), max(p1, p2))

        pid = rng.randrange(self.n_patients)
        new_vac = int(rng.choice(self._patient_options[pid]))
        sol2[pid] = new_vac
        return sol2, ("reassign", pid, new_vac)

    # ---- qualite ------------------------------------------------------
    def _occupation(self, pids: np.ndarray, vacs: np.ndarray) -> np.ndarray:
        """Occupation des lits jour par jour via un tableau de differences."""
        day0 = self._vac_day[vacs]
        fin = np.minimum(day0 + self._pat_sejour[pids] + 1, self.n_days)
        delta = np.zeros(self.n_days + 1)
        np.add.at(delta, day0, 1)
        np.add.at(delta, fin, -1)
        return np.cumsum(delta[:-1])

    def fitness(self, solution: Solution) -> float:
        """Plus la fitness est proche de 0 (par valeurs negatives), meilleur
        est le planning. On maximise cette fitness."""
        pids = np.fromiter(solution.keys(), dtype=int, count=len(solution))
        vacs = np.fromiter(solution.values(), dtype=int, count=len(solution))

        charge = np.zeros(self.n_vacations)
        np.add.at(charge, vacs, self._pat_duree[pids])
        overflow_vac = float(np.maximum(0, charge - self._vac_capacity).sum())

        occ = self._occupation(pids, vacs)
        overflow_lits = float(np.maximum(0, occ - self._lits_capacity_arr).sum())

        balance = float(charge.std())

        cost = self.w_vacation * overflow_vac + self.w_lits * overflow_lits + self.w_balance * balance
        return -cost

    def occupation_lits(self, solution: Solution) -> np.ndarray:
        pids = np.fromiter(solution.keys(), dtype=int, count=len(solution))
        vacs = np.fromiter(solution.values(), dtype=int, count=len(solution))
        return self._occupation(pids, vacs)


# --------------------------------------------------------------------------
# 3. Les metaheuristiques
# --------------------------------------------------------------------------

@dataclass
class RunResult:
    nom: str
    meilleure_solution: Solution
    meilleure_fitness: float
    historique: pd.DataFrame  # colonnes : HISTORY_COLUMNS
    duree_s: float = field(default=0.0)


def format_duree(duree_s: float) -> str:
    """Formate une duree courte en millisecondes, sinon en secondes."""
    if duree_s < 1.0:
        return f"{duree_s * 1000:.2f} ms"
    return f"{duree_s:.2f} s"


def _finalize(
    nom: str,
    best: Solution,
    best_f: float,
    rows: list[tuple],
    t0: float,
    current_f: float,
    k: int,
) -> RunResult:
    """Ajoute le point terminal, fige la duree et renvoie le RunResult."""
    duree = time.perf_counter() - t0
    rows.append((k, duree, current_f, best_f))
    hist = pd.DataFrame(rows, columns=HISTORY_COLUMNS)
    return RunResult(nom, best, best_f, hist, duree)


def _record_every(n_iter: int, n_points: int = 300) -> int:
    """Pas d'echantillonnage de l'historique (au plus ~n_points lignes)."""
    return max(1, n_iter // n_points)


def simulated_annealing(
    problem: PlanningProblem,
    T0: float = 50.0,
    alpha: float = 0.95,
    n_iter: int = 3000,
    seed: int = 0,
) -> RunResult:
    rng = random.Random(seed)
    current = problem.random_solution(rng)
    current_f = problem.fitness(current)
    best, best_f = dict(current), current_f
    T = T0
    rows: list[tuple] = []
    step = _record_every(n_iter)
    t0 = time.perf_counter()
    for k in range(n_iter):
        neighbor, _ = problem.neighbor(current, rng)
        f_new = problem.fitness(neighbor)
        delta = f_new - current_f
        if delta >= 0 or rng.random() < np.exp(delta / max(T, 1e-9)):
            current, current_f = neighbor, f_new
            if current_f > best_f:
                best, best_f = dict(current), current_f
        T *= alpha
        if k % step == 0:
            rows.append((k, time.perf_counter() - t0, current_f, best_f))
    return _finalize(METHODE_RECUIT, best, best_f, rows, t0, current_f, n_iter)


def tabu_search(
    problem: PlanningProblem,
    n_iter: int = 250,
    tabu_size: int = 20,
    neighborhood_size: int = 15,
    seed: int = 0,
) -> RunResult:
    rng = random.Random(seed)
    current = problem.random_solution(rng)
    current_f = problem.fitness(current)
    best, best_f = dict(current), current_f
    tabu_list: deque = deque(maxlen=tabu_size)
    rows: list[tuple] = []
    step = _record_every(n_iter)
    t0 = time.perf_counter()
    for k in range(n_iter):
        candidats = []
        for _ in range(neighborhood_size):
            voisin, mouvement = problem.neighbor(current, rng)
            candidats.append((voisin, mouvement, problem.fitness(voisin)))
        candidats.sort(key=lambda c: c[2], reverse=True)

        choisi = None
        for voisin, mouvement, f_val in candidats:
            if (mouvement not in tabu_list) or (f_val > best_f):  # critere d'aspiration
                choisi = (voisin, mouvement, f_val)
                break
        if choisi is None:
            choisi = candidats[0]

        current, mouvement, current_f = choisi
        tabu_list.append(mouvement)
        if current_f > best_f:
            best, best_f = dict(current), current_f

        if k % step == 0:
            rows.append((k, time.perf_counter() - t0, current_f, best_f))
    return _finalize(METHODE_TABOU, best, best_f, rows, t0, current_f, n_iter)


def tabu_simulated_annealing(
    problem: PlanningProblem,
    n_iter: int = 400,
    tabu_size: int = 20,
    neighborhood_size: int = 15,
    T0: float = 20.0,
    alpha: float = 0.97,
    seed: int = 0,
) -> RunResult:
    """Hybride tabou x recuit simule.

    A chaque iteration, on explore un voisinage, on ecarte les mouvements
    tabous (sauf aspiration) et on retient le meilleur candidat admissible.
    L'acceptation de ce candidat suit ensuite la regle de Metropolis du
    recuit simule : un candidat non ameliorant n'est accepte qu'avec la
    probabilite exp(delta / T). Le meilleur global reste memorise.
    """
    rng = random.Random(seed)
    current = problem.random_solution(rng)
    current_f = problem.fitness(current)
    best, best_f = dict(current), current_f
    tabu_list: deque = deque(maxlen=tabu_size)
    T = T0
    rows: list[tuple] = []
    step = _record_every(n_iter)
    t0 = time.perf_counter()
    for k in range(n_iter):
        candidats = []
        for _ in range(neighborhood_size):
            voisin, mouvement = problem.neighbor(current, rng)
            candidats.append((voisin, mouvement, problem.fitness(voisin)))
        candidats.sort(key=lambda c: c[2], reverse=True)

        choisi = None
        for voisin, mouvement, f_val in candidats:
            if (mouvement not in tabu_list) or (f_val > best_f):
                choisi = (voisin, mouvement, f_val)
                break
        if choisi is None:
            choisi = candidats[0]

        voisin, mouvement, f_new = choisi
        delta = f_new - current_f
        if delta >= 0 or rng.random() < np.exp(delta / max(T, 1e-9)):
            current, current_f = voisin, f_new
            tabu_list.append(mouvement)
            if current_f > best_f:
                best, best_f = dict(current), current_f
        T *= alpha

        if k % step == 0:
            rows.append((k, time.perf_counter() - t0, current_f, best_f))
    return _finalize(METHODE_HYBRIDE, best, best_f, rows, t0, current_f, n_iter)


def genetic_algorithm(
    problem: PlanningProblem,
    pop_size: int = 40,
    n_gen: int = 150,
    p_cross: float = 0.8,
    p_mut: float = 0.08,
    elitisme: bool = True,
    seed: int = 0,
) -> RunResult:
    rng = random.Random(seed)
    pids = list(range(problem.n_patients))

    population = [problem.random_solution(rng) for _ in range(pop_size)]
    fitnesses = [problem.fitness(ind) for ind in population]
    best_idx = int(np.argmax(fitnesses))
    best, best_f = dict(population[best_idx]), fitnesses[best_idx]

    def select():
        min_f = min(fitnesses)
        shifted = [f - min_f + 1e-6 for f in fitnesses]
        total = sum(shifted)
        probs = [s / total for s in shifted]
        idx = rng.choices(range(len(population)), weights=probs, k=1)[0]
        return population[idx]

    def crossover(p1, p2):
        if rng.random() > p_cross:
            return dict(p1)
        cut = rng.randint(1, len(pids) - 1)
        return {pid: (p1[pid] if i < cut else p2[pid]) for i, pid in enumerate(pids)}

    def mutate(ind):
        ind2 = dict(ind)
        for pid in pids:
            if rng.random() < p_mut:
                ind2[pid] = int(rng.choice(problem._options_for(pid)))
        return ind2

    rows: list[tuple] = []
    t0 = time.perf_counter()
    for g in range(n_gen):
        new_pop = [dict(best)] if elitisme else []
        while len(new_pop) < pop_size:
            new_pop.append(mutate(crossover(select(), select())))
        population = new_pop
        fitnesses = [problem.fitness(ind) for ind in population]
        gbest_idx = int(np.argmax(fitnesses))
        if fitnesses[gbest_idx] > best_f:
            best, best_f = dict(population[gbest_idx]), fitnesses[gbest_idx]
        rows.append((g, time.perf_counter() - t0, float(np.mean(fitnesses)), best_f))
    return _finalize(
        METHODE_GENETIQUE, best, best_f, rows, t0, float(np.mean(fitnesses)), n_gen
    )


def ant_colony_optimization(
    problem: PlanningProblem,
    n_ants: int = 15,
    n_iter: int = 150,
    alpha: float = 1.0,
    beta: float = 2.0,
    rho: float = 0.3,
    Q: float = 1.0,
    seed: int = 0,
) -> RunResult:
    """Optimisation par colonie de fourmis (ACO) pour l'affectation
    patients -> vacations.

    Chaque fourmi construit une solution complete : pour chaque patient,
    elle choisit une vacation compatible avec une probabilite proportionnelle
    a tau^alpha * eta^beta, ou tau est le niveau de pheromone et eta un
    heuristic qui penalise la charge deja accumulee dans la vacation.
    Les pheromones s'evaporent puis sont renforcees par la meilleure fourmi.
    """
    rng = random.Random(seed)
    tau = np.ones((problem.n_patients, problem.n_vacations))

    best, best_f = None, -np.inf
    rows: list[tuple] = []
    step = _record_every(n_iter)
    t0 = time.perf_counter()

    for k in range(n_iter):
        solutions = []
        for _ in range(n_ants):
            charge = np.zeros(problem.n_vacations)
            sol: Solution = {}
            for pid in range(problem.n_patients):
                options = problem._options_for(pid)
                duree = problem._pat_duree[pid]
                # heuristic : vacation peu chargee et capable d'accueillir le patient
                eta = 1.0 / (1.0 + charge[options] / np.maximum(problem._vac_capacity[options], 1.0))
                poids = (tau[pid, options] ** alpha) * (eta ** beta)
                total = poids.sum()
                if total <= 0:
                    probs = np.full(len(options), 1.0 / len(options))
                else:
                    probs = poids / total
                choix = int(rng.choices(list(options), weights=probs.tolist(), k=1)[0])
                sol[pid] = choix
                charge[choix] += duree
            solutions.append((sol, problem.fitness(sol)))

        solutions.sort(key=lambda s: s[1], reverse=True)
        iter_best, iter_best_f = solutions[0]
        if iter_best_f > best_f:
            best, best_f = dict(iter_best), iter_best_f

        # evaporation
        tau *= (1.0 - rho)
        # depot : la meilleure fourmi de l'iteration renforce ses aretes
        depot = Q / (1.0 + max(-iter_best_f, 0.0))
        for pid, vac_idx in iter_best.items():
            tau[pid, vac_idx] += depot

        if k % step == 0:
            rows.append((k, time.perf_counter() - t0, iter_best_f, best_f))

    return _finalize(METHODE_FOURMIS, best, best_f, rows, t0, iter_best_f, n_iter)


# --------------------------------------------------------------------------
# 4. API haut niveau : optimiser un planning avec toutes les methodes
# --------------------------------------------------------------------------

def optimize_planning(
    patients_df: pd.DataFrame,
    vacations_df: pd.DataFrame,
    lits_capacity: int = 42,
    seed: int = 0,
    sa_kwargs: dict | None = None,
    tabu_kwargs: dict | None = None,
    ga_kwargs: dict | None = None,
    hybrid_kwargs: dict | None = None,
    aco_kwargs: dict | None = None,
) -> dict[str, RunResult]:
    """Point d'entree principal : prend deux DataFrames pandas (patients,
    vacations) et renvoie un dict {nom_methode: RunResult} contenant, pour
    chaque metaheuristique, le meilleur planning trouve et son historique
    de convergence.
    """
    problem = PlanningProblem(patients_df, vacations_df, lits_capacity=lits_capacity)

    return {
        METHODE_RECUIT: simulated_annealing(problem, seed=seed, **(sa_kwargs or {})),
        METHODE_TABOU: tabu_search(problem, seed=seed, **(tabu_kwargs or {})),
        METHODE_GENETIQUE: genetic_algorithm(problem, seed=seed, **(ga_kwargs or {})),
        METHODE_HYBRIDE: tabu_simulated_annealing(problem, seed=seed, **(hybrid_kwargs or {})),
        METHODE_FOURMIS: ant_colony_optimization(problem, seed=seed, **(aco_kwargs or {})),
    }


def solution_to_dataframe(problem: PlanningProblem, solution: Solution) -> pd.DataFrame:
    """Transforme une solution (dict patient->vacation) en DataFrame lisible."""
    pids = list(solution.keys())
    vacs = [solution[pid] for pid in pids]
    out = pd.DataFrame(
        {
            "patient_id": pids,
            "specialite": problem._pat_specialite[pids],
            "duree_operatoire": problem._pat_duree[pids],
            "duree_sejour": problem._pat_sejour[pids],
            "vacation_id": problem.vacations["vacation_id"].to_numpy()[vacs],
            "jour_vacation": problem._vac_day[vacs],
        }
    )
    return out.sort_values(["jour_vacation", "vacation_id", "patient_id"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# 5. Validation : comparaison a l'optimum exact sur une petite instance
# --------------------------------------------------------------------------

def exact_bruteforce(problem: PlanningProblem):
    """Optimum exact par force brute — UNIQUEMENT pour de tres petites
    instances (quelques patients), utilise pour verifier que les
    metaheuristiques convergent bien vers le meilleur planning possible."""
    pids = list(range(problem.n_patients))
    options = [problem._options_for(pid) for pid in pids]
    best, best_f = None, -np.inf
    for combo in itertools.product(*options):
        sol = dict(zip(pids, combo))
        f = problem.fitness(sol)
        if f > best_f:
            best, best_f = sol, f
    return best, best_f


def small_validation_instance(seed: int = 1):
    """Petite instance (7 patients, 4 vacations) assez petite pour un
    calcul exact par force brute, utilisee pour verifier l'optimalite."""
    patients_df, vacations_df = generate_test_data(
        n_patients=7, n_days=1, vacations_par_jour_par_specialite=1, seed=seed
    )
    return patients_df, vacations_df
