"""Helpers partages par les tests."""

from __future__ import annotations

import pandas as pd

from optimiseur import optimizer as op

# Parametres reduits pour que les metaheuristiques tournent en quelques
# centiemes de seconde sur la petite instance de validation, tout en
# atteignant l'optimum exact.
SMALL_KWARGS = {
    "sa_kwargs": {"n_iter": 800},
    "tabu_kwargs": {"n_iter": 120, "neighborhood_size": 10},
    "ga_kwargs": {"pop_size": 20, "n_gen": 80},
    "hybrid_kwargs": {"n_iter": 250, "neighborhood_size": 10},
    "aco_kwargs": {"n_ants": 10, "n_iter": 100},
}

TOUTES_METHODES = {
    op.METHODE_RECUIT,
    op.METHODE_TABOU,
    op.METHODE_GENETIQUE,
    op.METHODE_HYBRIDE,
    op.METHODE_FOURMIS,
}


def make_problem(patients, vacations, **kwargs) -> op.PlanningProblem:
    """Construit un PlanningProblem depuis des listes de dicts."""
    return op.PlanningProblem(pd.DataFrame(patients), pd.DataFrame(vacations), **kwargs)


def make_eda_frame(n_rows: int = 30, n_dates: int = 3, seed: int = 0) -> pd.DataFrame:
    """Petit DataFrame au schema du Parquet produit par le notebook EDA."""
    import numpy as np

    rng = np.random.default_rng(seed)
    base = pd.Timestamp("2025-01-06")
    dates = base + pd.to_timedelta(rng.integers(0, n_dates, n_rows), unit="D")
    ccam = rng.choice(["NAGA001", "NCHA002", "LAMA003", "HAMA004"], n_rows)
    return pd.DataFrame(
        {
            "date_inter": dates,
            "room_duration_min": rng.integers(30, 240, n_rows).astype(float),
            "duree_sejour_corrigee": rng.integers(0, 8, n_rows),
            "ccam_1": ccam,
            "ghm_code": [c[:3] for c in ccam],
            "interv_type": rng.choice(["Prothese", "Laparotomie"], n_rows),
        }
    )
