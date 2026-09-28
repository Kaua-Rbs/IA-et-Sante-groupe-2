"""Tests du pont entre le Parquet EDA et le schema de l'optimiseur."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from optimiseur import data_bridge as db
from optimiseur import optimizer as op
from tests.helpers import make_eda_frame

REPO = Path(__file__).resolve().parents[1]
PARQUET_REEL = REPO / "resources" / "donnees_bloc_pretraitees.parquet"


class TestDeriveSpecialite(unittest.TestCase):
    def test_depuis_ccam_avec_regroupement_autre(self):
        df = pd.DataFrame({"ccam_1": ["NAGA", "NCHA", "LAMA", "NAGB"]})
        specialite = db.derive_specialite(df, max_specialites=1)
        self.assertEqual(list(specialite), ["N", "N", "Autre", "N"])

    def test_colonne_explicite_prioritaire(self):
        df = pd.DataFrame({"specialite": ["Cardio", "Digestif"], "ccam_1": ["N", "L"]})
        specialite = db.derive_specialite(df, specialite_col="specialite")
        self.assertEqual(list(specialite), ["Cardio", "Digestif"])

    def test_repli_sans_colonne(self):
        specialite = db.derive_specialite(pd.DataFrame({"foo": [1, 2]}))
        self.assertEqual(list(specialite), ["Non classe", "Non classe"])


class TestBuildPatients(unittest.TestCase):
    def test_schema_et_valeurs(self):
        df = pd.DataFrame(
            {
                "date_inter": pd.to_datetime(["2025-01-06", "2025-01-07"]),
                "room_duration_min": [np.nan, 120.0],
                "duree_sejour_corrigee": [2, np.nan],
                "ccam_1": ["NAGA", "LAMA"],
            }
        )
        patients = db.build_patients(df)
        self.assertEqual(
            list(patients.columns),
            ["patient_id", "specialite", "duree_operatoire", "duree_sejour", "date_inter"],
        )
        self.assertFalse(patients[["specialite", "duree_operatoire", "duree_sejour"]].isna().any().any())
        self.assertGreaterEqual(patients["duree_operatoire"].min(), 15)
        self.assertGreaterEqual(patients["duree_sejour"].min(), 0)

    def test_colonne_manquante_leve_erreur(self):
        with self.assertRaises(ValueError):
            db.build_patients(pd.DataFrame({"ccam_1": ["NAGA"]}))


class TestBuildVacations(unittest.TestCase):
    def test_comptage_et_unicite(self):
        vacations = db.build_vacations(["A", "B"], n_days=3, vacations_par_jour_par_specialite=2)
        self.assertEqual(len(vacations), 3 * 2 * 2)
        self.assertTrue(vacations["vacation_id"].is_unique)
        self.assertEqual(set(vacations["jour"]), {0, 1, 2})


class TestSelectHorizon(unittest.TestCase):
    def test_garde_les_dernieres_dates(self):
        df = make_eda_frame(n_rows=40, n_dates=6, seed=3)
        patients = db.build_patients(df)
        fenetre, contexte = db.select_horizon(patients, horizon_jours=3)
        self.assertEqual(contexte["n_days"], 3)
        self.assertEqual(set(fenetre["jour_origine"]), {0, 1, 2})
        self.assertEqual(list(fenetre["patient_id"]), list(range(len(fenetre))))

    def test_ignore_les_patients_sans_date(self):
        patients = pd.DataFrame(
            {
                "patient_id": [0, 1],
                "specialite": ["X", "X"],
                "duree_operatoire": [30, 30],
                "duree_sejour": [0, 0],
                "date_inter": [pd.NaT, pd.Timestamp("2025-01-06")],
            }
        )
        fenetre, _ = db.select_horizon(patients, horizon_jours=1)
        self.assertEqual(len(fenetre), 1)


class TestPrepareInputs(unittest.TestCase):
    def test_pipeline_sur_parquet_synthetique(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "eda.parquet"
            make_eda_frame(n_rows=40, n_dates=3, seed=5).to_parquet(path, index=False)
            patients, vacations, contexte = db.prepare_inputs(path, horizon_jours=3)
            self.assertGreater(len(patients), 0)
            self.assertGreater(len(vacations), 0)
            self.assertEqual(contexte["n_days"], 3)
            self.assertEqual(
                list(patients.columns),
                ["patient_id", "specialite", "duree_operatoire", "duree_sejour", "jour_origine"],
            )
            # les vacations couvrent jour x specialite
            self.assertEqual(
                len(vacations), contexte["n_days"] * len(contexte["specialites"])
            )

    def test_fichier_absent_leve_erreur(self):
        with self.assertRaises(FileNotFoundError):
            db.prepare_inputs("/tmp/inexistant_eda.parquet")


@unittest.skipUnless(PARQUET_REEL.exists(), "Parquet EDA reel absent")
class TestDonneesReelles(unittest.TestCase):
    def test_pipeline_reel_et_optimisation(self):
        patients, vacations, contexte = db.prepare_inputs(PARQUET_REEL)
        self.assertGreater(len(patients), 0)
        self.assertGreater(len(vacations), 0)
        self.assertFalse(patients[["specialite", "duree_operatoire", "duree_sejour"]].isna().any().any())

        res = op.optimize_planning(
            patients,
            vacations,
            sa_kwargs={"n_iter": 200},
            tabu_kwargs={"n_iter": 20, "neighborhood_size": 5},
            ga_kwargs={"pop_size": 10, "n_gen": 10},
            hybrid_kwargs={"n_iter": 20, "neighborhood_size": 5},
            aco_kwargs={"n_ants": 4, "n_iter": 10},
        )
        self.assertEqual(len(res), 5)
        for nom, r in res.items():
            with self.subTest(methode=nom):
                self.assertTrue(np.isfinite(r.meilleure_fitness))


if __name__ == "__main__":
    unittest.main()
