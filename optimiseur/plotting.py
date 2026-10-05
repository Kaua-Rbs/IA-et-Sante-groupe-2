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
    if isinstance(problem.lits_capacity, (int, float, np.integer, np.floating)):
        ax.axhline(problem.lits_capacity, color="red", linestyle="--", label="Capacite (lits)")
    else:
        ax.plot(
            jours,
            problem._lits_capacity_arr,
            color="red",
            linestyle="--",
            drawstyle="steps-mid",
            label="Capacite (lits)",
            linewidth=2,
        )
    ax.set_xlabel("Jour")
    ax.set_ylabel("Nombre de lits occupes")
    ax.set_title("Occupation des lits sur l'horizon du planning")
    ax.legend()
    fig.tight_layout()
    return fig


def plot_adaptation_dynamique(adaptation_res, ax=None):
    """Visualisation comparative avant / apres adaptation dynamique.

    Affiche deux diagrammes de charge :
      - En haut : le planning initial avec mise en exergue des annulations.
      - En bas : le planning adapte avec les urgences inserees, les retards
        bloc et les deplacements de patients realises.
    """
    prob_init = adaptation_res.problem_initial
    sol_init = adaptation_res.solution_initiale
    prob_adap = adaptation_res.problem_adapte
    sol_adap = adaptation_res.solution_adaptee
    deplaces_ids = {d.patient_id for d in adaptation_res.patients_deplaces}
    annules_ids = set(adaptation_res.annulations_appliquees)

    if ax is None:
        fig, axes = plt.subplots(
            2, 1, figsize=(11, max(7.0, 0.4 * len(prob_init.vacations))), sharex=True
        )
    else:
        fig = ax[0].figure
        axes = ax

    cmap = matplotlib.colormaps.get_cmap("tab20")
    vac_labels = [
        f"J{row.jour} - {row.specialite} (V{idx})" for idx, row in prob_init.vacations.iterrows()
    ]

    # --- 1. Planning initial ---
    ax_top = axes[0]
    curseurs_top = np.zeros(len(prob_init.vacations))
    par_vac_top = {v: [] for v in prob_init.vacations.index}
    for pid, vac_idx in sol_init.items():
        par_vac_top[vac_idx].append(pid)

    for vac_idx, pids in par_vac_top.items():
        for pid in pids:
            p_id_reel = prob_init.patients.loc[pid, "patient_id"]
            dur = prob_init.patients.loc[pid, "duree_operatoire"]
            est_annule = p_id_reel in annules_ids
            color = "#D9534F" if est_annule else cmap(pid % 20)
            hatch = "//" if est_annule else ""
            alpha = 0.5 if est_annule else 0.9
            ax_top.barh(
                vac_labels[vac_idx],
                dur,
                left=curseurs_top[vac_idx],
                color=color,
                edgecolor="black" if est_annule else "white",
                hatch=hatch,
                alpha=alpha,
            )
            label_text = f"P{p_id_reel}" + (" (Annule)" if est_annule else "")
            if dur >= 35:
                ax_top.text(
                    curseurs_top[vac_idx] + dur / 2,
                    vac_idx,
                    label_text,
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white" if not est_annule else "black",
                    fontweight="bold",
                )
            curseurs_top[vac_idx] += dur

    for vac_idx, row in prob_init.vacations.iterrows():
        ax_top.plot(
            [row.capacite_min, row.capacite_min],
            [vac_idx - 0.4, vac_idx + 0.4],
            color="black",
            lw=1.5,
        )

    ax_top.set_title(
        f"Planning initial (avant aleas) - Fitness : {adaptation_res.fitness_initiale:.2f}"
        + (" - Raye rouge = patients qui vont annuler" if annules_ids else "")
    )
    ax_top.set_ylabel("Vacations")
    ax_top.grid(axis="x", alpha=0.3)

    # --- 2. Planning adapte ---
    ax_bot = axes[1]
    curseurs_bot = np.zeros(len(prob_adap.vacations))
    # Prendre en compte les retards de bloc
    for vac_idx in range(prob_adap.n_vacations):
        delay = prob_adap.vacation_delays[vac_idx]
        if delay > 0:
            ax_bot.barh(
                vac_labels[vac_idx],
                delay,
                left=0,
                color="#777777",
                edgecolor="black",
                hatch="xx",
                alpha=0.6,
            )
            ax_bot.text(
                delay / 2,
                vac_idx,
                f"Retard {int(delay)}m",
                ha="center",
                va="center",
                fontsize=7,
                color="white",
                fontweight="bold",
            )
            curseurs_bot[vac_idx] = delay

    par_vac_bot = {v: [] for v in prob_adap.vacations.index}
    for pid_adapte, vac_idx in sol_adap.items():
        par_vac_bot[vac_idx].append(pid_adapte)

    for vac_idx, pids in par_vac_bot.items():
        for pid_adapte in pids:
            p_row = prob_adap.patients.loc[pid_adapte]
            p_id = p_row["patient_id"]
            dur = p_row["duree_operatoire"]
            is_urg = bool(p_row.get("is_urgence", False))
            is_dep = p_id in deplaces_ids

            if is_urg:
                col = "#D9534F"
                edge_col = "black"
                lw = 1.5
            elif is_dep:
                col = "#F0AD4E"
                edge_col = "blue"
                lw = 1.2
            else:
                col = cmap((pid_adapte * 3) % 20)
                edge_col = "white"
                lw = 0.5

            ax_bot.barh(
                vac_labels[vac_idx],
                dur,
                left=curseurs_bot[vac_idx],
                color=col,
                edgecolor=edge_col,
                linewidth=lw,
            )
            lbl = f"URG {p_id}" if is_urg else (f"P{p_id}*" if is_dep else f"P{p_id}")
            if dur >= 35:
                ax_bot.text(
                    curseurs_bot[vac_idx] + dur / 2,
                    vac_idx,
                    lbl,
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white" if not is_dep else "black",
                    fontweight="bold",
                )
            curseurs_bot[vac_idx] += dur

    for vac_idx, row in prob_adap.vacations.iterrows():
        ax_bot.plot(
            [row.capacite_min, row.capacite_min],
            [vac_idx - 0.4, vac_idx + 0.4],
            color="black",
            lw=1.5,
        )

    ax_bot.set_title(
        f"Planning adapte dynamiquement au Jour {adaptation_res.jour_courant} - "
        f"Fitness : {adaptation_res.fitness_adaptee:.2f} | Rouge: Urgences | Orange*: Deplacements ({adaptation_res.perturbation_count})"
    )
    ax_bot.set_xlabel("Minutes utilisees (trait noir = capacite standard)")
    ax_bot.set_ylabel("Vacations")
    ax_bot.grid(axis="x", alpha=0.3)

    fig.tight_layout()
    return fig


def plot_comparaison_alternatives(plannings: dict[str, object], ax=None):
    """Barres comparatives des profils de plannings alternatifs :
    qualite globale (fitness), marge de securite bloc et pics de lits.
    """
    noms = list(plannings.keys())
    fitnesses = [plannings[n].fitness for n in noms]
    marges = [plannings[n].marge_moyenne_bloc_min for n in noms]
    pics_lits = [plannings[n].pic_lits for n in noms]
    taux_diff = [plannings[n].taux_patients_differents * 100 for n in noms]

    couleurs = ["#4C72B0", "#55A868", "#C44E52", "#8172B3"][: len(noms)]

    if ax is None:
        fig, axes = plt.subplots(2, 2, figsize=(11, 7))
    else:
        fig = ax[0, 0].figure if hasattr(ax, "ndim") and ax.ndim == 2 else ax[0].figure
        axes = ax.reshape(2, 2) if hasattr(ax, "reshape") else ax

    # 1. Fitness
    b0 = axes[0, 0].bar(noms, fitnesses, color=couleurs)
    axes[0, 0].bar_label(b0, fmt="%.2f", padding=2, fontsize=8)
    axes[0, 0].set_title("Qualite globale (Fitness)")
    axes[0, 0].set_ylabel("Fitness")
    axes[0, 0].tick_params(axis="x", rotation=12)

    # 2. Marge moyenne bloc
    b1 = axes[0, 1].bar(noms, marges, color=couleurs)
    axes[0, 1].bar_label(b1, fmt="%.1f min", padding=2, fontsize=8)
    axes[0, 1].set_title("Marge moyenne disponible / vacation (Buffer anti-aleas)")
    axes[0, 1].set_ylabel("Minutes libres")
    axes[0, 1].tick_params(axis="x", rotation=12)

    # 3. Pic d'occupation des lits
    b2 = axes[1, 0].bar(noms, pics_lits, color=couleurs)
    axes[1, 0].bar_label(b2, fmt="%d lits", padding=2, fontsize=8)
    axes[1, 0].set_title("Pic maximal d'occupation des lits")
    axes[1, 0].set_ylabel("Lits occupes")
    axes[1, 0].tick_params(axis="x", rotation=12)

    # 4. Taux de difference vs nominal (Date B)
    b3 = axes[1, 1].bar(noms, taux_diff, color=couleurs)
    axes[1, 1].bar_label(b3, fmt="%.1f %%", padding=2, fontsize=8)
    axes[1, 1].set_title("Taux de divergence vs Nominal (Options Date B)")
    axes[1, 1].set_ylabel("% patients avec creneau different")
    axes[1, 1].tick_params(axis="x", rotation=12)

    fig.tight_layout()
    return fig


def plot_occupation_lits_aleas(
    problem: PlanningProblem,
    solution: Solution,
    indisponibilites: list | None = None,
    ax=None,
):
    """Occupation journaliere des lits mettant en valeur les periodes
    d'indisponibilite de lits et la reduction de capacite associee.
    """
    occ = problem.occupation_lits(solution)
    jours = np.arange(problem.n_days)

    if ax is None:
        fig, ax = plt.subplots(figsize=(8, 4.5))
    else:
        fig = ax.figure

    ax.bar(jours, occ, color="#4C72B0", label="Lits occupes", alpha=0.85)

    # Capacite de reference et capacite effective
    ax.plot(
        jours,
        problem._lits_capacity_arr,
        color="red",
        linestyle="--",
        drawstyle="steps-mid",
        label="Capacite disponible (apres aleas)",
        linewidth=2,
    )

    if indisponibilites:
        for ind in indisponibilites:
            d = ind.jour_debut
            f = ind.jour_fin
            ax.axvspan(
                d - 0.4,
                f + 0.4,
                color="red",
                alpha=0.15,
                hatch="//",
                label=f"Indisponibilite (-{ind.lits_perdus} lits)",
            )

    ax.set_xlabel("Jour")
    ax.set_ylabel("Nombre de lits")
    ax.set_title("Occupation des lits et impact des indisponibilites")
    ax.legend()
    fig.tight_layout()
    return fig
