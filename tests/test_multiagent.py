"""Tests des systemes multi-agents Mesa (SMA et SMA x metaheuristiques)."""

from __future__ import annotations

import unittest

from optimiseur import optimizer as op

try:
    from optimiseur import multiagent as ma

    MESA_DISPONIBLE = True
except ImportError:  # pragma: no cover - depend de l'environnement
    MESA_DISPONIBLE = False


@unittest.skipUnless(MESA_DISPONIBLE, "mesa n'est pas installe")
class TestSMAPetiteInstance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.patients, cls.vacations = op.small_validation_instance(seed=1)
        cls.prob = op.PlanningProblem(cls.patients, cls.vacations)
        _, cls.f_exact = op.exact_bruteforce(cls.prob)
        cls.sma = ma.systeme_multiagent(cls.prob, n_agents=4, n_steps=40, seed=0)
        cls.hybride = ma.systeme_multiagent_hybride(cls.prob, n_agents=4, n_steps=20, seed=0)

    def test_optimum_atteint(self):
        for nom, resultat in (
            (op.METHODE_SMA, self.sma),
            (op.METHODE_SMA_HYBRIDE, self.hybride),
        ):
            with self.subTest(methode=nom):
                self.assertAlmostEqual(resultat.meilleure_fitness, self.f_exact, places=6)

    def test_champs_run_result(self):
        for nom, resultat in (
            (op.METHODE_SMA, self.sma),
            (op.METHODE_SMA_HYBRIDE, self.hybride),
        ):
            with self.subTest(methode=nom):
                self.assertEqual(resultat.nom, nom)
                self.assertEqual(list(resultat.historique.columns), op.HISTORY_COLUMNS)
                self.assertGreater(len(resultat.historique), 0)
                self.assertAlmostEqual(
                    resultat.meilleure_fitness, resultat.historique["meilleure_fitness"].max(), places=9
                )

    def test_solution_valide(self):
        for resultat in (self.sma, self.hybride):
            self.assertEqual(set(resultat.meilleure_solution), set(range(self.prob.n_patients)))
            for pid, vac_idx in resultat.meilleure_solution.items():
                self.assertIn(vac_idx, self.prob._options_for(pid).tolist())

    def test_determinisme(self):
        a = ma.systeme_multiagent(self.prob, n_agents=4, n_steps=10, seed=7)
        b = ma.systeme_multiagent(self.prob, n_agents=4, n_steps=10, seed=7)
        self.assertEqual(a.meilleure_fitness, b.meilleure_fitness)
        self.assertEqual(a.meilleure_solution, b.meilleure_solution)

        c = ma.systeme_multiagent_hybride(self.prob, n_agents=4, n_steps=5, seed=7)
        d = ma.systeme_multiagent_hybride(self.prob, n_agents=4, n_steps=5, seed=7)
        self.assertEqual(c.meilleure_fitness, d.meilleure_fitness)
        self.assertEqual(c.meilleure_solution, d.meilleure_solution)


@unittest.skipUnless(MESA_DISPONIBLE, "mesa n'est pas installe")
class TestTableauNoirEtCoordinateur(unittest.TestCase):
    def _modele(self, **kwargs):
        patients, vacations = op.small_validation_instance(seed=1)
        probleme = op.PlanningProblem(patients, vacations)
        return ma.ModeleSMA(
            probleme,
            ma.AGENTS_SIMPLES,
            n_agents=3,
            seed=0,
            **kwargs,
        )

    def test_publication_initialise_le_tableau_noir(self):
        modele = self._modele()
        self.assertIsNotNone(modele.tableau_noir.meilleure_solution)
        self.assertGreater(modele.tableau_noir.nb_publications, 0)

    def test_publier_garde_le_meilleur(self):
        patients, vacations = op.small_validation_instance(seed=1)
        probleme = op.PlanningProblem(patients, vacations)
        tableau = ma.TableauNoir(probleme)
        solution = probleme.random_solution()
        fitness = probleme.fitness(solution)
        self.assertTrue(tableau.publier(solution, fitness))
        self.assertFalse(tableau.publier(solution, fitness - 1.0))
        self.assertEqual(tableau.version, 1)

    def test_coordinateur_migre(self):
        modele = self._modele(intervalle_migration=1)
        modele.step()
        self.assertGreater(modele.coordinateur.nb_migrations, 0)
        # apres migration, les agents sous la moyenne ont le meilleur commun
        meilleure = modele.tableau_noir.meilleure_fitness
        self.assertTrue(all(agent.fitness <= meilleure + 1e-9 for agent in modele.agents_chercheurs))

    def test_coordinateur_redemarre(self):
        modele = self._modele(stagnation_max=1)
        pourcentages = []
        for _ in range(3):
            modele.step()
            pourcentages.append(modele.coordinateur.nb_redemarrages)
        self.assertGreaterEqual(max(pourcentages), 1)


@unittest.skipUnless(MESA_DISPONIBLE, "mesa n'est pas installe")
class TestBudgetSMA(unittest.TestCase):
    def test_budget_respecte(self):
        patients, vacations = op.generate_test_data(n_patients=80, n_days=8, seed=5)
        probleme = op.PlanningProblem(patients, vacations)
        budget = 0.2
        resultat = ma.systeme_multiagent(probleme, n_steps=10**6, time_budget_s=budget)
        self.assertLessEqual(resultat.duree_s, budget + 0.5)


if __name__ == "__main__":
    unittest.main()
