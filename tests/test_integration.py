"""Tests d'integration : CLI run_demo et integrite des notebooks."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import nbformat

REPO = Path(__file__).resolve().parents[1]

METHODES_ATTENDUES = ["Recuit simule", "Tabou", "Genetique", "Tabou x Recuit", "Fourmis (ACO)"]


class TestRunDemoCLI(unittest.TestCase):
    def test_run_demo_bout_en_bout(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m", "optimiseur.run_demo",
                    "--n-patients", "12",
                    "--n-days", "3",
                    "--out", tmp,
                ],
                cwd=REPO,
                capture_output=True,
                text=True,
                timeout=300,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertEqual(proc.stdout.count("[OPTIMUM ATTEINT]"), 5)
            for nom in METHODES_ATTENDUES:
                self.assertIn(nom, proc.stdout)

            for fichier in (
                "patients_test.csv",
                "vacations_test.csv",
                "convergence.png",
                "comparaison.png",
                "planning.png",
                "occupation_lits.png",
            ):
                with self.subTest(fichier=fichier):
                    self.assertTrue((Path(tmp) / fichier).exists())


class TestNotebooks(unittest.TestCase):
    def test_guide_optimisation_valide(self):
        nb = nbformat.read(REPO / "notebooks" / "guide_optimisation.ipynb", as_version=4)
        self.assertEqual(nb.nbformat, 4)
        self.assertTrue(any(c.cell_type == "markdown" for c in nb.cells))
        self.assertTrue(any(c.cell_type == "code" for c in nb.cells))
        erreurs = [
            c
            for c in nb.cells
            if c.cell_type == "code"
            and any(o.get("output_type") == "error" for o in c.get("outputs", []))
        ]
        self.assertEqual(erreurs, [], "le notebook guide contient des cellules en erreur")

    def test_rapport_aleas_valide(self):
        nb = nbformat.read(REPO / "notebooks" / "rapport_aleas_et_adaptation.ipynb", as_version=4)
        self.assertEqual(nb.nbformat, 4)
        self.assertTrue(any(c.cell_type == "markdown" for c in nb.cells))
        self.assertTrue(any(c.cell_type == "code" for c in nb.cells))
        erreurs = [
            c
            for c in nb.cells
            if c.cell_type == "code"
            and any(o.get("output_type") == "error" for o in c.get("outputs", []))
        ]
        self.assertEqual(erreurs, [], "le notebook rapport d'aleas contient des cellules en erreur")

    def test_eda_donees_bloc_non_modifie(self):
        nb = nbformat.read(REPO / "EDA_donees_bloc.ipynb", as_version=4)
        for i, cell in enumerate(nb.cells):
            if cell.cell_type == "code":
                with self.subTest(cellule=i):
                    self.assertIsNone(cell.get("execution_count"))
                    self.assertEqual(cell.get("outputs"), [])


if __name__ == "__main__":
    unittest.main()
