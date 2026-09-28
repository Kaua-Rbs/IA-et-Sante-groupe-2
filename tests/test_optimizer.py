"""Tests du coeur : generation, modele, metaheuristiques, API, conversion."""

from __future__ import annotations

import itertools
import unittest

import pandas as pd

from optimiseur import optimizer as op
from tests.helpers import SMALL_KWARGS, TOUTES_METHODES, make_problem


class TestGenerateTestData(unittest.TestCase):
    def test_shapes_and_columns(self):
        patients, vacations = op.generate_test_data(n_patients=12, n_days=3, seed=1)
        self.assertEqual(len(patients), 12)
        self.assertEqual(len(vacations), 3 * len(op.DEFAULT_SPECIALITES))
        self.assertEqual(
            list(patients.columns), ["patient_id", "specialite", "duree_operatoire", "duree_sejour"]
        )
        self.assertEqual(list(vacations.columns), ["vacation_id", "jour", "specialite", "capacite_min"])

    def test_determinism(self):
        a = op.generate_test_data(n_patients=15, n_days=2, seed=7)
        b = op.generate_test_data(n_patients=15, n_days=2, seed=7)
        pd.testing.assert_frame_equal(a[0], b[0])
        pd.testing.assert_frame_equal(a[1], b[1])

    def test_vacation_ids_unique_and_jour_range(self):
        _, vacations = op.generate_test_data(n_patients=5, n_days=4, seed=0)
        self.assertTrue(vacations["vacation_id"].is_unique)
        self.assertEqual(set(vacations["jour"]), {0, 1, 2, 3})


class TestPlanningProblem(unittest.TestCase):
    def _problem(self):
        return make_problem(
            [
                {"patient_id": 0, "specialite": "X", "duree_operatoire": 60, "duree_sejour": 0},
                {"patient_id": 1, "specialite": "X", "duree_operatoire": 90, "duree_sejour": 0},
                {"patient_id": 2, "specialite": "Y", "duree_operatoire": 30, "duree_sejour": 1},
            ],
            [
                {"vacation_id": 10, "jour": 0, "specialite": "X", "capacite_min": 200},
                {"vacation_id": 11, "jour": 1, "specialite": "X", "capacite_min": 200},
                {"vacation_id": 12, "jour": 0, "specialite": "Y", "capacite_min": 200},
            ],
            lits_capacity=5,
        )

    def test_attributes(self):
        prob = self._problem()
        self.assertEqual(prob.n_patients, 3)
        self.assertEqual(prob.n_vacations, 3)
        self.assertEqual(prob.n_days, 2)

    def test_options_non_vides_et_compatibles(self):
        prob = self._problem()
        for pid in range(prob.n_patients):
            options = prob._options_for(pid)
            self.assertGreater(len(options), 0)
            for vac_idx in options:
                self.assertEqual(
                    prob.vacations.loc[vac_idx, "specialite"], prob.patients.loc[pid, "specialite"]
                )

    def test_random_solution_valide(self):
        import random

        prob = self._problem()
        rng = random.Random(0)
        sol = prob.random_solution(rng)
        self.assertEqual(set(sol), set(range(prob.n_patients)))
        for pid, vac_idx in sol.items():
            self.assertIn(vac_idx, prob._options_for(pid).tolist())

    def test_neighbor_valide_et_mouvement_hashable(self):
        import random

        prob = self._problem()
        rng = random.Random(0)
        sol = prob.random_solution(rng)
        types = set()
        for _ in range(100):
            voisin, mouvement = prob.neighbor(sol, rng)
            self.assertEqual(set(voisin), set(sol))
            for pid, vac_idx in voisin.items():
                self.assertIn(vac_idx, prob._options_for(pid).tolist())
            hash(mouvement)  # doit etre hashable (liste taboue)
            types.add(mouvement[0])
        self.assertTrue(types <= {"reassign", "swap"})


class TestFitness(unittest.TestCase):
    def test_depassement_capacite_vacation(self):
        # charge = 150, capacite = 120 -> overflow 30 -> 5 * 30 = 150
        prob = make_problem(
            [
                {"patient_id": 0, "specialite": "X", "duree_operatoire": 60, "duree_sejour": 0},
                {"patient_id": 1, "specialite": "X", "duree_operatoire": 90, "duree_sejour": 0},
            ],
            [{"vacation_id": 0, "jour": 0, "specialite": "X", "capacite_min": 120}],
            lits_capacity=5,
        )
        self.assertAlmostEqual(prob.fitness({0: 0, 1: 0}), -150.0, places=9)

    def test_terme_equilibrage(self):
        # charges [10, 30] -> std = 10 -> 0.05 * 10 = 0.5
        prob = make_problem(
            [
                {"patient_id": 0, "specialite": "X", "duree_operatoire": 10, "duree_sejour": 0},
                {"patient_id": 1, "specialite": "X", "duree_operatoire": 30, "duree_sejour": 0},
            ],
            [
                {"vacation_id": 0, "jour": 0, "specialite": "X", "capacite_min": 1000},
                {"vacation_id": 1, "jour": 1, "specialite": "X", "capacite_min": 1000},
            ],
            lits_capacity=100,
        )
        self.assertAlmostEqual(prob.fitness({0: 0, 1: 1}), -0.5, places=9)

    def test_depassement_lits(self):
        # 3 patients, sejour 2, tous au jour 0, capacite lits 1 -> overflow 2 par jour
        prob = make_problem(
            [
                {"patient_id": i, "specialite": "X", "duree_operatoire": 10, "duree_sejour": 2}
                for i in range(3)
            ],
            [
                {"vacation_id": 0, "jour": 0, "specialite": "X", "capacite_min": 1000},
                {"vacation_id": 1, "jour": 1, "specialite": "X", "capacite_min": 1000},
                {"vacation_id": 2, "jour": 2, "specialite": "X", "capacite_min": 1000},
            ],
            lits_capacity=1,
            w_vacation=0.0,
            w_lits=3.0,
            w_balance=0.0,
        )
        # occupation [3, 3, 3] -> overflow 2+2+2 = 6 -> 3 * 6 = 18
        self.assertAlmostEqual(prob.fitness({0: 0, 1: 0, 2: 0}), -18.0, places=9)

    def test_fitness_parfaite_egale_zero(self):
        prob = make_problem(
            [{"patient_id": 0, "specialite": "X", "duree_operatoire": 30, "duree_sejour": 0}],
            [{"vacation_id": 0, "jour": 0, "specialite": "X", "capacite_min": 100}],
            lits_capacity=10,
        )
        self.assertAlmostEqual(prob.fitness({0: 0}), 0.0, places=9)


class TestOccupationLits(unittest.TestCase):
    def _prob(self, sejour):
        return make_problem(
            [{"patient_id": 0, "specialite": "X", "duree_operatoire": 30, "duree_sejour": sejour}],
            [
                {"vacation_id": i, "jour": i, "specialite": "X", "capacite_min": 1000}
                for i in range(3)
            ],
            lits_capacity=10,
        )

    def test_sejour_court(self):
        self.assertEqual(list(self._prob(1).occupation_lits({0: 0})), [1, 1, 0])

    def test_sejour_borne_a_l_horizon(self):
        self.assertEqual(list(self._prob(10).occupation_lits({0: 0})), [1, 1, 1])


class TestExactBruteforce(unittest.TestCase):
    def test_optimum_independant(self):
        patients, vacations = op.small_validation_instance(seed=1)
        prob = op.PlanningProblem(patients, vacations)
        _, best_f = op.exact_bruteforce(prob)
        pids = range(prob.n_patients)
        options = [prob._options_for(pid) for pid in pids]
        valeurs = [prob.fitness(dict(zip(pids, combo))) for combo in itertools.product(*options)]
        self.assertAlmostEqual(best_f, max(valeurs), places=9)


class TestMetaheuristiques(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patients, cls.vacations = op.small_validation_instance(seed=1)
        cls.prob = op.PlanningProblem(cls.patients, cls.vacations)
        _, cls.f_exact = op.exact_bruteforce(cls.prob)
        cls.resultats = op.optimize_planning(cls.patients, cls.vacations, **SMALL_KWARGS)

    def test_toutes_atteignent_optimum(self):
        for nom, res in self.resultats.items():
            with self.subTest(methode=nom):
                self.assertAlmostEqual(res.meilleure_fitness, self.f_exact, places=6)

    def test_cles_optimize_planning(self):
        self.assertEqual(set(self.resultats), TOUTES_METHODES)

    def test_champs_run_result(self):
        for nom, res in self.resultats.items():
            with self.subTest(methode=nom):
                self.assertEqual(res.nom, nom)
                self.assertGreater(res.duree_s, 0.0)
                self.assertEqual(list(res.historique.columns), op.HISTORY_COLUMNS)
                self.assertGreater(len(res.historique), 0)

    def test_format_duree(self):
        self.assertEqual(op.format_duree(0.005), "5.00 ms")
        self.assertEqual(op.format_duree(0.999), "999.00 ms")
        self.assertEqual(op.format_duree(1.5), "1.50 s")

    def test_historique_coherent(self):
        for nom, res in self.resultats.items():
            with self.subTest(methode=nom):
                hist = res.historique
                self.assertTrue(hist["time_s"].is_monotonic_increasing)
                self.assertAlmostEqual(res.meilleure_fitness, hist["meilleure_fitness"].max(), places=9)
                self.assertGreaterEqual(
                    res.meilleure_fitness, hist["fitness_courante"].iloc[0] - 1e-9
                )

    def test_solution_valide(self):
        for nom, res in self.resultats.items():
            with self.subTest(methode=nom):
                sol = res.meilleure_solution
                self.assertEqual(set(sol), set(range(self.prob.n_patients)))
                for pid, vac_idx in sol.items():
                    self.assertIn(vac_idx, self.prob._options_for(pid).tolist())

    def test_determinisme_meme_seed(self):
        a = op.optimize_planning(self.patients, self.vacations, **SMALL_KWARGS)
        b = op.optimize_planning(self.patients, self.vacations, **SMALL_KWARGS)
        for nom in TOUTES_METHODES:
            with self.subTest(methode=nom):
                self.assertEqual(a[nom].meilleure_fitness, b[nom].meilleure_fitness)
                self.assertEqual(a[nom].meilleure_solution, b[nom].meilleure_solution)

    def test_algorithmes_avec_petits_parametres(self):
        res = op.optimize_planning(
            self.patients,
            self.vacations,
            sa_kwargs={"n_iter": 5},
            tabu_kwargs={"n_iter": 3, "neighborhood_size": 2},
            ga_kwargs={"pop_size": 4, "n_gen": 3},
            hybrid_kwargs={"n_iter": 3, "neighborhood_size": 2},
            aco_kwargs={"n_ants": 2, "n_iter": 2},
        )
        self.assertEqual(set(res), TOUTES_METHODES)


class TestSolutionToDataframe(unittest.TestCase):
    def test_conversion_indice_vers_vacation_id(self):
        prob = make_problem(
            [
                {"patient_id": 0, "specialite": "X", "duree_operatoire": 10, "duree_sejour": 0},
                {"patient_id": 1, "specialite": "X", "duree_operatoire": 20, "duree_sejour": 1},
            ],
            [
                {"vacation_id": 100, "jour": 0, "specialite": "X", "capacite_min": 100},
                {"vacation_id": 200, "jour": 1, "specialite": "X", "capacite_min": 100},
            ],
        )
        df = op.solution_to_dataframe(prob, {0: 1, 1: 0})
        self.assertEqual(
            list(df.columns),
            ["patient_id", "specialite", "duree_operatoire", "duree_sejour", "vacation_id", "jour_vacation"],
        )
        ligne0 = df[df["patient_id"] == 0].iloc[0]
        self.assertEqual(ligne0["vacation_id"], 200)
        self.assertEqual(ligne0["jour_vacation"], 1)
        ligne1 = df[df["patient_id"] == 1].iloc[0]
        self.assertEqual(ligne1["vacation_id"], 100)
        self.assertEqual(ligne1["jour_vacation"], 0)
        # tri par jour de vacation
        self.assertTrue(df["jour_vacation"].is_monotonic_increasing)

    def test_run_result_duree_par_defaut(self):
        res = op.RunResult("x", {}, 0.0, pd.DataFrame())
        self.assertEqual(res.duree_s, 0.0)


if __name__ == "__main__":
    unittest.main()
