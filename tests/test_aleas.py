"""Tests du module de gestion des aleas et d'adaptation dynamique."""

from __future__ import annotations

import unittest
import numpy as np
import pandas as pd

from optimiseur import optimizer as op
from optimiseur import aleas as al
from optimiseur import plotting as pl
from tests.helpers import make_problem


class TestStructuresAleas(unittest.TestCase):
    def test_creation_urgence(self):
        u = al.Urgence(
            patient_id="URG_1",
            specialite="Cardio",
            duree_operatoire=90,
            duree_sejour=2,
            jour_apparition=1,
            delai_max_jours=0,
            priorite=1,
        )
        self.assertEqual(u.patient_id, "URG_1")
        self.assertEqual(u.specialite, "Cardio")
        self.assertEqual(u.duree_operatoire, 90.0)
        self.assertEqual(u.jour_apparition, 1)

    def test_scenario_et_methodes_ajouts(self):
        sc = al.ScenarioAleas(nom="Test Scenario")
        self.assertTrue(sc.est_vide())

        sc.ajouter_urgence("U1", "ORL", 45, 1, 0)
        sc.ajouter_annulation(3, 1)
        sc.ajouter_indisponibilite_lits(1, 2, 4)
        sc.ajouter_retard_bloc(0, 30)

        self.assertFalse(sc.est_vide())
        self.assertEqual(sc.total_aleas(), 4)
        resume = sc.resume()
        self.assertIn("Test Scenario", resume)
        self.assertIn("Urgences : 1", resume)
        self.assertIn("Annulations : 1", resume)
        self.assertIn("Indisponibilites lits : 1", resume)
        self.assertIn("Retards bloc : 1", resume)


class TestGenererScenarioAleas(unittest.TestCase):
    def test_generer_scenario_reproductible(self):
        patients, vacations = op.generate_test_data(n_patients=20, n_days=3, seed=12)
        prob = op.PlanningProblem(patients, vacations)
        sol = prob.random_solution()

        sc1 = al.generer_scenario_aleas(prob, sol, jour_courant=1, n_urgences=2, n_annulations=1, seed=42)
        sc2 = al.generer_scenario_aleas(prob, sol, jour_courant=1, n_urgences=2, n_annulations=1, seed=42)

        self.assertEqual(len(sc1.urgences), 2)
        self.assertEqual(len(sc1.annulations), 1)
        self.assertEqual(sc1.urgences[0].patient_id, sc2.urgences[0].patient_id)
        self.assertEqual(sc1.urgences[0].duree_operatoire, sc2.urgences[0].duree_operatoire)
        self.assertEqual(sc1.annulations[0].patient_id, sc2.annulations[0].patient_id)


class TestPlanningsAlternatifs(unittest.TestCase):
    def setUp(self):
        self.patients, self.vacations = op.generate_test_data(n_patients=15, n_days=3, seed=5)
        self.prob = op.PlanningProblem(self.patients, self.vacations, lits_capacity=20)

    def test_generer_plannings_alternatifs_profils(self):
        alts = al.generer_plannings_alternatifs(
            self.prob,
            marge_buffer_bloc=0.15,
            marge_buffer_lits=0.15,
            seed=42,
            metaheuristic_kwargs={"n_iter": 100},
        )
        self.assertIn("Nominal", alts)
        self.assertIn("Robuste_Buffer", alts)
        self.assertIn("Securite_Lits", alts)
        self.assertIn("Alternatif_Date_B", alts)

        nom = alts["Nominal"]
        rob = alts["Robuste_Buffer"]
        self.assertIsInstance(nom.planning_df, pd.DataFrame)
        self.assertGreaterEqual(rob.marge_moyenne_bloc_min, 0.0)

        # L'alternatif diversifie doit presenter un taux de difference > 0
        div = alts["Alternatif_Date_B"]
        self.assertGreater(div.taux_patients_differents, 0.0)

    def test_extraire_options_date_a_b(self):
        sol_a = self.prob.random_solution()
        alts = al.generer_plannings_alternatifs(
            self.prob,
            solution_nominale=sol_a,
            seed=1,
            metaheuristic_kwargs={"n_iter": 50},
        )
        sol_b = alts["Alternatif_Date_B"].solution

        df_ab = al.extraire_options_date_a_b(self.prob, sol_a, sol_b)
        self.assertEqual(len(df_ab), self.prob.n_patients)
        self.assertIn("option_A_jour", df_ab.columns)
        self.assertIn("option_B_jour", df_ab.columns)
        self.assertIn("option_A_vacation", df_ab.columns)
        self.assertIn("option_B_vacation", df_ab.columns)
        self.assertIn("recommandation", df_ab.columns)


class TestAdaptationDynamique(unittest.TestCase):
    def setUp(self):
        self.patients, self.vacations = op.generate_test_data(n_patients=20, n_days=4, seed=10)
        self.prob = op.PlanningProblem(self.patients, self.vacations, lits_capacity=30)
        # Solution initiale valide
        res = op.simulated_annealing(self.prob, n_iter=200, seed=0)
        self.sol_init = res.meilleure_solution

    def test_gel_interventions_passees(self):
        jour_courant = 2
        # Identifier les patients dont l'affectation initiale est a jour < 2
        patients_passes = {
            pid: vac
            for pid, vac in self.sol_init.items()
            if self.prob._vac_day[vac] < jour_courant
        }
        self.assertGreater(len(patients_passes), 0)

        scenario = al.ScenarioAleas(nom="Test gel")
        scenario.ajouter_urgence("URG_T1", "Orthopedie", 80, 2, jour_apparition=2)
        scenario.ajouter_retard_bloc(0, 45)

        adap_res = al.adapter_planning(
            self.prob,
            self.sol_init,
            scenario,
            jour_courant=jour_courant,
            n_iter=100,
            seed=0,
        )

        # Verifier que chaque patient passe a conserve EXACTEMENT sa vacation initiale
        prob_adap = adap_res.problem_adapte
        sol_adap = adap_res.solution_adaptee
        for old_pid, vac_initiale in patients_passes.items():
            # Trouver l'indice dans prob_adap
            pid_reel = self.prob.patients.loc[old_pid, "patient_id"]
            new_idx = prob_adap.patients.index[prob_adap.patients["patient_id"] == pid_reel][0]
            self.assertEqual(
                sol_adap[new_idx],
                vac_initiale,
                msg=f"Le patient passe {pid_reel} aurait du etre gele",
            )

    def test_evenements_futurs_restent_caches_et_faisabilite_est_mesuree(self):
        scenario = al.ScenarioAleas(nom="Evenements futurs")
        scenario.ajouter_urgence("URG_FUTURE", "Cardio", 60, 1, jour_apparition=3)
        scenario.ajouter_annulation(self.patients.loc[0, "patient_id"], jour_notification=3)
        scenario.ajouter_indisponibilite_lits(3, 3, lits_perdus=5)

        result = al.adapter_planning(
            self.prob, self.sol_init, scenario, jour_courant=1, n_iter=20, seed=0,
        )
        self.assertEqual(len(result.problem_adapte.patients), len(self.patients))
        self.assertEqual(result.annulations_appliquees, [])
        self.assertTrue(np.array_equal(
            result.problem_adapte._lits_capacity_arr, self.prob._lits_capacity_arr,
        ))
        self.assertEqual(
            (result.depassement_vacation_min, result.depassement_lits_jours),
            result.problem_adapte.violations(result.solution_adaptee),
        )
        self.assertEqual(result.faisable,
                         result.depassement_vacation_min == 0 and result.depassement_lits_jours == 0)

    def test_urgence_sans_vacation_dans_sa_fenetre_est_refusee(self):
        patients = pd.DataFrame([
            {"patient_id": 1, "specialite": "X", "duree_operatoire": 30, "duree_sejour": 0},
        ])
        vacations = pd.DataFrame([
            {"vacation_id": 10, "jour": 1, "specialite": "X", "capacite_min": 120},
        ])
        problem = op.PlanningProblem(patients, vacations)
        scenario = al.ScenarioAleas(nom="Fenetre impossible")
        scenario.ajouter_urgence("URG_NOW", "X", 30, 0, jour_apparition=0,
                                 delai_max_jours=0)
        with self.assertRaisesRegex(ValueError, "Aucune vacation compatible"):
            al.adapter_planning(problem, {0: 0}, scenario, jour_courant=0,
                                n_iter=1)

        scenario_spec = al.ScenarioAleas(nom="Specialite impossible")
        scenario_spec.ajouter_urgence("URG_Y", "Y", 30, 0,
                                     jour_apparition=1, delai_max_jours=0)
        with self.assertRaisesRegex(ValueError, "Aucune vacation compatible"):
            al.adapter_planning(problem, {0: 0}, scenario_spec, jour_courant=1,
                                n_iter=1)

    def test_annulation_retiree_et_urgences_inserees(self):
        # Trouver un patient au jour 2
        pid_a_annuler = None
        for pid, vac in self.sol_init.items():
            if self.prob._vac_day[vac] >= 2:
                pid_a_annuler = self.prob.patients.loc[pid, "patient_id"]
                break

        self.assertIsNotNone(pid_a_annuler)

        scenario = al.ScenarioAleas(nom="Test annulation + urgence")
        scenario.ajouter_annulation(pid_a_annuler, jour_notification=2)
        scenario.ajouter_urgence("URG_VITAL", "Cardio", 75, 1, jour_apparition=2, delai_max_jours=0)
        scenario.ajouter_indisponibilite_lits(2, 3, lits_perdus=5)
        scenario.ajouter_retard_bloc(1, 40)

        adap_res = al.adapter_planning(
            self.prob,
            self.sol_init,
            scenario,
            jour_courant=2,
            n_iter=150,
            seed=7,
        )

        prob_adap = adap_res.problem_adapte
        sol_adap = adap_res.solution_adaptee

        # 1. Le patient annule ne doit plus etre present
        self.assertNotIn(pid_a_annuler, prob_adap.patients["patient_id"].values)
        self.assertIn(pid_a_annuler, adap_res.annulations_appliquees)

        # 2. L'urgence doit etre presente et affectee
        self.assertIn("URG_VITAL", prob_adap.patients["patient_id"].values)
        urg_idx = prob_adap.patients.index[prob_adap.patients["patient_id"] == "URG_VITAL"][0]
        self.assertIn(urg_idx, sol_adap)
        urg_vac = sol_adap[urg_idx]
        self.assertEqual(prob_adap._vac_day[urg_vac], 2)  # delai_max = 0 donc jour 2

        # 3. Le rapport est genere
        self.assertIn("RAPPORT D'ADAPTATION DYNAMIQUE", adap_res.rapport)
        self.assertIn("URG_VITAL", adap_res.rapport)

    def test_penalite_stabilite_contient_les_deplacements(self):
        # Scenario sans contrainte forte : la stabilite doit eviter les deplacements inutiles
        scenario = al.ScenarioAleas(nom="Scenario calme")
        adap_res = al.adapter_planning(
            self.prob,
            self.sol_init,
            scenario,
            jour_courant=1,
            w_perturbation=10.0,
            n_iter=100,
            seed=0,
        )
        self.assertEqual(adap_res.perturbation_count, 0)


class TestPlottingAleas(unittest.TestCase):
    def test_plot_adaptation_et_alternatives_sans_erreur(self):
        patients, vacations = op.generate_test_data(n_patients=12, n_days=3, seed=3)
        prob = op.PlanningProblem(patients, vacations, lits_capacity=15)
        sol = prob.random_solution()

        # Plannings alternatifs plot
        alts = al.generer_plannings_alternatifs(prob, solution_nominale=sol, metaheuristic_kwargs={"n_iter": 30})
        fig_alt = pl.plot_comparaison_alternatives(alts)
        self.assertIsNotNone(fig_alt)

        # Adaptation plot
        sc = al.generer_scenario_aleas(prob, sol, jour_courant=1, n_urgences=1, n_annulations=1, seed=0)
        adap_res = al.adapter_planning(prob, sol, sc, jour_courant=1, n_iter=40, seed=0)
        fig_adap = pl.plot_adaptation_dynamique(adap_res)
        self.assertIsNotNone(fig_adap)

        # Lits avec aleas plot
        fig_lits = pl.plot_occupation_lits_aleas(prob, sol, indisponibilites=sc.indisponibilites_lits)
        self.assertIsNotNone(fig_lits)
