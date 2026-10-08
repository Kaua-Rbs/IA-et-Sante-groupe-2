"""
coordination_bridge.py
----------------------
Pont entre le noyau d'optimisation (``optimiseur.optimizer``) et le
squelette de coordination asynchrone ``hospital_sim``.

- ``EtatBloc`` : etat du domaine (patients, vacations, indisponibilites) ;
- ``Planning`` : planning propose (patient_id -> vacation_id) ;
- ``EtatBlocAdapter`` : applique les evenements hospitaliers a l'etat ;
- ``PlanificateurOptimiseur`` : ``Scheduler`` asynchrone qui execute une
  metaheuristique dans un thread (``asyncio.to_thread``) pour ne pas bloquer
  la boucle d'evenements ;
- ``ValidateurBloc`` : verifie la faisabilite (capacites vacations et lits)
  avant acceptation explicite par le ``Coordinator``.

Le sens des dependances reste ``optimiseur`` -> ``hospital_sim`` : le noyau
d'optimisation ne connait pas la couche de coordination, seul ce pont fait
le lien.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace

import pandas as pd

from hospital_sim.contracts import (
    EventKind,
    HospitalEvent,
    Proposal,
    SchedulingRequest,
    Snapshot,
    ValidationResult,
)

from . import optimizer as op

# Methode de planification par defaut pour la re-planification dynamique.
METHODE_PLANIFICATION = op.METHODE_SMA_HYBRIDE


# --------------------------------------------------------------------------
# 1. Types du domaine
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class EtatBloc:
    """Etat du bloc : tables patients / vacations et vacations indisponibles."""

    patients: pd.DataFrame
    vacations: pd.DataFrame
    lits_capacity: int = 42
    indisponibles: frozenset[int] = frozenset()


@dataclass(frozen=True)
class Planning:
    """Planning propose au coordinateur (patient_id -> vacation_id)."""

    affectation: dict[int, int]
    methode: str = ""
    fitness: float = 0.0


# --------------------------------------------------------------------------
# 2. Adaptateur d'etat : application des evenements
# --------------------------------------------------------------------------

def _entier_payload(event: HospitalEvent, cle: str) -> int:
    if cle not in event.payload:
        raise ValueError(f"Payload incomplet : {cle} est requis")
    return int(event.payload[cle])  # type: ignore[arg-type]


class EtatBlocAdapter:
    """``StateAdapter`` du contrat hospital_sim pour le domaine du bloc.

    Evenements supportes :

    - ``RESOURCE_UNAVAILABLE`` : ``vacation_id`` devient indisponible ;
    - ``CANCELLATION`` : ``patient_id`` est retire du planning ;
    - ``EMERGENCY_ARRIVAL`` : ajoute un patient (``patient_id`` optionnel,
      ``specialite``, ``duree_operatoire``, ``duree_sejour`` optionnel) ;
    - ``DELAYED_DISCHARGE`` : ``patient_id``, ``jours`` (defaut 1) ;
    - ``SURGERY_OVERRUN`` : ``vacation_id``, ``minutes`` de capacite en moins.

    Tout autre evenement leve ``ValueError`` (contrat du ``StateAdapter``).
    """

    def apply_event(self, snapshot: Snapshot, event: HospitalEvent) -> EtatBloc:
        etat: EtatBloc = snapshot.domain

        if event.kind is EventKind.RESOURCE_UNAVAILABLE:
            vac_id = _entier_payload(event, "vacation_id")
            if vac_id not in set(etat.vacations["vacation_id"]):
                raise ValueError(f"Vacation inconnue : {vac_id}")
            return replace(etat, indisponibles=etat.indisponibles | {vac_id})

        if event.kind is EventKind.CANCELLATION:
            pid = _entier_payload(event, "patient_id")
            patients = etat.patients
            if pid not in set(patients["patient_id"]):
                raise ValueError(f"Patient inconnu : {pid}")
            return replace(
                etat, patients=patients[patients["patient_id"] != pid].reset_index(drop=True)
            )

        if event.kind is EventKind.EMERGENCY_ARRIVAL:
            payload = event.payload
            if "specialite" not in payload or "duree_operatoire" not in payload:
                raise ValueError("Payload incomplet : specialite et duree_operatoire sont requis")
            deja = set(etat.patients["patient_id"])
            pid = int(payload.get("patient_id", max(deja) + 1 if deja else 0))
            if pid in deja:
                raise ValueError(f"Patient deja present : {pid}")
            ligne = pd.DataFrame(
                [{
                    "patient_id": pid,
                    "specialite": payload["specialite"],
                    "duree_operatoire": int(payload["duree_operatoire"]),  # type: ignore[arg-type]
                    "duree_sejour": int(payload.get("duree_sejour", 0)),  # type: ignore[arg-type]
                }]
            )
            return replace(etat, patients=pd.concat([etat.patients, ligne], ignore_index=True))

        if event.kind is EventKind.DELAYED_DISCHARGE:
            pid = _entier_payload(event, "patient_id")
            jours = int(event.payload.get("jours", 1))  # type: ignore[arg-type]
            if jours < 0:
                raise ValueError("jours doit etre positif")
            patients = etat.patients.copy()
            masque = patients["patient_id"] == pid
            if not masque.any():
                raise ValueError(f"Patient inconnu : {pid}")
            patients.loc[masque, "duree_sejour"] += jours
            return replace(etat, patients=patients)

        if event.kind is EventKind.SURGERY_OVERRUN:
            vac_id = _entier_payload(event, "vacation_id")
            minutes = float(event.payload.get("minutes", 0.0))  # type: ignore[arg-type]
            if minutes < 0:
                raise ValueError("minutes doit etre positif")
            vacations = etat.vacations.copy()
            masque = vacations["vacation_id"] == vac_id
            if not masque.any():
                raise ValueError(f"Vacation inconnue : {vac_id}")
            vacations.loc[masque, "capacite_min"] = (
                vacations.loc[masque, "capacite_min"] - minutes
            ).clip(lower=0)
            return replace(etat, vacations=vacations)

        raise ValueError(f"Evenement non supporte : {event.kind}")

    def fixed_commitments(self, snapshot: Snapshot) -> frozenset[int]:
        """Aucun engagement fixe dans le modele simplifie (point d'extension)."""
        return frozenset()


# --------------------------------------------------------------------------
# 3. Conversions etat <-> PlanningProblem
# --------------------------------------------------------------------------

def probleme_depuis_etat(etat: EtatBloc) -> op.PlanningProblem:
    """Construit un ``PlanningProblem`` en retirant les vacations indisponibles."""
    vacations = etat.vacations
    if etat.indisponibles:
        vacations = vacations[~vacations["vacation_id"].isin(etat.indisponibles)]
    return op.PlanningProblem(
        etat.patients, vacations.reset_index(drop=True), lits_capacity=etat.lits_capacity
    )


def affectation_vers_solution(problem: op.PlanningProblem, affectation: dict[int, int]) -> op.Solution:
    """Convertit patient_id -> vacation_id en patient_id -> indice interne."""
    index_pid = {int(pid): i for i, pid in enumerate(problem.patients["patient_id"])}
    index_vid = {int(vid): i for i, vid in enumerate(problem.vacations["vacation_id"])}
    return {index_pid[int(pid)]: index_vid[int(vid)] for pid, vid in affectation.items()}


def solution_vers_affectation(problem: op.PlanningProblem, solution: op.Solution) -> dict[int, int]:
    """Convertit patient_id -> indice interne en patient_id -> vacation_id."""
    pids = problem.patients["patient_id"].to_numpy()
    vids = problem.vacations["vacation_id"].to_numpy()
    return {int(pids[i]): int(vids[solution[i]]) for i in range(problem.n_patients)}


# --------------------------------------------------------------------------
# 4. Scheduler et validateur
# --------------------------------------------------------------------------

class PlanificateurOptimiseur:
    """``Scheduler`` : lance une metaheuristique sur un snapshot gele.

    L'optimisation CPU se fait dans un thread via ``asyncio.to_thread`` pour
    garder la boucle d'evenements reactive (le coordinateur peut annuler).
    """

    def __init__(
        self,
        methode: str = METHODE_PLANIFICATION,
        budget_s: float = 1.0,
        seed: int = 0,
        kwargs_methode: dict | None = None,
    ):
        if methode not in op.KWARGS_PAR_METHODE:
            raise ValueError(f"Methode inconnue : {methode}")
        self.methode = methode
        self.budget_s = budget_s
        self.seed = seed
        self.kwargs_methode = kwargs_methode or {}

    def _optimiser(self, request: SchedulingRequest, budget: float) -> Proposal | None:
        etat: EtatBloc = request.snapshot.domain
        problem = probleme_depuis_etat(etat)
        if problem.n_vacations == 0 or problem.n_patients == 0:
            return None
        resultats = op.optimize_planning(
            problem.patients,
            problem.vacations,
            lits_capacity=etat.lits_capacity,
            seed=self.seed,
            methodes=[self.methode],
            time_budget_s=budget,
            **{op.KWARGS_PAR_METHODE[self.methode]: self.kwargs_methode},
        )
        resultat = resultats[self.methode]
        planning = Planning(
            affectation=solution_vers_affectation(problem, resultat.meilleure_solution),
            methode=self.methode,
            fitness=resultat.meilleure_fitness,
        )
        return Proposal(schedule=planning, base_version=request.snapshot.version)

    async def propose(self, request: SchedulingRequest) -> Proposal | None:
        reste = request.deadline - time.monotonic()
        if reste <= 0:
            return None
        budget = min(self.budget_s, reste)
        return await asyncio.to_thread(self._optimiser, request, budget)


class ValidateurBloc:
    """``Validator`` : verifie que le planning propose respecte le snapshot.

    Controles : version de base, couverture exacte des patients, vacations
    connues et compatibles, capacites vacations et lits non depassees.
    ``PlanningProblem.violations`` separe les contraintes dures (capacites)
    du critere souple d'equilibrage de ``fitness``.
    """

    def validate(self, snapshot: Snapshot, proposal: Proposal) -> ValidationResult:
        raisons: list[str] = []
        if proposal.base_version != snapshot.version:
            return ValidationResult(False, ("Version de base obsolete",))

        etat: EtatBloc = snapshot.domain
        problem = probleme_depuis_etat(etat)
        if problem.n_vacations == 0:
            return ValidationResult(False, ("Aucune vacation disponible",))

        attendus = {int(pid) for pid in problem.patients["patient_id"]}
        fournis = {int(pid) for pid in proposal.schedule.affectation}
        if attendus != fournis:
            raisons.append(
                f"Patients manquants : {sorted(attendus - fournis)} ; inconnus : {sorted(fournis - attendus)}"
            )
            return ValidationResult(False, tuple(raisons))

        try:
            solution = affectation_vers_solution(problem, proposal.schedule.affectation)
        except KeyError as exc:
            raisons.append(f"Vacation ou patient inconnu : {exc}")
            return ValidationResult(False, tuple(raisons))

        depassement_vac, depassement_lits = problem.violations(solution)
        if depassement_vac > 1e-6:
            raisons.append(f"Capacite vacation depassee de {depassement_vac:.1f} min")
        if depassement_lits > 1e-6:
            raisons.append(f"Capacite lits depassee de {depassement_lits:.1f} lits-jours")
        return ValidationResult(not raisons, tuple(raisons))
