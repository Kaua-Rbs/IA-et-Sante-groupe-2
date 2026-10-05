"""Tests de robustesse sur grandes instances (synthetique et donnees reelles).

Verifient que les tableaux numpy precalcules de ``PlanningProblem`` donnent
exactement les memes valeurs qu'une implementation naive pandas/boucles sur
des instances de plusieurs centaines de patients, et que les 10 methodes y
retournent des plannings valides et deterministes. Les donnees reelles
(Parquet EDA) sont ignorees si le fichier est absent.
"""

from __future__ import annotations

import random
import unittest
from pathlib import Path

import numpy as np

from optimiseur import data_bridge as db
from optimiseur import optimizer as op

PARQUET = Path(db.DEFAULT_PARQUET)
HORIZON_REEL = 20
CAPACITE_REELLE = 480


def _fitness_naive(prob: op.PlanningProblem, solution: op.Solution) -> tuple[float, float, float]:
    """Oracle independant (pandas + boucles) : renvoie (fitness, depassement
    vacations, depassement lits). Volontairement lent, sans numpy vectorise."""
    charge = np.zeros(prob.n_vacations)
    for pid, vac in solution.items():
        charge[vac] += prob.patients.iloc[pid]["duree_operatoire"]
    overflow_vac = sum(
        max(0.0, charge[v] - prob.vacations.iloc[v]["capacite_min"])
        for v in range(prob.n_vacations)
    )

    occupation = np.zeros(prob.n_days)
    for pid, vac in solution.items():
        premier_jour = int(prob.vacations.iloc[vac]["jour"])
        fin = min(premier_jour + int(prob.patients.iloc[pid]["duree_sejour"]) + 1, prob.n_days)
        occupation[premier_jour:fin] += 1
    overflow_lits = float(np.maximum(0, occupation - prob.lits_capacity).sum())

    balance = float(charge.std())
    fitness = -(
        prob.w_vacation * overflow_vac + prob.w_lits * overflow_lits + prob.w_balance * balance
    )
    return fitness, float(overflow_vac), overflow_lits


def _occupation_naive(prob: op.PlanningProblem, solution: op.Solution) -> np.ndarray:
    occupation = np.zeros(prob.n_days)
    for pid, vac in solution.items():
        premier_jour = int(prob.vacations.iloc[vac]["jour"])
        fin = min(premier_jour + int(prob.patients.iloc[pid]["duree_sejour"]) + 1, prob.n_days)
        occupation[premier_jour:fin] += 1
    return occupation


class TestGrandeInstanceSynthetique(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patients, cls.vacations = op.generate_test_data(
            n_patients=400, n_days=15, vacations_par_jour_par_specialite=3, seed=123
        )
        cls.prob = op.PlanningProblem(cls.patients, cls.vacations)
        rng = random.Random(7)
        cls.solutions = [cls.prob.random_solution(rng) for _ in range(3)]

    def test_taille_instance(self):
        self.assertEqual(self.prob.n_patients, 400)
        self.assertEqual(self.prob.n_vacations, 15 * len(op.DEFAULT_SPECIALITES) * 3)

    def test_solutions_aleatoires_valides(self):
        for sol in self.solutions:
            self.assertEqual(set(sol), set(range(self.prob.n_patients)))
            for pid, vac in sol.items():
                self.assertIn(vac, self.prob._options_for(pid).tolist())

    def test_fitness_concordance_oracle(self):
        for sol in self.solutions:
            attendu, _, _ = _fitness_naive(self.prob, sol)
            self.assertAlmostEqual(self.prob.fitness(sol), attendu, places=9)

    def test_violations_concordance_oracle(self):
        for sol in self.solutions:
            _, vac_naive, lits_naif = _fitness_naive(self.prob, sol)
            obs_vac, obs_lits = self.prob.violations(sol)
            self.assertAlmostEqual(obs_vac, vac_naive, places=9)
            self.assertAlmostEqual(obs_lits, lits_naif, places=9)

    def test_occupation_lits_concordance_oracle(self):
        for sol in self.solutions:
            np.testing.assert_allclose(self.prob.occupation_lits(sol), _occupation_naive(self.prob, sol))

    def test_fitness_deterministe(self):
        sol = self.solutions[0]
        self.assertEqual(self.prob.fitness(sol), self.prob.fitness(dict(sol)))

    def test_voisins_valides_et_hashables(self):
        rng = random.Random(3)
        types = set()
        for _ in range(200):
            voisin, mouvement = self.prob.neighbor(self.solutions[1], rng)
            self.assertEqual(set(voisin), set(self.solutions[1]))
            hash(mouvement)
            types.add(mouvement[0])
            for pid, vac in voisin.items():
                self.assertIn(vac, self.prob._options_for(pid).tolist())
        self.assertTrue(types <= {"reassign", "swap"})


class TestMethodesGrandeInstance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patients, cls.vacations = op.generate_test_data(
            n_patients=300, n_days=12, vacations_par_jour_par_specialite=2, seed=321
        )
        cls.prob = op.PlanningProblem(cls.patients, cls.vacations)

    def _verifier_resultat(self, result: op.RunResult, nom: str):
        self.assertEqual(result.nom, nom)
        self.assertEqual(set(result.meilleure_solution), set(range(self.prob.n_patients)))
        for pid, vac in result.meilleure_solution.items():
            self.assertIn(vac, self.prob._options_for(pid).tolist())
        self.assertTrue(np.isfinite(result.meilleure_fitness))
        self.assertLessEqual(result.meilleure_fitness, 0.0)
        self.assertGreaterEqual(result.meilleure_fitness, -np.inf)
        self.assertAlmostEqual(
            result.meilleure_fitness,
            float(result.historique["meilleure_fitness"].max()),
            places=9,
        )
        self.assertEqual(result.meilleure_fitness, float(result.historique["meilleure_fitness"].iloc[-1]))
    def test_les_10_methodes_sur_300_patients(self):
        resultats = op.optimize_planning(
            self.patients,
            self.vacations,
            methodes="toutes",
            seed=5,
            time_budget_s=0.5,
            sa_kwargs={"n_iter": 300},
            tabu_kwargs={"n_iter": 40, "neighborhood_size": 8},
            ga_kwargs={"pop_size": 12, "n_gen": 10},
            hybrid_kwargs={"n_iter": 50, "neighborhood_size": 8},
            aco_kwargs={"n_ants": 5, "n_iter": 5},
            gen_tabu_kwargs={"pop_size": 10, "n_gen": 8},
            gen_recuit_kwargs={"pop_size": 10, "n_gen": 8},
            fourmis_tabu_kwargs={"n_ants": 5, "n_iter": 5},
            sma_kwargs={"n_agents": 4, "n_steps": 6, "intervalle_migration": 2, "stagnation_max": 4},
            sma_hybride_kwargs={
                "n_agents": 4,
                "n_steps": 6,
                "intervalle_migration": 2,
                "stagnation_max": 4,
            },
        )
        self.assertEqual(set(resultats), set(op.TOUTES_METHODES))
        for nom, result in resultats.items():
            with self.subTest(methode=nom):
                self._verifier_resultat(result, nom)

    def test_hook_solution_initiale_ne_degrade_pas(self):
        depart = self.prob.random_solution(random.Random(11))
        fitness_depart = self.prob.fitness(depart)
        resultats = op.optimize_planning(
            self.patients,
            self.vacations,
            methodes=[op.METHODE_RECUIT, op.METHODE_TABOU],
            seed=2,
            time_budget_s=0.3,
            sa_kwargs={"n_iter": 200, "solution_initiale": depart},
            tabu_kwargs={"n_iter": 30, "neighborhood_size": 8, "solution_initiale": depart},
        )
        for nom, result in resultats.items():
            with self.subTest(methode=nom):
                self.assertGreaterEqual(result.meilleure_fitness, fitness_depart - 1e-9)


@unittest.skipUnless(PARQUET.exists(), f"Parquet EDA absent : {PARQUET}")
class TestDonneesReellesGrandeInstance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patients, cls.vacations, cls.contexte = db.prepare_inputs(
            PARQUET, horizon_jours=HORIZON_REEL, capacite_min=CAPACITE_REELLE
        )
        cls.prob = op.PlanningProblem(cls.patients, cls.vacations)
        cls.solution = cls.prob.random_solution(random.Random(0))

    def test_taille_instance(self):
        self.assertEqual(len(self.patients), self.contexte["n_patients"])
        self.assertEqual(self.prob.n_vacations, len(self.vacations))
        self.assertGreaterEqual(len(self.patients), 100)

    def test_fitness_et_violations_concordance_oracle(self):
        attendu, vac_naive, lits_naif = _fitness_naive(self.prob, self.solution)
        self.assertAlmostEqual(self.prob.fitness(self.solution), attendu, places=9)
        obs_vac, obs_lits = self.prob.violations(self.solution)
        self.assertAlmostEqual(obs_vac, vac_naive, places=9)
        self.assertAlmostEqual(obs_lits, lits_naif, places=9)

    def test_solution_to_dataframe_sur_grande_instance(self):
        planning = op.solution_to_dataframe(self.prob, self.solution)
        self.assertEqual(len(planning), self.prob.n_patients)
        self.assertEqual(set(planning["patient_id"]), set(range(self.prob.n_patients)))
        self.assertTrue(set(planning["vacation_id"]).issubset(set(self.vacations["vacation_id"])))
        self.assertTrue(set(planning["jour_vacation"]).issubset(set(self.vacations["jour"])))

    def test_recuit_et_sma_sur_donnees_reelles(self):
        depart = self.prob.random_solution(random.Random(11))
        fitness_depart = self.prob.fitness(depart)
        resultats = op.optimize_planning(
            self.patients,
            self.vacations,
            methodes=[op.METHODE_RECUIT, op.METHODE_SMA],
            seed=1,
            time_budget_s=0.5,
            sa_kwargs={"n_iter": 300, "solution_initiale": depart},
            sma_kwargs={"n_agents": 4, "n_steps": 5, "stagnation_max": 3},
        )
        recuit = resultats[op.METHODE_RECUIT]
        self.assertGreaterEqual(recuit.meilleure_fitness, fitness_depart - 1e-9)
        for nom, result in resultats.items():
            with self.subTest(methode=nom):
                self.assertEqual(set(result.meilleure_solution), set(range(self.prob.n_patients)))
                self.assertTrue(np.isfinite(result.meilleure_fitness))


if __name__ == "__main__":
    unittest.main()
