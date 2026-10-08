"""Tests du harnais de benchmark (tableaux, agregats, selecteur)."""

from __future__ import annotations

import unittest

import pandas as pd

from optimiseur import benchmark as bm
from optimiseur import optimizer as op


class TestCampagnePetite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.methode_a = op.METHODE_RECUIT
        cls.methode_b = op.METHODE_TABOU
        cls.campagne = bm.campagne_petite_validation(
            n_graines=2, budget_s=0.05, methodes=[cls.methode_a, cls.methode_b]
        )

    def test_reference_exacte(self):
        patients, vacations = op.small_validation_instance(seed=1)
        _, optimum = op.exact_bruteforce(op.PlanningProblem(patients, vacations))
        self.assertTrue(self.campagne.reference_exacte)
        self.assertAlmostEqual(self.campagne.reference, optimum, places=9)

    def test_tableau_long(self):
        tableau = self.campagne.tableau
        self.assertEqual(set(tableau.columns), {"methode", "graine", "fitness", "duree_s"})
        self.assertEqual(len(tableau), 4)
        self.assertEqual(sorted(tableau["graine"].unique()), [0, 1])
        self.assertTrue((tableau["duree_s"] > 0).all())

    def test_resume_colonnes_et_bornes(self):
        resume = self.campagne.resume
        attendues = {
            "methode",
            "n_graines",
            "moyenne",
            "mediane",
            "ecart_type",
            "minimum",
            "maximum",
            "q25",
            "q75",
            "ecart_moyen_ref",
            "taux_reference",
            "rang_moyen",
            "duree_moyenne_s",
            "budget_s",
        }
        self.assertTrue(attendues <= set(resume.columns))
        self.assertTrue((resume["taux_reference"].between(0.0, 1.0)).all())
        self.assertTrue((resume["rang_moyen"].between(1.0, 2.0)).all())
        self.assertTrue((resume["n_graines"] == 2).all())

    def test_taux_reference_dict(self):
        taux = self.campagne.taux_reference
        self.assertEqual(set(taux), {self.methode_a, self.methode_b})


class TestResumerReferenceImposee(unittest.TestCase):
    def test_ecarts_et_taux(self):
        tableau = pd.DataFrame(
            {
                "methode": ["A", "A", "B", "B"],
                "graine": [0, 1, 0, 1],
                "fitness": [-10.0, -8.0, -9.0, -9.0],
                "duree_s": [1.0, 1.0, 2.0, 3.0],
            }
        )
        resume = bm.resumer(tableau, reference=-8.0, budget_s=1.0).set_index("methode")
        self.assertAlmostEqual(resume.loc["A", "ecart_moyen_ref"], 1.0)
        self.assertAlmostEqual(resume.loc["A", "taux_reference"], 0.5)
        self.assertAlmostEqual(resume.loc["B", "ecart_moyen_ref"], 1.0)
        self.assertAlmostEqual(resume.loc["B", "taux_reference"], 0.0)
        self.assertAlmostEqual(resume.loc["A", "rang_moyen"], 1.5)

    def test_reference_par_defaut(self):
        tableau = pd.DataFrame(
            {
                "methode": ["A", "B"],
                "graine": [0, 0],
                "fitness": [-5.0, -7.0],
                "duree_s": [0.1, 0.1],
            }
        )
        resume = bm.resumer(tableau).set_index("methode")
        self.assertAlmostEqual(resume.loc["A", "ecart_moyen_ref"], 0.0)
        self.assertAlmostEqual(resume.loc["B", "ecart_moyen_ref"], 2.0)


class TestCampagneSurInstance(unittest.TestCase):
    def test_campagne_generique(self):
        patients, vacations = op.generate_test_data(n_patients=25, n_days=4, seed=7)
        campagne = bm.campagne_sur_instance(
            patients,
            vacations,
            nom="test",
            n_graines=2,
            budget_s=0.05,
            methodes=[op.METHODE_RECUIT],
        )
        self.assertEqual(campagne.nom, "test")
        self.assertFalse(campagne.reference_exacte)
        self.assertEqual(set(campagne.tableau["methode"]), {op.METHODE_RECUIT})
        self.assertEqual(len(campagne.tableau), 2)
        self.assertAlmostEqual(campagne.reference, float(campagne.tableau["fitness"].max()), places=9)


class TestPlafonds(unittest.TestCase):
    def test_kwargs_plafonnes_couvrent_toutes_les_methodes(self):
        kwargs = bm.kwargs_plafonnes()
        self.assertEqual(set(kwargs), set(op.KWARGS_PAR_METHODE.values()))
        self.assertEqual(set(bm.PLAFONDS_ITERATIONS), set(op.TOUTES_METHODES))


if __name__ == "__main__":
    unittest.main()
