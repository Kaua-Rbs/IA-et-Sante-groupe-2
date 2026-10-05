"""
benchmark.py
------------
Campagnes de comparaison multi-graines des methodes d'optimisation.

Deux echelles sont prevues :

- **petite echelle** : instance de validation ``small_validation_instance``
  (7 patients, 4 vacations) dont l'optimum exact est calcule par force
  brute ; on mesure surtout le taux d'optimum et l'ecart ;
- **grande echelle** : instance synthetique parametrable (defaut 300
  patients, 20 jours, 80 vacations) ; l'optimum est inconnu, on compare les
  methodes entre elles (meilleur connu, rangs, convergence).

Protocole : budget temps identique pour toutes les methodes, plafonds
d'iteration tres eleves pour que le budget soit le seul frein, meme graine
par methode a chaque repetition.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import optimizer as op

# Plafonds d'iteration par methode : le budget temps doit etre le seul frein.
PLAFONDS_ITERATIONS = {
    op.METHODE_RECUIT: {"n_iter": 10**6},
    op.METHODE_TABOU: {"n_iter": 10**6},
    op.METHODE_GENETIQUE: {"n_gen": 10**6},
    op.METHODE_HYBRIDE: {"n_iter": 10**6},
    op.METHODE_FOURMIS: {"n_iter": 10**6},
    op.METHODE_GEN_TABOU: {"n_gen": 10**6},
    op.METHODE_GEN_RECUIT: {"n_gen": 10**6},
    op.METHODE_FOURMIS_TABOU: {"n_iter": 10**6},
    op.METHODE_SMA: {"n_steps": 10**6},
    op.METHODE_SMA_HYBRIDE: {"n_steps": 10**6},
}


def kwargs_plafonnes() -> dict[str, dict]:
    """Kwargs ``optimize_planning`` avec plafonds d'iteration eleves."""
    return {
        op.KWARGS_PAR_METHODE[nom]: dict(valeurs)
        for nom, valeurs in PLAFONDS_ITERATIONS.items()
    }


def executer_campagne(
    patients: pd.DataFrame,
    vacations: pd.DataFrame,
    n_graines: int = 20,
    budget_s: float = 1.0,
    lits_capacity: int = 42,
    methodes: list[str] | None = None,
    verbose: bool = False,
) -> dict[str, list[op.RunResult]]:
    """Execute chaque methode sur ``n_graines`` graines (0..n_graines-1) avec
    le meme budget temps, et renvoie {methode: [RunResult, ...]}."""
    methodes = list(methodes or op.TOUTES_METHODES)
    kwargs = kwargs_plafonnes()
    resultats: dict[str, list[op.RunResult]] = {nom: [] for nom in methodes}
    for graine in range(n_graines):
        pas = op.optimize_planning(
            patients,
            vacations,
            lits_capacity=lits_capacity,
            seed=graine,
            methodes=methodes,
            time_budget_s=budget_s,
            **kwargs,
        )
        for nom, resultat in pas.items():
            resultats[nom].append(resultat)
        if verbose:
            print(f"   graine {graine + 1}/{n_graines} terminee")
    return resultats


def tableau_graines(resultats: dict[str, list[op.RunResult]]) -> pd.DataFrame:
    """Tableau long : une ligne par (methode, graine)."""
    lignes = [
        {
            "methode": nom,
            "graine": graine,
            "fitness": resultat.meilleure_fitness,
            "duree_s": resultat.duree_s,
        }
        for nom, liste in resultats.items()
        for graine, resultat in enumerate(liste)
    ]
    return pd.DataFrame(lignes)


def resumer(
    tableau: pd.DataFrame,
    reference: float | None = None,
    budget_s: float | None = None,
) -> pd.DataFrame:
    """Agrege le tableau long par methode.

    ``reference`` : meilleure fitness connue (optimum exact a petite echelle,
    meilleur observe a grande echelle). Si fournie, ajoute l'ecart moyen et le
    taux d'atteinte (a 1e-6) ; sinon, le meilleur observe sert de reference
    pour le rang et l'ecart.
    """
    if reference is None:
        reference = float(tableau["fitness"].max())

    rangs = tableau.assign(
        rang=tableau.groupby("graine")["fitness"].rank(ascending=False, method="average")
    )
    lignes = []
    for nom, groupe in tableau.groupby("methode", sort=False):
        fitness = groupe["fitness"]
        ecarts = reference - fitness
        rang_moyen = float(rangs[rangs["methode"] == nom]["rang"].mean())
        lignes.append(
            {
                "methode": nom,
                "n_graines": len(groupe),
                "moyenne": float(fitness.mean()),
                "mediane": float(fitness.median()),
                "ecart_type": float(fitness.std(ddof=0)),
                "minimum": float(fitness.min()),
                "maximum": float(fitness.max()),
                "q25": float(fitness.quantile(0.25)),
                "q75": float(fitness.quantile(0.75)),
                "ecart_moyen_ref": float(ecarts.mean()),
                "ecart_min_ref": float(ecarts.min()),
                "taux_reference": float((ecarts.abs() <= 1e-6).mean()),
                "rang_moyen": rang_moyen,
                "duree_moyenne_s": float(groupe["duree_s"].mean()),
                "budget_s": float(budget_s) if budget_s is not None else np.nan,
            }
        )
    return pd.DataFrame(lignes).sort_values("methode").reset_index(drop=True)


@dataclass
class Campagne:
    """Resultats d'une campagne a une echelle donnee."""

    nom: str
    resultats: dict[str, list[op.RunResult]]
    tableau: pd.DataFrame
    resume: pd.DataFrame
    reference: float
    reference_exacte: bool = False

    @property
    def taux_reference(self) -> dict[str, float]:
        return dict(zip(self.resume["methode"], self.resume["taux_reference"]))


def campagne_petite_validation(
    n_graines: int = 20,
    budget_s: float = 0.5,
    seed_instance: int = 1,
    methodes: list[str] | None = None,
    verbose: bool = False,
) -> Campagne:
    """Petite instance dont l'optimum exact est connu par force brute."""
    patients, vacations = op.small_validation_instance(seed=seed_instance)
    problem = op.PlanningProblem(patients, vacations)
    _, optimum = op.exact_bruteforce(problem)
    resultats = executer_campagne(
        patients,
        vacations,
        n_graines=n_graines,
        budget_s=budget_s,
        lits_capacity=problem.lits_capacity,
        methodes=methodes,
        verbose=verbose,
    )
    tableau = tableau_graines(resultats)
    return Campagne(
        nom="petite",
        resultats=resultats,
        tableau=tableau,
        resume=resumer(tableau, reference=optimum, budget_s=budget_s),
        reference=optimum,
        reference_exacte=True,
    )


def campagne_sur_instance(
    patients: pd.DataFrame,
    vacations: pd.DataFrame,
    nom: str = "instance",
    n_graines: int = 20,
    budget_s: float = 3.0,
    lits_capacity: int = 42,
    methodes: list[str] | None = None,
    verbose: bool = False,
) -> Campagne:
    """Campagne generique sur une instance fournie (synthetique ou reelle).

    La reference est le meilleur resultat observe (optimum inconnu).
    """
    resultats = executer_campagne(
        patients,
        vacations,
        n_graines=n_graines,
        budget_s=budget_s,
        lits_capacity=lits_capacity,
        methodes=methodes,
        verbose=verbose,
    )
    tableau = tableau_graines(resultats)
    meilleur_connu = float(tableau["fitness"].max())
    return Campagne(
        nom=nom,
        resultats=resultats,
        tableau=tableau,
        resume=resumer(tableau, reference=meilleur_connu, budget_s=budget_s),
        reference=meilleur_connu,
        reference_exacte=False,
    )


def campagne_grande_echelle(
    n_graines: int = 20,
    budget_s: float = 3.0,
    n_patients: int = 300,
    n_days: int = 20,
    seed_instance: int = 42,
    lits_capacity: int = 42,
    methodes: list[str] | None = None,
    verbose: bool = False,
) -> Campagne:
    """Grande instance synthetique ; reference = meilleure fitness observee."""
    patients, vacations = op.generate_test_data(
        n_patients=n_patients, n_days=n_days, seed=seed_instance
    )
    return campagne_sur_instance(
        patients,
        vacations,
        nom="grande",
        n_graines=n_graines,
        budget_s=budget_s,
        lits_capacity=lits_capacity,
        methodes=methodes,
        verbose=verbose,
    )
