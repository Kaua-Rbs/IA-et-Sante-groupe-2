"""Tests du pont de coordination optimiseur <-> hospital_sim."""

from __future__ import annotations

import time
import unittest
from types import SimpleNamespace

import pandas as pd

from hospital_sim.contracts import (
    EventKind,
    HospitalEvent,
    Proposal,
    SchedulingRequest,
    Snapshot,
)
from hospital_sim.coordinator import Coordinator
from optimiseur import optimizer as op
from optimiseur.coordination_bridge import (
    EtatBloc,
    EtatBlocAdapter,
    PlanificateurOptimiseur,
    Planning,
    ValidateurBloc,
    affectation_vers_solution,
    probleme_depuis_etat,
    solution_vers_affectation,
)


def _etat(patients=None, vacations=None, lits_capacity: int = 20, indisponibles=frozenset()):
    patients = patients or [
        {"patient_id": 0, "specialite": "X", "duree_operatoire": 60, "duree_sejour": 1},
        {"patient_id": 1, "specialite": "X", "duree_operatoire": 50, "duree_sejour": 0},
        {"patient_id": 2, "specialite": "Y", "duree_operatoire": 40, "duree_sejour": 1},
    ]
    vacations = vacations or [
        {"vacation_id": 10, "jour": 0, "specialite": "X", "capacite_min": 600},
        {"vacation_id": 11, "jour": 1, "specialite": "X", "capacite_min": 600},
        {"vacation_id": 12, "jour": 0, "specialite": "Y", "capacite_min": 600},
    ]
    return EtatBloc(
        pd.DataFrame(patients),
        pd.DataFrame(vacations),
        lits_capacity=lits_capacity,
        indisponibles=indisponibles,
    )


def _snapshot(etat: EtatBloc, version: int = 0) -> Snapshot:
    return Snapshot(float(version), version, etat, None)


class TestEtatBlocAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = EtatBlocAdapter()
        self.etat = _etat()

    def test_resource_unavailable(self):
        event = HospitalEvent("e", 1.0, EventKind.RESOURCE_UNAVAILABLE, {"vacation_id": 10})
        nouveau = self.adapter.apply_event(_snapshot(self.etat), event)
        self.assertEqual(nouveau.indisponibles, frozenset({10}))
        self.assertEqual(self.etat.indisponibles, frozenset())  # etat d'origine intact

    def test_resource_inconnue(self):
        event = HospitalEvent("e", 1.0, EventKind.RESOURCE_UNAVAILABLE, {"vacation_id": 999})
        with self.assertRaises(ValueError):
            self.adapter.apply_event(_snapshot(self.etat), event)

    def test_cancellation(self):
        event = HospitalEvent("e", 1.0, EventKind.CANCELLATION, {"patient_id": 1})
        nouveau = self.adapter.apply_event(_snapshot(self.etat), event)
        self.assertEqual(set(nouveau.patients["patient_id"]), {0, 2})

    def test_cancellation_patient_inconnu(self):
        event = HospitalEvent("e", 1.0, EventKind.CANCELLATION, {"patient_id": 42})
        with self.assertRaises(ValueError):
            self.adapter.apply_event(_snapshot(self.etat), event)

    def test_arrivee_urgence_id_auto(self):
        event = HospitalEvent(
            "e", 1.0, EventKind.EMERGENCY_ARRIVAL,
            {"specialite": "X", "duree_operatoire": 90, "duree_sejour": 2},
        )
        nouveau = self.adapter.apply_event(_snapshot(self.etat), event)
        self.assertEqual(len(nouveau.patients), 4)
        ligne = nouveau.patients.iloc[-1]
        self.assertEqual(ligne["patient_id"], 3)
        self.assertEqual(ligne["duree_operatoire"], 90)

    def test_arrivee_urgence_doublon(self):
        event = HospitalEvent(
            "e", 1.0, EventKind.EMERGENCY_ARRIVAL,
            {"patient_id": 0, "specialite": "X", "duree_operatoire": 90},
        )
        with self.assertRaises(ValueError):
            self.adapter.apply_event(_snapshot(self.etat), event)

    def test_sejour_prolonge(self):
        event = HospitalEvent("e", 1.0, EventKind.DELAYED_DISCHARGE, {"patient_id": 0, "jours": 3})
        nouveau = self.adapter.apply_event(_snapshot(self.etat), event)
        self.assertEqual(int(nouveau.patients.loc[nouveau.patients["patient_id"] == 0, "duree_sejour"].iloc[0]), 4)

    def test_depassement_bloc(self):
        event = HospitalEvent("e", 1.0, EventKind.SURGERY_OVERRUN, {"vacation_id": 10, "minutes": 100})
        nouveau = self.adapter.apply_event(_snapshot(self.etat), event)
        self.assertEqual(int(nouveau.vacations.loc[nouveau.vacations["vacation_id"] == 10, "capacite_min"].iloc[0]), 500)

    def test_evenement_non_supporte(self):
        faux = SimpleNamespace(kind="inconnu", payload={})
        with self.assertRaises(ValueError):
            self.adapter.apply_event(_snapshot(self.etat), faux)

    def test_engagements_fixes(self):
        self.assertEqual(self.adapter.fixed_commitments(_snapshot(self.etat)), frozenset())


class TestConversions(unittest.TestCase):
    def test_aller_retour(self):
        etat = _etat()
        problem = probleme_depuis_etat(etat)
        affectation = {0: 11, 1: 10, 2: 12}
        solution = affectation_vers_solution(problem, affectation)
        self.assertEqual(solution_vers_affectation(problem, solution), affectation)

    def test_vacations_indisponibles_exclues(self):
        etat = _etat(indisponibles=frozenset({10}))
        problem = probleme_depuis_etat(etat)
        self.assertNotIn(10, set(problem.vacations["vacation_id"]))
        self.assertEqual(problem.n_vacations, 2)


class TestValidateur(unittest.TestCase):
    def setUp(self):
        self.etat = _etat()
        self.snapshot = _snapshot(self.etat)
        self.validator = ValidateurBloc()
        problem = probleme_depuis_etat(self.etat)
        self.solution = problem.random_solution()
        self.affectation = solution_vers_affectation(problem, self.solution)

    def test_valide(self):
        resultat = self.validator.validate(self.snapshot, Proposal(Planning(self.affectation, "test"), 0))
        self.assertTrue(resultat.feasible, resultat.reasons)

    def test_version_obsolete(self):
        resultat = self.validator.validate(self.snapshot, Proposal(Planning(self.affectation, "test"), 1))
        self.assertFalse(resultat.feasible)

    def test_patient_manquant(self):
        affectation = dict(self.affectation)
        affectation.pop(0)
        resultat = self.validator.validate(self.snapshot, Proposal(Planning(affectation, "test"), 0))
        self.assertFalse(resultat.feasible)
        self.assertTrue(any("Patients manquants" in raison for raison in resultat.reasons))

    def test_vacation_inconnue(self):
        affectation = dict(self.affectation)
        affectation[0] = 999
        resultat = self.validator.validate(self.snapshot, Proposal(Planning(affectation, "test"), 0))
        self.assertFalse(resultat.feasible)

    def test_capacite_depassee(self):
        etat = _etat(
            patients=[{"patient_id": 0, "specialite": "X", "duree_operatoire": 200, "duree_sejour": 0}],
            vacations=[{"vacation_id": 10, "jour": 0, "specialite": "X", "capacite_min": 120}],
        )
        snapshot = _snapshot(etat)
        resultat = self.validator.validate(snapshot, Proposal(Planning({0: 10}, "test"), 0))
        self.assertFalse(resultat.feasible)
        self.assertTrue(any("Capacite vacation" in raison for raison in resultat.reasons))


class TestPlanificateurOptimiseur(unittest.IsolatedAsyncioTestCase):
    async def test_propose_et_validation(self):
        etat = _etat()
        snapshot = _snapshot(etat)
        planificateur = PlanificateurOptimiseur(methode=op.METHODE_RECUIT, budget_s=0.5, seed=0)
        request = SchedulingRequest(snapshot, frozenset(), time.monotonic() + 5.0)
        proposal = await planificateur.propose(request)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal.base_version, 0)
        self.assertTrue(ValidateurBloc().validate(snapshot, proposal).feasible)

    async def test_deadline_depassee(self):
        etat = _etat()
        snapshot = _snapshot(etat)
        planificateur = PlanificateurOptimiseur(methode=op.METHODE_RECUIT, budget_s=0.5, seed=0)
        request = SchedulingRequest(snapshot, frozenset(), time.monotonic() - 1.0)
        self.assertIsNone(await planificateur.propose(request))

    async def test_methode_inconnue(self):
        with self.assertRaises(ValueError):
            PlanificateurOptimiseur(methode="inexistante")


class TestCoordinatorBoutEnBout(unittest.IsolatedAsyncioTestCase):
    async def test_replanification_apres_indisponibilite(self):
        etat = _etat()
        coordinator = Coordinator(
            initial=_snapshot(etat),
            state_adapter=EtatBlocAdapter(),
            scheduler=PlanificateurOptimiseur(methode=op.METHODE_HYBRIDE, budget_s=0.5, seed=0),
            validator=ValidateurBloc(),
            timeout_seconds=10.0,
        )
        async with coordinator:
            coordinator.submit(
                HospitalEvent("evt-1", 1.0, EventKind.RESOURCE_UNAVAILABLE, {"vacation_id": 10})
            )
            await coordinator.wait_idle()
            self.assertEqual(coordinator.outcomes[-1].status, "proposal_ready")
            resultat = coordinator.accept(coordinator.snapshot.version)
            self.assertTrue(resultat.feasible)
            planning = coordinator.snapshot.accepted_schedule
            self.assertIsInstance(planning, Planning)
            self.assertEqual(len(planning.affectation), 3)

            coordinator.submit(
                HospitalEvent(
                    "evt-2", 2.0, EventKind.EMERGENCY_ARRIVAL,
                    {"specialite": "Y", "duree_operatoire": 30, "duree_sejour": 0},
                )
            )
            await coordinator.wait_idle()
            self.assertEqual(coordinator.outcomes[-1].status, "proposal_ready")
            resultat = coordinator.accept(coordinator.snapshot.version)
            self.assertTrue(resultat.feasible)
            self.assertEqual(len(coordinator.snapshot.accepted_schedule.affectation), 4)


if __name__ == "__main__":
    unittest.main()
