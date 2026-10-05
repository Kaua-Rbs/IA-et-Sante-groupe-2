"""
aleas.py
--------
Systeme de gestion des aleas et d'aide a la decision pour le bloc operatoire.

Types d'aleas geres :
  1. Urgences : nouveaux patients non programmes arrivant avec un niveau de
     priorite et un delai maximal d'intervention.
  2. Annulations : patients programmes dont l'intervention est annulee,
     liberant du temps de salle et des lits d'hospitalisation.
  3. Indisponibilite lits : fermetures imprevues ou baisse temporaire de
     la capacite en lits sur un ou plusieurs jours.
  4. Retard bloc : depassement d'intervention ou alea technique reduisant la
     capacite utile d'une vacation.

Approches proposees :
  1. Generation de plannings alternatifs :
     - Profil Nominal (maximisation de l'efficience standard)
     - Profil Robuste Bufferise (marges de securite temps bloc et lits pour absorber
       retards et urgences)
     - Profil Securite Lits (priorite anti-saturation et lissage lits)
     - Profil Alternatif Diversifie avec proposition Date A / Date B pour chaque patient
  2. Adaptation dynamique (reactive replanning) :
     - Gel des interventions passees (jours < jour_courant)
     - Retrait des annulations et injection des urgences
     - Mise a jour dynamique des contraintes (retards bloc, baisse de lits)
     - Re-optimisation sous contrainte de stabilite (principe de moindre perturbation,
       minimisation du nombre de deplacements de patients futurs)
"""

from __future__ import annotations

import copy
import random
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

import numpy as np
import pandas as pd

from .optimizer import (
    HISTORY_COLUMNS,
    METHODE_RECUIT,
    METHODE_TABOU,
    PlanningProblem,
    RunResult,
    Solution,
    simulated_annealing,
    tabu_search,
)


# --------------------------------------------------------------------------
# 1. Types d'aleas et structures de donnees
# --------------------------------------------------------------------------

class TypeAlea(str, Enum):
    URGENCE = "urgence"
    ANNULATION = "annulation"
    INDISPONIBILITE_LITS = "indisponibilite_lits"
    RETARD_BLOC = "retard_bloc"


@dataclass
class Urgence:
    """Nouveau patient urgent se presentant de facon imprevue."""
    patient_id: int | str
    specialite: str
    duree_operatoire: float
    duree_sejour: int
    jour_apparition: int
    delai_max_jours: int = 0
    priorite: int = 1  # 1 = vital/absolu, 2 = urgent sous 24-48h
    motif: str = "Urgence chirurgicale non programmee"


@dataclass
class Annulation:
    """Patient programme dont l'intervention est annulee."""
    patient_id: int | str
    jour_notification: int
    motif: str = "Contre-indication medicale / indisponibilite patient"


@dataclass
class IndisponibiliteLits:
    """Perte imprevue de lits d'hospitalisation sur une periode donnee."""
    jour_debut: int
    jour_fin: int
    lits_perdus: int
    motif: str = "Fermeture imprevue de lits / tension RH / isolement"


@dataclass
class RetardBloc:
    """Depassement horaire ou incident reduisant la capacite d'une vacation."""
    vacation_id: int
    retard_min: float
    motif: str = "Depassement d'intervention / panne ou nettoyage prolonge"


@dataclass
class ScenarioAleas:
    """Conteneur d'un ensemble d'aleas a appliquer au planning."""
    nom: str = "Scenario d'aleas"
    urgences: list[Urgence] = field(default_factory=list)
    annulations: list[Annulation] = field(default_factory=list)
    indisponibilites_lits: list[IndisponibiliteLits] = field(default_factory=list)
    retards_bloc: list[RetardBloc] = field(default_factory=list)

    def ajouter_urgence(
        self,
        patient_id: int | str,
        specialite: str,
        duree_operatoire: float,
        duree_sejour: int,
        jour_apparition: int,
        delai_max_jours: int = 0,
        priorite: int = 1,
        motif: str = "Urgence chirurgicale non programmee",
    ) -> Urgence:
        u = Urgence(
            patient_id=patient_id,
            specialite=specialite,
            duree_operatoire=float(duree_operatoire),
            duree_sejour=int(duree_sejour),
            jour_apparition=int(jour_apparition),
            delai_max_jours=int(delai_max_jours),
            priorite=priorite,
            motif=motif,
        )
        self.urgences.append(u)
        return u

    def ajouter_annulation(
        self,
        patient_id: int | str,
        jour_notification: int,
        motif: str = "Contre-indication medicale / indisponibilite patient",
    ) -> Annulation:
        a = Annulation(patient_id=patient_id, jour_notification=int(jour_notification), motif=motif)
        self.annulations.append(a)
        return a

    def ajouter_indisponibilite_lits(
        self,
        jour_debut: int,
        jour_fin: int,
        lits_perdus: int,
        motif: str = "Fermeture imprevue de lits / tension RH / isolement",
    ) -> IndisponibiliteLits:
        i = IndisponibiliteLits(
            jour_debut=int(jour_debut),
            jour_fin=int(jour_fin),
            lits_perdus=int(lits_perdus),
            motif=motif,
        )
        self.indisponibilites_lits.append(i)
        return i

    def ajouter_retard_bloc(
        self,
        vacation_id: int,
        retard_min: float,
        motif: str = "Depassement d'intervention / panne ou nettoyage prolonge",
    ) -> RetardBloc:
        r = RetardBloc(vacation_id=int(vacation_id), retard_min=float(retard_min), motif=motif)
        self.retards_bloc.append(r)
        return r

    def total_aleas(self) -> int:
        return (
            len(self.urgences)
            + len(self.annulations)
            + len(self.indisponibilites_lits)
            + len(self.retards_bloc)
        )

    def est_vide(self) -> bool:
        return self.total_aleas() == 0

    def resume(self) -> str:
        lignes = [
            f"Scenario : {self.nom} ({self.total_aleas()} aleas au total)",
            f"  - Urgences : {len(self.urgences)}",
            f"  - Annulations : {len(self.annulations)}",
            f"  - Indisponibilites lits : {len(self.indisponibilites_lits)}",
            f"  - Retards bloc : {len(self.retards_bloc)}",
        ]
        return "\n".join(lignes)


# --------------------------------------------------------------------------
# 2. Simulateur d'aleas realistes
# --------------------------------------------------------------------------

def generer_scenario_aleas(
    problem: PlanningProblem,
    solution: Solution | None = None,
    jour_courant: int = 1,
    n_urgences: int = 2,
    n_annulations: int = 1,
    proba_retard_bloc: float = 0.35,
    max_retard_min: float = 60.0,
    proba_baisse_lits: float = 0.5,
    lits_perdus: int = 5,
    seed: int = 42,
) -> ScenarioAleas:
    """Simule de maniere reproductible un ensemble realiste d'aleas
    survenant a partir du jour courant.
    """
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    scenario = ScenarioAleas(nom=f"Simulation aleas au Jour {jour_courant}")

    specialites_dispos = list(problem.compatible.keys())
    existing_pids = set(problem.patients["patient_id"])
    max_id = max(existing_pids) if existing_pids else 0

    # 1. Generation des urgences
    for i in range(n_urgences):
        u_id = f"URG_{i+1}"
        spec = rng.choice(specialites_dispos)
        # duree tiree dans la distribution des patients existants de cette specialite si dispo
        patients_spec = problem.patients[problem.patients["specialite"] == spec]
        if len(patients_spec) > 0:
            duree_op = float(np_rng.choice(patients_spec["duree_operatoire"]))
            duree_sej = int(np_rng.choice(patients_spec["duree_sejour"]))
        else:
            duree_op = float(rng.randint(45, 120))
            duree_sej = int(rng.randint(0, 3))

        delai_max = 0 if rng.random() < 0.6 else min(1, max(0, problem.n_days - 1 - jour_courant))
        scenario.ajouter_urgence(
            patient_id=u_id,
            specialite=spec,
            duree_operatoire=duree_op,
            duree_sejour=duree_sej,
            jour_apparition=jour_courant,
            delai_max_jours=delai_max,
            priorite=1 if delai_max == 0 else 2,
            motif="Arrivee patient urgent SMUR/Urgences",
        )

    # 2. Generation des annulations (parmi les patients programmes a partir du jour_courant)
    candidats_annulation = []
    if solution is not None:
        for pid_idx, vac_idx in solution.items():
            jour_vac = int(problem._vac_day[vac_idx])
            if jour_vac >= jour_courant:
                pid_reel = problem.patients.loc[pid_idx, "patient_id"]
                candidats_annulation.append((pid_reel, jour_vac))
    else:
        for idx, row in problem.patients.iterrows():
            candidats_annulation.append((row["patient_id"], jour_courant))

    if candidats_annulation and n_annulations > 0:
        n_a_choisir = min(n_annulations, len(candidats_annulation))
        choisis = rng.sample(candidats_annulation, n_a_choisir)
        for pid_reel, j_vac in choisis:
            scenario.ajouter_annulation(
                patient_id=pid_reel,
                jour_notification=jour_courant,
                motif="Contre-indication anesthesique de derniere minute",
            )

    # 3. Indisponibilite de lits
    if rng.random() < proba_baisse_lits and jour_courant < problem.n_days:
        j_fin = min(problem.n_days - 1, jour_courant + rng.randint(0, 2))
        scenario.ajouter_indisponibilite_lits(
            jour_debut=jour_courant,
            jour_fin=j_fin,
            lits_perdus=lits_perdus,
            motif="Tension d'effectifs infirmiers / lits fermes",
        )

    # 4. Retards de bloc sur les vacations du jour courant
    vacations_jour = problem.vacations[problem.vacations["jour"] == jour_courant]
    for _, row in vacations_jour.iterrows():
        if rng.random() < proba_retard_bloc:
            retard = float(rng.randint(20, int(max_retard_min)))
            scenario.ajouter_retard_bloc(
                vacation_id=int(row["vacation_id"]),
                retard_min=retard,
                motif="Prolongation premiere intervention / retard brancardage",
            )

    return scenario


# --------------------------------------------------------------------------
# 3. Generation de plannings alternatifs
# --------------------------------------------------------------------------

@dataclass
class PlanningAlternatifResult:
    """Resultat et caracteristiques d'un planning alternatif."""
    nom: str
    description: str
    solution: Solution
    fitness: float
    overflow_vacation: float
    overflow_lits: float
    marge_moyenne_bloc_min: float
    pic_lits: int
    taux_patients_differents: float  # distance relative / nominal (0 = identique)
    planning_df: pd.DataFrame


def generer_plannings_alternatifs(
    problem: PlanningProblem,
    solution_nominale: Solution | None = None,
    marge_buffer_bloc: float = 0.15,
    marge_buffer_lits: float = 0.15,
    seed: int = 0,
    methode: str = METHODE_RECUIT,
    metaheuristic_kwargs: dict | None = None,
) -> dict[str, PlanningAlternatifResult]:
    """Genere une palette de plannings alternatifs aux caracteristiques
    operationnelles complementaires :
      1. 'Nominal' : optimise a pleine capacite pour le bloc et les lits.
      2. 'Robuste_Buffer' : optimise avec des reserves de temps (buffer 15%)
         et de lits pour absorber proactivement les retards et urgences.
      3. 'Securite_Lits' : priorite absolue au lissage et a la sous-saturation
         des lits d'hospitalisation (anti-tension d'admission).
      4. 'Alternatif_Diversifie' : seconde solution viable a forte divergence,
         permettant de proposer l'option Date A / Date B au praticien.
    """
    kwargs = metaheuristic_kwargs or {}
    resultats: dict[str, PlanningAlternatifResult] = {}

    def _resoudre(prob: PlanningProblem, s_seed: int) -> Solution:
        if methode == METHODE_TABOU:
            res = tabu_search(prob, seed=s_seed, **kwargs)
        else:
            res = simulated_annealing(prob, seed=s_seed, **kwargs)
        return res.meilleure_solution

    # 1. Solution Nominale
    if solution_nominale is None:
        sol_nominale = _resoudre(problem, seed)
    else:
        sol_nominale = dict(solution_nominale)

    # 2. Solution Robuste avec marges tampons (Buffer anti-aleas)
    vac_buffer = problem.vacations.copy()
    vac_buffer["capacite_min"] = vac_buffer["capacite_min"] * (1.0 - marge_buffer_bloc)
    lits_buffer = np.maximum(1, np.floor(problem._lits_capacity_arr * (1.0 - marge_buffer_lits)))
    prob_buffer = PlanningProblem(
        problem.patients.copy(),
        vac_buffer,
        lits_capacity=lits_buffer,
        w_vacation=problem.w_vacation,
        w_lits=problem.w_lits,
        w_balance=problem.w_balance,
    )
    sol_robuste = _resoudre(prob_buffer, seed + 101)

    # 3. Solution Securite Lits (fort lissage des lits et penalite lits triplee)
    prob_lits = PlanningProblem(
        problem.patients.copy(),
        problem.vacations.copy(),
        lits_capacity=np.maximum(1, np.floor(problem._lits_capacity_arr * 0.85)),
        w_vacation=problem.w_vacation,
        w_lits=problem.w_lits * 3.0,
        w_balance=problem.w_balance * 4.0,
    )
    sol_securite_lits = _resoudre(prob_lits, seed + 202)

    # 4. Solution Alternative Diversifiee (Date B)
    # Recherche d'une solution de qualite avec seed differente et contrainte de divergence
    sol_diversifiee = _generer_solution_diversifiee(
        problem, sol_nominale, seed=seed + 303, **kwargs
    )

    plannings_bruts = [
        (
            "Nominal",
            "Planning nominal standard optimise pour une efficience maximale",
            sol_nominale,
        ),
        (
            "Robuste_Buffer",
            f"Planning robuste avec marge de securite ({int(marge_buffer_bloc*100)}% bloc, {int(marge_buffer_lits*100)}% lits)",
            sol_robuste,
        ),
        (
            "Securite_Lits",
            "Planning securisant les capacites d'hospitalisation et lissant les pics de lits",
            sol_securite_lits,
        ),
        (
            "Alternatif_Date_B",
            "Planning alternatif diversifie pour proposer une Date B aux chirurgiens",
            sol_diversifiee,
        ),
    ]

    for nom, desc, sol in plannings_bruts:
        pids = np.fromiter(sol.keys(), dtype=int, count=len(sol))
        vacs = np.fromiter(sol.values(), dtype=int, count=len(sol))
        charge = np.zeros(problem.n_vacations)
        np.add.at(charge, vacs, problem._pat_duree[pids])
        overflow_vac = float(np.maximum(0, charge - problem._vac_capacity).sum())
        occ = problem.occupation_lits(sol)
        overflow_lits = float(np.maximum(0, occ - problem._lits_capacity_arr).sum())
        marge_moy = float(np.maximum(0, problem._vac_capacity - charge).mean())
        pic_lits = int(occ.max()) if len(occ) > 0 else 0
        diff_count = sum(1 for p in sol if sol[p] != sol_nominale.get(p, -1))
        taux_diff = diff_count / max(1, len(sol))

        df_sol = _solution_to_detail_dataframe(problem, sol)

        resultats[nom] = PlanningAlternatifResult(
            nom=nom,
            description=desc,
            solution=sol,
            fitness=problem.fitness(sol),
            overflow_vacation=overflow_vac,
            overflow_lits=overflow_lits,
            marge_moyenne_bloc_min=marge_moy,
            pic_lits=pic_lits,
            taux_patients_differents=taux_diff,
            planning_df=df_sol,
        )

    return resultats


def _generer_solution_diversifiee(
    problem: PlanningProblem,
    reference: Solution,
    seed: int = 42,
    n_iter: int = 1500,
    T0: float = 40.0,
    alpha: float = 0.96,
    w_distance: float = 4.0,
    **kwargs,
) -> Solution:
    """Genere une solution de haute fitness mais s'eloignant de la solution
    de reference (distance de Hamming favorisee pour maximiser les options Date B).
    """
    rng = random.Random(seed)
    current = problem.random_solution(rng)

    def _eval(sol: Solution) -> float:
        f = problem.fitness(sol)
        diffs = sum(1 for p, v in sol.items() if v != reference.get(p, -1))
        # bonus de distance par rapport a reference
        return f + w_distance * (diffs / max(1, problem.n_patients))

    current_score = _eval(current)
    best = dict(current)
    best_score = current_score
    T = T0

    for _ in range(n_iter):
        neighbor, _ = problem.neighbor(current, rng)
        sc = _eval(neighbor)
        delta = sc - current_score
        if delta >= 0 or rng.random() < np.exp(delta / max(T, 1e-9)):
            current, current_score = neighbor, sc
            if current_score > best_score:
                best, best_score = dict(current), current_score
        T *= alpha

    return best


def extraire_options_date_a_b(
    problem: PlanningProblem,
    solution_a: Solution,
    solution_b: Solution,
    nom_a: str = "Date A (Nominal)",
    nom_b: str = "Date B (Alternatif)",
) -> pd.DataFrame:
    """Compare deux plannings et extrait pour chaque patient ses deux options
    optimales de rendez-vous (Date A et Date B), conformement aux consignes
    du projet hospitalier (consultation preparatoire et arbitrage chirurgien).
    """
    lignes = []
    for pid in range(problem.n_patients):
        pid_reel = problem.patients.loc[pid, "patient_id"]
        spec = problem.patients.loc[pid, "specialite"]
        duree = problem.patients.loc[pid, "duree_operatoire"]
        sejour = problem.patients.loc[pid, "duree_sejour"]

        vac_a = solution_a.get(pid)
        vac_b = solution_b.get(pid)

        if vac_a is not None and vac_b is not None:
            jour_a = int(problem._vac_day[vac_a])
            jour_b = int(problem._vac_day[vac_b])
            vac_id_a = problem.vacations.loc[vac_a, "vacation_id"]
            vac_id_b = problem.vacations.loc[vac_b, "vacation_id"]

            jours_distincts = jour_a != jour_b
            meme_vacation = vac_a == vac_b

            if meme_vacation:
                recommandation = "Option unique optimale"
            elif jours_distincts:
                recommandation = f"Alternative a J{jour_b} proposee"
            else:
                recommandation = "Meme jour, autre vacation de salle"

            lignes.append(
                {
                    "patient_id": pid_reel,
                    "specialite": spec,
                    "duree_operatoire": duree,
                    "duree_sejour": sejour,
                    "option_A_jour": jour_a,
                    "option_A_vacation": vac_id_a,
                    "option_B_jour": jour_b,
                    "option_B_vacation": vac_id_b,
                    "jours_distincts": jours_distincts,
                    "meme_creneau": meme_vacation,
                    "recommandation": recommandation,
                }
            )

    df = pd.DataFrame(lignes)
    return df.sort_values(["option_A_jour", "option_A_vacation", "patient_id"]).reset_index(drop=True)


def _solution_to_detail_dataframe(problem: PlanningProblem, solution: Solution) -> pd.DataFrame:
    """Version etendue de solution_to_dataframe avec statut et capacites."""
    pids = list(solution.keys())
    vacs = [solution[pid] for pid in pids]
    out = pd.DataFrame(
        {
            "patient_id": problem.patients["patient_id"].to_numpy()[pids],
            "specialite": problem._pat_specialite[pids],
            "duree_operatoire": problem._pat_duree[pids],
            "duree_sejour": problem._pat_sejour[pids],
            "vacation_id": problem.vacations["vacation_id"].to_numpy()[vacs],
            "jour_vacation": problem._vac_day[vacs],
        }
    )
    return out.sort_values(["jour_vacation", "vacation_id", "patient_id"]).reset_index(drop=True)


# --------------------------------------------------------------------------
# 4. Adaptation dynamique (Reactive Replanning)
# --------------------------------------------------------------------------

@dataclass
class DeplacementPatient:
    """Detail d'un patient deplace lors de l'adaptation dynamique."""
    patient_id: int | str
    vacation_avant: int
    jour_avant: int
    vacation_apres: int
    jour_apres: int
    est_changement_jour: bool
    motif: str


@dataclass
class AdaptationResult:
    """Synthese complete du processus d'adaptation dynamique."""
    solution_initiale: Solution
    solution_adaptee: Solution
    problem_initial: PlanningProblem
    problem_adapte: PlanningProblem
    scenario: ScenarioAleas
    jour_courant: int
    patients_deplaces: list[DeplacementPatient]
    urgences_affectees: list[dict]
    annulations_appliquees: list[int | str]
    patients_geles: list[int | str]
    fitness_initiale: float
    fitness_adaptee: float
    perturbation_count: int
    duree_calcul_s: float
    rapport: str


def adapter_planning(
    problem: PlanningProblem,
    solution_initiale: Solution,
    scenario: ScenarioAleas,
    jour_courant: int = 1,
    w_perturbation: float = 3.0,
    w_changement_jour: float = 8.0,
    n_iter: int = 350,
    methode: str = METHODE_TABOU,
    seed: int = 0,
) -> AdaptationResult:
    """Adapte dynamiquement un planning existant suite a la survenue d'aleas.

    Principes cles :
      1. Gel des interventions passees : tout patient programme sur un
         jour < jour_courant ne peut plus etre modifie.
      2. Annulations : liberation immediate des creneaux de bloc et lits des
         patients annules a partir de jour_courant.
      3. Urgences : insertion prioritaire des urgences dans les vacations
         compatibles du jour d'apparition (ou selon le delai max).
      4. Retards & Lits : recalcul des capacites effectives restantes.
      5. Moindre perturbation : minimisation du nombre de deplacements de
         patients futurs (cout de stabilite).
    """
    t0 = time.perf_counter()
    rng = random.Random(seed)

    # 1. Identifier les patients geles (jour < jour_courant)
    patients_geles_indices = set()
    patients_geles_ids = []
    for pid_idx, vac_idx in solution_initiale.items():
        if problem._vac_day[vac_idx] < jour_courant:
            patients_geles_indices.add(pid_idx)
            patients_geles_ids.append(problem.patients.loc[pid_idx, "patient_id"])

    # 2. Filtrer les annulations applicables (seulement pour patients non geles)
    annulations_ids = {a.patient_id for a in scenario.annulations}
    annulations_retenues = []
    for a in scenario.annulations:
        # verifier si le patient est dans le planning
        matches = problem.patients.index[problem.patients["patient_id"] == a.patient_id].tolist()
        if matches:
            idx = matches[0]
            if idx not in patients_geles_indices:
                annulations_retenues.append(a.patient_id)

    # 3. Construire la nouvelle table des patients (anciens non-annules + urgences)
    patients_lignes = []
    id_mapping_ancien_vers_nouveau: dict[int, int] = {}
    id_mapping_nouveau_vers_ancien: dict[int, int] = {}
    new_pid_idx = 0

    for old_idx, row in problem.patients.iterrows():
        p_id = row["patient_id"]
        if p_id in annulations_retenues:
            continue  # patient annule retire
        id_mapping_ancien_vers_nouveau[old_idx] = new_pid_idx
        id_mapping_nouveau_vers_ancien[new_pid_idx] = old_idx
        patients_lignes.append(
            {
                "patient_id": p_id,
                "specialite": row["specialite"],
                "duree_operatoire": row["duree_operatoire"],
                "duree_sejour": row["duree_sejour"],
                "is_urgence": False,
                "id_origine": p_id,
            }
        )
        new_pid_idx += 1

    # Ajouter les urgences
    urgences_nouveaux_indices = []
    for u in scenario.urgences:
        urgences_nouveaux_indices.append((new_pid_idx, u))
        patients_lignes.append(
            {
                "patient_id": u.patient_id,
                "specialite": u.specialite,
                "duree_operatoire": u.duree_operatoire,
                "duree_sejour": u.duree_sejour,
                "is_urgence": True,
                "id_origine": u.patient_id,
            }
        )
        new_pid_idx += 1

    patients_adapte_df = pd.DataFrame(patients_lignes)

    # 4. Mettre a jour les capacites de lits (prise en compte des indisponibilites)
    lits_arr_adapte = problem._lits_capacity_arr.copy()
    for indisp in scenario.indisponibilites_lits:
        debut = max(jour_courant, indisp.jour_debut)
        fin = min(problem.n_days - 1, indisp.jour_fin)
        if fin >= debut:
            lits_arr_adapte[debut : fin + 1] = np.maximum(
                0.0, lits_arr_adapte[debut : fin + 1] - indisp.lits_perdus
            )

    # 5. Mettre a jour les retards bloc
    delays_adapte = (
        problem.vacation_delays.copy()
        if hasattr(problem, "vacation_delays")
        else np.zeros(problem.n_vacations)
    )
    for retard in scenario.retards_bloc:
        # recherche de l'indice de la vacation
        matches = problem.vacations.index[
            problem.vacations["vacation_id"] == retard.vacation_id
        ].tolist()
        if matches:
            v_idx = matches[0]
            delays_adapte[v_idx] += retard.retard_min
        elif 0 <= retard.vacation_id < problem.n_vacations:
            delays_adapte[retard.vacation_id] += retard.retard_min

    # Nouveau probleme adapte
    problem_adapte = PlanningProblem(
        patients_df=patients_adapte_df,
        vacations_df=problem.vacations.copy(),
        lits_capacity=lits_arr_adapte,
        vacation_delays=delays_adapte,
        w_vacation=problem.w_vacation,
        w_lits=problem.w_lits,
        w_balance=problem.w_balance,
    )

    # 6. Ensemble des indices geles dans le nouveau probleme
    nouveaux_geles = {
        id_mapping_ancien_vers_nouveau[old_idx]
        for old_idx in patients_geles_indices
        if old_idx in id_mapping_ancien_vers_nouveau
    }

    # 7. Initialiser la solution de depart pour l'adaptation (warm-start)
    solution_depart: Solution = {}
    for old_idx, vac_idx in solution_initiale.items():
        if old_idx in id_mapping_ancien_vers_nouveau:
            new_idx = id_mapping_ancien_vers_nouveau[old_idx]
            solution_depart[new_idx] = vac_idx

    # Affecter les urgences par une regle gloutonne (vacation compatible la moins chargee)
    charge_courante = np.zeros(problem_adapte.n_vacations)
    for p_idx, v_idx in solution_depart.items():
        charge_courante[v_idx] += problem_adapte._pat_duree[p_idx]

    urgences_options_restreintes: dict[int, list[int]] = {}
    for new_idx, u in urgences_nouveaux_indices:
        compatibles = problem_adapte._patient_options[new_idx]
        # Restreindre aux vacations dans la fenetre d'urgence :
        # jour_apparition <= jour <= jour_apparition + delai_max_jours
        jour_max = min(problem_adapte.n_days - 1, u.jour_apparition + u.delai_max_jours)
        options_urg = [
            v for v in compatibles if u.jour_apparition <= problem_adapte._vac_day[v] <= jour_max
        ]
        if not options_urg:
            # repli : toutes les options a partir du jour d'apparition
            options_urg = [v for v in compatibles if problem_adapte._vac_day[v] >= u.jour_apparition]
        if not options_urg:
            options_urg = list(compatibles)

        urgences_options_restreintes[new_idx] = options_urg

        # Choix glouton de la vacation la moins saturee
        meilleure_vac = min(
            options_urg,
            key=lambda v: charge_courante[v] / max(1.0, problem_adapte._vac_capacity[v]),
        )
        solution_depart[new_idx] = int(meilleure_vac)
        charge_courante[meilleure_vac] += problem_adapte._pat_duree[new_idx]

    # Patients deplacables : tous sauf les geles
    patients_deplacables = [i for i in range(problem_adapte.n_patients) if i not in nouveaux_geles]

    # Reference des affectations initiales pour la penalite de perturbation
    ref_initiale = dict(solution_depart)

    # 8. Métaheuristique de re-optimisation locale sous contrainte de stabilite
    def _score_adaptation(sol: Solution) -> float:
        f = problem_adapte.fitness(sol)
        penalite = 0.0
        for pid in patients_deplacables:
            # Ne penaliser que les patients electifs initiaux (pas les urgences)
            if pid not in urgences_options_restreintes:
                v_curr = sol[pid]
                v_init = ref_initiale[pid]
                if v_curr != v_init:
                    if problem_adapte._vac_day[v_curr] != problem_adapte._vac_day[v_init]:
                        penalite += w_changement_jour
                    else:
                        penalite += w_perturbation
        return f - penalite

    def _voisin_adapte(sol: Solution) -> tuple[Solution, tuple]:
        sol2 = dict(sol)
        if not patients_deplacables:
            return sol2, ("noop",)

        pid = rng.choice(patients_deplacables)
        if pid in urgences_options_restreintes:
            opts = urgences_options_restreintes[pid]
        else:
            # pour un patient non-urgent, favoriser des vacations a partir de jour_courant
            toutes_opts = problem_adapte._patient_options[pid]
            futures = [v for v in toutes_opts if problem_adapte._vac_day[v] >= jour_courant]
            opts = futures if futures else list(toutes_opts)

        nouv_vac = int(rng.choice(opts))
        sol2[pid] = nouv_vac
        return sol2, ("reassign", pid, nouv_vac)

    # Recherche taboue reactive
    current = dict(solution_depart)
    current_score = _score_adaptation(current)
    best = dict(current)
    best_score = current_score

    tabu_list: deque = deque(maxlen=25)
    neighborhood_size = min(20, max(5, len(patients_deplacables) * 2))

    for k in range(n_iter):
        candidats = []
        for _ in range(neighborhood_size):
            voisin, mvt = _voisin_adapte(current)
            sc = _score_adaptation(voisin)
            candidats.append((voisin, mvt, sc))
        candidats.sort(key=lambda c: c[2], reverse=True)

        choisi = None
        for voisin, mvt, sc in candidats:
            if (mvt not in tabu_list) or (sc > best_score):
                choisi = (voisin, mvt, sc)
                break
        if choisi is None:
            choisi = candidats[0]

        current, mvt, current_score = choisi
        tabu_list.append(mvt)
        if current_score > best_score:
            best, best_score = dict(current), current_score

    solution_adaptee = best
    duree_calc = time.perf_counter() - t0

    # 9. Analyser les deplacements et impacts
    deplacements: list[DeplacementPatient] = []
    urgences_affectees: list[dict] = []

    for new_idx in range(problem_adapte.n_patients):
        p_row = problem_adapte.patients.loc[new_idx]
        p_id = p_row["patient_id"]
        vac_apres = solution_adaptee[new_idx]
        jour_apres = int(problem_adapte._vac_day[vac_apres])
        vac_id_apres = problem_adapte.vacations.loc[vac_apres, "vacation_id"]

        if p_row["is_urgence"]:
            urgences_affectees.append(
                {
                    "patient_id": p_id,
                    "specialite": p_row["specialite"],
                    "duree_operatoire": p_row["duree_operatoire"],
                    "vacation_id": vac_id_apres,
                    "jour": jour_apres,
                }
            )
        else:
            old_idx = id_mapping_nouveau_vers_ancien[new_idx]
            vac_avant = solution_initiale[old_idx]
            jour_avant = int(problem._vac_day[vac_avant])
            vac_id_avant = problem.vacations.loc[vac_avant, "vacation_id"]

            if vac_apres != vac_avant:
                changement_j = jour_apres != jour_avant
                motif_dep = (
                    "Decalage sur autre jour pour absorber aleas"
                    if changement_j
                    else "Reaffectation de salle le meme jour"
                )
                deplacements.append(
                    DeplacementPatient(
                        patient_id=p_id,
                        vacation_avant=vac_id_avant,
                        jour_avant=jour_avant,
                        vacation_apres=vac_id_apres,
                        jour_apres=jour_apres,
                        est_changement_jour=changement_j,
                        motif=motif_dep,
                    )
                )

    fitness_init = problem.fitness(solution_initiale)
    fitness_adap = problem_adapte.fitness(solution_adaptee)

    # 10. Redaction du rapport d'adaptation detaille
    rapport = _generer_rapport_adaptation(
        scenario=scenario,
        jour_courant=jour_courant,
        fitness_init=fitness_init,
        fitness_adap=fitness_adap,
        patients_geles=patients_geles_ids,
        annulations_retenues=annulations_retenues,
        urgences_affectees=urgences_affectees,
        deplacements=deplacements,
        duree_s=duree_calc,
    )

    return AdaptationResult(
        solution_initiale=solution_initiale,
        solution_adaptee=solution_adaptee,
        problem_initial=problem,
        problem_adapte=problem_adapte,
        scenario=scenario,
        jour_courant=jour_courant,
        patients_deplaces=deplacements,
        urgences_affectees=urgences_affectees,
        annulations_appliquees=annulations_retenues,
        patients_geles=patients_geles_ids,
        fitness_initiale=fitness_init,
        fitness_adaptee=fitness_adap,
        perturbation_count=len(deplacements),
        duree_calcul_s=duree_calc,
        rapport=rapport,
    )


def _generer_rapport_adaptation(
    scenario: ScenarioAleas,
    jour_courant: int,
    fitness_init: float,
    fitness_adap: float,
    patients_geles: list,
    annulations_retenues: list,
    urgences_affectees: list[dict],
    deplacements: list[DeplacementPatient],
    duree_s: float,
) -> str:
    sep = "=" * 78
    sous_sep = "-" * 78
    lignes = [
        sep,
        "             RAPPORT D'ADAPTATION DYNAMIQUE DU BLOC OPERATOIRE",
        sep,
        f"Point d'etape : Jour courant {jour_courant} | Temps d'optimisation reactive : {duree_s*1000:.1f} ms",
        f"Qualite du planning : Fitness initiale = {fitness_init:8.2f} -> Fitness adaptee = {fitness_adap:8.2f}",
        sous_sep,
        "1. SYNTHESE DES ALEAS CONSIDERES :",
        f"   - {len(urgences_affectees)} Urgence(s) arrivee(s)",
        f"   - {len(annulations_retenues)} Annulation(s) validee(s)",
        f"   - {len(scenario.indisponibilites_lits)} Periode(s) de tension / lits indisponibles",
        f"   - {len(scenario.retards_bloc)} Vacation(s) impactee(s) par un retard de bloc",
        sous_sep,
        f"2. GESTION DES HISTORIQUES ET CONTRAINTES DE STABILITE :",
        f"   - Patients geles (passes) : {len(patients_geles)} patient(s) sanctuarise(s) (jours < {jour_courant})",
        f"   - Perturbation de planning : {len(deplacements)} patient(s) deplace(s) au total",
    ]

    if urgences_affectees:
        lignes.append(sous_sep)
        lignes.append("3. INTEGRATION DES URGENCES :")
        for u in urgences_affectees:
            lignes.append(
                f"   [+] Urgence {u['patient_id']} ({u['specialite']}, {u['duree_operatoire']} min) -> Affectee au Jour {u['jour']}, Vacation {u['vacation_id']}"
            )

    if annulations_retenues:
        lignes.append(sous_sep)
        lignes.append("4. ANNULATIONS TRAITEES :")
        for a_id in annulations_retenues:
            lignes.append(f"   [-] Patient {a_id} retire du planning (creneaux et lits liberes)")

    if deplacements:
        lignes.append(sous_sep)
        lignes.append("5. DEPLACEMENTS DE PATIENTS (ARBITRAGES DE MOINDRE PERTURBATION) :")
        for d in deplacements:
            chg = "Changement de jour" if d.est_changement_jour else "Meme jour (autre vacation)"
            lignes.append(
                f"   [~] Patient {d.patient_id} : J{d.jour_avant} (V{d.vacation_avant}) -> J{d.jour_apres} (V{d.vacation_apres}) [{chg}]"
            )
    else:
        lignes.append(sous_sep)
        lignes.append("5. AUCUN DEPLACEMENT NECESSAIRE : les aleas ont ete absorbes par les marges existantes !")

    lignes.append(sep)
    return "\n".join(lignes)
