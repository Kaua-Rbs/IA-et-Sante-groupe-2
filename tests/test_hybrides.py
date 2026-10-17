"""Tests des hybrides ajoutes : genetique x tabou, genetique x recuit,
fourmis x tabou, plus les hooks de reprise et le selecteur de methodes."""

from __future__ import annotations

import unittest

import numpy as np

from optimiseur import optimizer as op
from tests.helpers import make_problem

HYBRIDES = [op.METHODE_GEN_TABOU, op.METHODE_GEN_RECUIT, op.METHODE_FOURMIS_TABOU]

KWARGS_REDUITS = {
    op.METHODE_GEN_TABOU: {"n_gen": 30},
    op.METHODE_GEN_RECUIT: {"n_gen": 30},
    op.METHODE_FOURMIS_TABOU: {"n_iter": 30, "n_ants": 8},
}


class TestHybridesPetiteInstance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patients, cls.vacations = op.small_validation_instance(seed=1)
        cls.prob = op.PlanningProblem(cls.patients, cls.vacations)
        _, cls.f_exact = op.exact_bruteforce(cls.prob)
        cls.resultats = {}
        for nom in HYBRIDES:
            cls.resultats[nom] = op.optimize_planning(
                cls.patients,
                cls.vacations,
                methodes=[nom],
                time_budget_s=2.0,
                **{op.KWARGS_PAR_METHODE[nom]: KWARGS_REDUITS[nom]},
            )[nom]

    def test_optimum_atteint(self):
        for nom, resultat in self.resultats.items():
            with self.subTest(methode=nom):
                self.assertAlmostEqual(resultat.meilleure_fitness, self.f_exact, places=6)

    def test_solution_valide(self):
        for nom, resultat in self.resultats.items():
            with self.subTest(methode=nom):
                self.assertEqual(set(resultat.meilleure_solution), set(range(self.prob.n_patients)))
                for pid, vac_idx in resultat.meilleure_solution.items():
                    self.assertIn(vac_idx, self.prob._options_for(pid).tolist())

    def test_historique_coherent(self):
        for nom, resultat in self.resultats.items():
            with self.subTest(methode=nom):
                hist = resultat.historique
                self.assertEqual(list(hist.columns), op.HISTORY_COLUMNS)
                self.assertTrue(hist["time_s"].is_monotonic_increasing)
                self.assertAlmostEqual(
                    resultat.meilleure_fitness, hist["meilleure_fitness"].max(), places=9
                )

    def test_determinisme_meme_seed(self):
        for nom in HYBRIDES:
            with self.subTest(methode=nom):
                a = op.optimize_planning(
                    self.patients, self.vacations, methodes=[nom], **{op.KWARGS_PAR_METHODE[nom]: KWARGS_REDUITS[nom]}
                )[nom]
                b = op.optimize_planning(
                    self.patients, self.vacations, methodes=[nom], **{op.KWARGS_PAR_METHODE[nom]: KWARGS_REDUITS[nom]}
                )[nom]
                self.assertEqual(a.meilleure_fitness, b.meilleure_fitness)
                self.assertEqual(a.meilleure_solution, b.meilleure_solution)


class TestHooksReprise(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patients, cls.vacations = op.small_validation_instance(seed=1)
        cls.prob = op.PlanningProblem(cls.patients, cls.vacations)
        cls.best, cls.best_f = op.exact_bruteforce(cls.prob)

    def test_solution_initiale_conservee(self):
        depart_f = self.prob.fitness(self.best)
        for fonc in (op.simulated_annealing, op.tabu_search, op.tabu_simulated_annealing):
            with self.subTest(fonction=fonc.__name__):
                resultat = fonc(self.prob, n_iter=5, seed=0, solution_initiale=self.best)
                self.assertGreaterEqual(resultat.meilleure_fitness, depart_f - 1e-9)
                self.assertEqual(resultat.meilleure_solution, self.best)

    def test_population_initiale(self):
        depart_f = self.prob.fitness(self.best)
        resultat = op.genetic_algorithm(self.prob, pop_size=4, n_gen=3, seed=0, population_initiale=[self.best])
        self.assertGreaterEqual(resultat.meilleure_fitness, depart_f - 1e-9)

    def test_pheromones_initiaux(self):
        depart_f = self.prob.fitness(self.best)
        pheromones = np.ones((self.prob.n_patients, self.prob.n_vacations))
        resultat = op.ant_colony_optimization(
            self.prob,
            n_ants=2,
            n_iter=2,
            seed=0,
            pheromones_initiaux=pheromones,
            meilleure_solution_initiale=self.best,
        )
        self.assertGreaterEqual(resultat.meilleure_fitness, depart_f - 1e-9)

    def test_etat_rempli(self):
        etat_ga: dict = {}
        op.genetic_algorithm(self.prob, pop_size=4, n_gen=2, seed=0, etat=etat_ga)
        self.assertIn("population", etat_ga)
        self.assertIn("meilleure_solution", etat_ga)
        self.assertEqual(len(etat_ga["population"]), 4)

        etat_aco: dict = {}
        op.ant_colony_optimization(self.prob, n_ants=2, n_iter=2, seed=0, etat=etat_aco)
        self.assertEqual(etat_aco["pheromones"].shape, (self.prob.n_patients, self.prob.n_vacations))
        self.assertIn("meilleure_fitness", etat_aco)


class TestBudgetTemps(unittest.TestCase):
    def test_budget_respecte(self):
        patients, vacations = op.generate_test_data(n_patients=120, n_days=10, seed=3)
        budget = 0.2
        resultats = op.optimize_planning(
            patients,
            vacations,
            methodes=HYBRIDES,
            time_budget_s=budget,
            gen_tabu_kwargs={"n_gen": 10**6},
            gen_recuit_kwargs={"n_gen": 10**6},
            fourmis_tabu_kwargs={"n_iter": 10**6},
        )
        for nom, resultat in resultats.items():
            with self.subTest(methode=nom):
                self.assertLessEqual(resultat.duree_s, budget + 0.5)


class TestSelecteurMethodes(unittest.TestCase):
    def test_toutes_les_methodes(self):
        patients, vacations = op.small_validation_instance(seed=1)
        resultats = op.optimize_planning(
            patients, vacations, methodes="toutes", time_budget_s=0.3
        )
        self.assertEqual(list(resultats), list(op.TOUTES_METHODES))
        for resultat in resultats.values():
            self.assertTrue(np.isfinite(resultat.meilleure_fitness))

    def test_defaut_historique(self):
        patients, vacations = op.small_validation_instance(seed=1)
        resultats = op.optimize_planning(patients, vacations)
        self.assertEqual(list(resultats), list(op.METHODES_HISTORIQUES))

    def test_methode_inconnue(self):
        patients, vacations = op.small_validation_instance(seed=1)
        with self.assertRaises(ValueError):
            op.optimize_planning(patients, vacations, methodes=["n'existe pas"])

    def test_chaine_inconnue(self):
        patients, vacations = op.small_validation_instance(seed=1)
        with self.assertRaises(ValueError):
            op.optimize_planning(patients, vacations, methodes="toutes-les-methodes")


class TestViolations(unittest.TestCase):
    def test_depassement_detecte(self):
        prob = make_problem(
            [
                {"patient_id": 0, "specialite": "X", "duree_operatoire": 200, "duree_sejour": 0},
            ],
            [{"vacation_id": 0, "jour": 0, "specialite": "X", "capacite_min": 120}],
            lits_capacity=1,
        )
        depassement_vac, depassement_lits = prob.violations({0: 0})
        self.assertAlmostEqual(depassement_vac, 80.0, places=9)
        self.assertAlmostEqual(depassement_lits, 0.0, places=9)

    def test_planning_faisable(self):
        prob = make_problem(
            [{"patient_id": 0, "specialite": "X", "duree_operatoire": 60, "duree_sejour": 0}],
            [{"vacation_id": 0, "jour": 0, "specialite": "X", "capacite_min": 120}],
            lits_capacity=5,
        )
        self.assertEqual(prob.violations({0: 0}), (0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
