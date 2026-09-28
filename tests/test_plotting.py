"""Tests des graphiques (backend Agg, sans affichage)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
from matplotlib.figure import Figure

from optimiseur import optimizer as op
from optimiseur import plotting as pl
from optimiseur.optimizer import RunResult
from tests.helpers import SMALL_KWARGS, TOUTES_METHODES


class TestPlotting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patients, cls.vacations = op.small_validation_instance(seed=1)
        cls.prob = op.PlanningProblem(cls.patients, cls.vacations)
        cls.resultats = op.optimize_planning(cls.patients, cls.vacations, **SMALL_KWARGS)
        cls.solution = cls.resultats[op.METHODE_RECUIT].meilleure_solution

    def test_couleurs_couvrent_toutes_les_methodes(self):
        self.assertEqual(set(pl.COULEURS), TOUTES_METHODES)

    def test_fonctions_renvoient_une_figure(self):
        figures = {
            "convergence": pl.plot_convergence(self.resultats),
            "comparaison": pl.plot_comparaison_barres(self.resultats),
            "planning": pl.plot_planning(self.prob, self.solution),
            "lits": pl.plot_occupation_lits(self.prob, self.solution),
        }
        for nom, fig in figures.items():
            with self.subTest(figure=nom):
                self.assertIsInstance(fig, Figure)

    def test_savefig(self):
        with tempfile.TemporaryDirectory() as tmp:
            for nom, fig in {
                "convergence": pl.plot_convergence(self.resultats),
                "comparaison": pl.plot_comparaison_barres(self.resultats),
                "planning": pl.plot_planning(self.prob, self.solution),
                "lits": pl.plot_occupation_lits(self.prob, self.solution),
            }.items():
                path = Path(tmp) / f"{nom}.png"
                fig.savefig(path)
                self.assertTrue(path.exists() and path.stat().st_size > 0)


class TestUnitesDeTemps(unittest.TestCase):
    @staticmethod
    def _resultats(duree_s: float) -> dict:
        def resultat(nom: str, duree: float, fitness: float) -> RunResult:
            historique = pd.DataFrame(
                {"time_s": [0.0, duree], "meilleure_fitness": [fitness - 1.0, fitness]}
            )
            return RunResult(nom, {}, fitness, historique, duree)

        return {
            op.METHODE_RECUIT: resultat(op.METHODE_RECUIT, duree_s, -1.0),
            op.METHODE_TABOU: resultat(op.METHODE_TABOU, duree_s * 2, -1.1),
        }

    def test_affichage_en_millisecondes(self):
        resultats = self._resultats(0.001)
        fig = pl.plot_comparaison_barres(resultats)
        self.assertEqual(fig.axes[1].get_ylabel(), "Temps (ms)")
        self.assertTrue(any(t.get_text() for t in fig.axes[1].texts))
        self.assertEqual(pl.plot_convergence(resultats).axes[0].get_xlabel(), "Temps ecoule (ms)")

    def test_affichage_en_secondes(self):
        resultats = self._resultats(2.0)
        fig = pl.plot_comparaison_barres(resultats)
        self.assertEqual(fig.axes[1].get_ylabel(), "Temps (s)")
        self.assertEqual(pl.plot_convergence(resultats).axes[0].get_xlabel(), "Temps ecoule (s)")


if __name__ == "__main__":
    unittest.main()
