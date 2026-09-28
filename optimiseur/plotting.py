"""
plotting.py
-----------
Fonctions de visualisation pour comparer les metaheuristiques :
vitesse de convergence, qualite finale, temps de calcul, et planning
obtenu.
"""

from __future__ import annotations

import numpy as np
import matplotlib
import matplotlib.pyplot as plt

from .optimizer import (
    METHODE_FOURMIS,
    METHODE_GENETIQUE,
    METHODE_HYBRIDE,
    METHODE_RECUIT,
    METHODE_TABOU,
    PlanningProblem,
    RunResult,
    Solution,
)

COULEURS = {
    METHODE_RECUIT: "#4C72B0",
    METHODE_TABOU: "#DD8452",
    METHODE_GENETIQUE: "#55A868",
    METHODE_HYBRIDE: "#8172B3",
    METHODE_FOURMIS: "#CCB974",
}


def _unite_temps(durees) -> tuple[float, str]:
    """Choisit l'unite d'affichage : millisecondes si tout est < 1 s."""
    duree_max = max(durees) if len(durees) else 0.0
    return (1000.0, "ms") if duree_max < 1.0 else (1.0, "s")


def plot_convergence(resultats: dict[str, RunResult], ax=None):
    """Courbe de convergence : meilleure fitness trouvee en fonction du
    temps ecoule (comparaison directe de vitesse entre methodes)."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 4.5))
    else:
        fig = ax.figure

    temps_max = max((res.historique["time_s"].max() for res in resultats.values()), default=0.0)
    facteur, unite = _unite_temps([temps_max])
    for nom, res in resultats.items():
        h = res.historique
        ax.plot(
            h["time_s"] * facteur,
            h["meilleure_fitness"],
            label=nom,
            color=COULEURS.get(nom),
            linewidth=2,
        )
    ax.set_yscale("symlog", linthresh=1.0)
    ax.set_xlabel(f"Temps ecoule ({unite})")
    ax.set_ylabel("Meilleure qualite trouvee (fitness)")
    ax.set_title("Vitesse de convergence des metaheuristiques")
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    return fig


def plot_comparaison_barres(resultats: dict[str, RunResult], ax=None):
    """Deux barres : qualite finale obtenue et temps de calcul total,
    pour comparer directement les methodes."""
    noms = list(resultats.keys())
    finals = [resultats[n].meilleure_fitness for n in noms]
    durees = [resultats[n].duree_s for n in noms]
    couleurs = [COULEURS.get(n, "grey") for n in noms]
    facteur, unite = _unite_temps(durees)

    if ax is None:
        fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    else:
        fig = ax[0].figure
        axes = ax

    barres_qualite = axes[0].bar(noms, finals, color=couleurs)
    axes[0].bar_label(barres_qualite, fmt="%.2f", padding=2, fontsize=8)
    axes[0].set_title("Qualite finale (0 = planning sans aucune tension)")
    axes[0].set_ylabel("Fitness finale")
    axes[0].tick_params(axis="x", rotation=15)
    axes[0].margins(y=0.15)

    barres_temps = axes[1].bar(noms, [d * facteur for d in durees], color=couleurs)
    axes[1].bar_label(barres_temps, fmt="%.2f", padding=2, fontsize=8)
    axes[1].set_title("Temps de calcul total")
    axes[1].set_ylabel(f"Temps ({unite})")
    axes[1].tick_params(axis="x", rotation=15)
    axes[1].margins(y=0.15)

    fig.tight_layout()
    return fig


def plot_planning(problem: PlanningProblem, solution: Solution, titre: str = "Planning obtenu", ax=None):
    """Diagramme en barres empilees : charge (minutes) de chaque vacation,
    patient par patient, avec la capacite en pointille."""
    if ax is None:
        fig, ax = plt.subplots(figsize=(10, max(4, 0.28 * len(problem.vacations))))
    else:
        fig = ax.figure

    vac_labels = [
        f"J{row.jour} - {row.specialite} (V{idx})" for idx, row in problem.vacations.iterrows()
    ]
    curseurs = np.zeros(len(problem.vacations))

    # regrouper les patients par vacation, dans un ordre stable
    par_vacation = {v: [] for v in problem.vacations.index}
    for pid, vac_idx in solution.items():
        par_vacation[vac_idx].append(pid)

    cmap = matplotlib.colormaps.get_cmap("tab20")
    for vac_idx, pids in par_vacation.items():
        for i, pid in enumerate(pids):
            dur = problem.patients.loc[pid, "duree_operatoire"]
            ax.barh(vac_labels[vac_idx], dur, left=curseurs[vac_idx], color=cmap(pid % 20), edgecolor="white")
            curseurs[vac_idx] += dur

    for vac_idx, row in problem.vacations.iterrows():
        ax.plot([row.capacite_min, row.capacite_min], [vac_idx - 0.4, vac_idx + 0.4], color="black", lw=1)

    ax.set_xlabel("Minutes utilisees (trait noir = capacite de la vacation)")
    ax.set_title(titre)
    fig.tight_layout()
    return fig


def plot_occupation_lits(problem: PlanningProblem, solution: Solution, ax=None):
    """Occupation des lits jour par jour, comparee a la capacite disponible."""
    occ = problem.occupation_lits(solution)
    jours = np.arange(problem.n_days)

    if ax is None:
        fig, ax = plt.subplots(figsize=(7, 4))
    else:
        fig = ax.figure

    ax.bar(jours, occ, color="#4C72B0", label="Lits occupes")
    ax.axhline(problem.lits_capacity, color="red", linestyle="--", label="Capacite (lits)")
    ax.set_xlabel("Jour")
    ax.set_ylabel("Nombre de lits occupes")
    ax.set_title("Occupation des lits sur l'horizon du planning")
    ax.legend()
    fig.tight_layout()
    return fig
