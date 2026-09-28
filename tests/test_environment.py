"""Tests d'environnement : dependances Python et tkinter local."""

from __future__ import annotations

import importlib
import os
import unittest


class TestDependencies(unittest.TestCase):
    def test_required_modules_importable(self):
        for module in ("numpy", "pandas", "matplotlib", "seaborn", "openpyxl", "pyarrow", "nbformat"):
            with self.subTest(module=module):
                importlib.import_module(module)

    def test_python_supported(self):
        import sys

        self.assertGreaterEqual(sys.version_info[:2], (3, 12))


def _tkinter_disponible() -> bool:
    try:
        import tkinter  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


class TestTkinterLocal(unittest.TestCase):
    @unittest.skipUnless(_tkinter_disponible(), "tkinter non installe")
    @unittest.skipUnless(os.environ.get("DISPLAY"), "aucun affichage (DISPLAY absent)")
    def test_creation_fenetre(self):
        import tkinter

        root = tkinter.Tk()
        root.withdraw()
        self.assertEqual(tkinter.TkVersion, 8.6)
        root.destroy()

    @unittest.skipUnless(_tkinter_disponible(), "tkinter non installe")
    def test_app_gui_importable(self):
        from optimiseur import app_gui  # noqa: F401


if __name__ == "__main__":
    unittest.main()
