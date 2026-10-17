"""
multiagent.py
-------------
Systemes multi-agents (SMA) Mesa pour le planning de bloc operatoire.

Deux modeles construits sur les memes briques (tableau noir, coordinateur,
agents-chercheurs) :

- ``systeme_multiagent`` : agents simples (glouton, descente, aleatoire)
  qui cooperent via un tableau noir et un coordinateur de migration ;
- ``systeme_multiagent_hybride`` : chaque agent encapsule une
  metaheuristique (recuit, tabou, genetique, fourmis, tabou x recuit) et
  reprend periodiquement le meilleur commun.

Le coordinateur gere la migration du meilleur planning vers les agents les
moins performants et declenche des redemarrages partiels en cas de
stagnation. La sortie est un ``RunResult`` compatible avec le reste du
package (plotting, benchmark, GUI).

Determinisme : chaque agent possede son propre ``random.Random`` seme depuis
la graine du modele ; l'ordre d'activation est l'ordre de creation. Mesa
n'est utilise que pour le modele et le registre d'agents, pas pour le tirage
aleatoire.
"""

from __future__ import annotations

import random
import time

import mesa
import numpy as np

from .optimizer import (
    METHODE_SMA,
    METHODE_SMA_HYBRIDE,
    PlanningProblem,
    RunResult,
    Solution,
    _budget_atteint,
    _finalize,
    ant_colony_optimization,
    genetic_algorithm,
    simulated_annealing,
    tabu_search,
    tabu_simulated_annealing,
)


# --------------------------------------------------------------------------
# 1. Tableau noir : memoire partagee des agents
# --------------------------------------------------------------------------

class TableauNoir:
    """Meilleure solution connue, publiee par les agents au fil des etapes."""

    def __init__(self, probleme: PlanningProblem):
        self.probleme = probleme
        self.meilleure_solution: Solution | None = None
        self.meilleure_fitness: float = -np.inf
        self.version: int = 0
        self.nb_publications: int = 0

    def publier(self, solution: Solution, fitness: float) -> bool:
        """Enregistre ``solution`` si elle ameliore le meilleur connu."""
        if self.meilleure_solution is None or fitness > self.meilleure_fitness + 1e-12:
            self.meilleure_solution = dict(solution)
            self.meilleure_fitness = float(fitness)
            self.version += 1
            self.nb_publications += 1
            return True
        return False

    def lire(self) -> Solution | None:
        if self.meilleure_solution is None:
            return None
        return dict(self.meilleure_solution)


# --------------------------------------------------------------------------
# 2. Coordinateur : migration et redemarrages
# --------------------------------------------------------------------------

class Coordinateur:
    """Pilote la cooperation : migration du meilleur, redemarrage partiel
    des agents les plus faibles quand plus aucune amelioration n'apparait."""

    def __init__(
        self,
        intervalle_migration: int = 5,
        stagnation_max: int = 15,
        fraction_redemarrage: float = 0.5,
    ):
        self.intervalle_migration = max(1, intervalle_migration)
        self.stagnation_max = max(1, stagnation_max)
        self.fraction_redemarrage = min(max(fraction_redemarrage, 0.0), 1.0)
        self.derniere_version = 0
        self.etapes_stagnation = 0
        self.nb_migrations = 0
        self.nb_redemarrages = 0

    def etape(self, agents, tableau_noir: TableauNoir, probleme, rng, etape: int) -> None:
        if tableau_noir.version > self.derniere_version:
            self.derniere_version = tableau_noir.version
            self.etapes_stagnation = 0
        else:
            self.etapes_stagnation += 1

        meilleure = tableau_noir.lire()
        if meilleure is None:
            return

        if self.etapes_stagnation >= self.stagnation_max:
            # redemarrage partiel : les agents les plus faibles repartent
            tries = sorted(agents, key=lambda a: a.fitness)
            n = max(1, int(round(len(tries) * self.fraction_redemarrage)))
            for agent in tries[:n]:
                agent.repartir(probleme.random_solution(rng))
            self.nb_redemarrages += 1
            self.etapes_stagnation = 0
            return

        if etape > 0 and etape % self.intervalle_migration == 0:
            moyenne = float(np.mean([a.fitness for a in agents]))
            for agent in agents:
                if agent.fitness < moyenne:
                    agent.migrer(meilleure)
            self.nb_migrations += 1


# --------------------------------------------------------------------------
# 3. Agents-chercheurs
# --------------------------------------------------------------------------

class AgentChercheur(mesa.Agent):
    """Agent de base : detient une solution courante et publie ses
    ameliorations au tableau noir."""

    nom = "chercheur"

    def __init__(self, model: mesa.Model, probleme: PlanningProblem, seed: int):
        super().__init__(model)  # enregistrement automatique dans model.agents
        self.probleme = probleme
        self.alea = random.Random(seed)
        self.solution = probleme.random_solution(self.alea)
        self.fitness = probleme.fitness(self.solution)

    # -- API utilisee par le modele et le coordinateur --------------------
    def etape(self) -> None:
        raise NotImplementedError

    def publier(self) -> None:
        self.model.tableau_noir.publier(self.solution, self.fitness)

    def migrer(self, solution: Solution) -> None:
        """Adopte une solution imposee par le coordinateur."""
        self.solution = dict(solution)
        self.fitness = self.probleme.fitness(self.solution)

    def repartir(self, solution: Solution | None = None) -> None:
        """Redemarre depuis une solution aleatoire (ou imposee)."""
        if solution is None:
            solution = self.probleme.random_solution(self.alea)
        self.solution = dict(solution)
        self.fitness = self.probleme.fitness(self.solution)

    def _adopter(self, resultat: RunResult) -> None:
        if resultat.meilleure_fitness > self.fitness:
            self.solution = dict(resultat.meilleure_solution)
            self.fitness = resultat.meilleure_fitness


class AgentGlouton(AgentChercheur):
    """Construit un planning glouton (patients tries par duree decroissante,
    vacation la moins chargee) et le conserve s'il est meilleur."""

    nom = "glouton"

    def etape(self) -> None:
        ordre = list(range(self.probleme.n_patients))
        self.alea.shuffle(ordre)
        charge = np.zeros(self.probleme.n_vacations)
        sol: Solution = {}
        for pid in ordre:
            options = self.probleme._options_for(pid)
            duree = self.probleme._pat_duree[pid]
            choix = int(options[int(np.argmin(charge[options] + duree))])
            sol[pid] = choix
            charge[choix] += duree
        f = self.probleme.fitness(sol)
        if f > self.fitness:
            self.solution, self.fitness = sol, f
        self.publier()


class AgentDescente(AgentChercheur):
    """Descente stochastique : teste quelques voisins, garde le meilleur ;
    redemarre localement si aucun voisin n'ameliore la solution."""

    nom = "descente"

    def __init__(self, model, probleme, seed, voisins: int = 12):
        super().__init__(model, probleme, seed)
        self.voisins = voisins

    def etape(self) -> None:
        meilleur, meilleure_f = self.solution, self.fitness
        for _ in range(self.voisins):
            voisin, _ = self.probleme.neighbor(self.solution, self.alea)
            f = self.probleme.fitness(voisin)
            if f > meilleure_f:
                meilleur, meilleure_f = voisin, f
        if meilleure_f > self.fitness:
            self.solution, self.fitness = meilleur, meilleure_f
        else:
            self.repartir()
        self.publier()


class AgentAleatoire(AgentChercheur):
    """Exploration pure : tire des plannings aleatoires et publie les
    ameliorations accidentelles."""

    nom = "aleatoire"

    def etape(self) -> None:
        sol = self.probleme.random_solution(self.alea)
        f = self.probleme.fitness(sol)
        if f > self.fitness:
            self.solution, self.fitness = sol, f
        self.publier()


class AgentMetaheuristique(AgentChercheur):
    """Agent generique encapsulant une metaheuristique par quantum."""

    nom = "metaheuristique"

    def __init__(self, model, probleme, seed, quantum: int = 30):
        super().__init__(model, probleme, seed)
        self.quantum = quantum


class AgentRecuit(AgentMetaheuristique):
    nom = "recuit"

    def __init__(self, model, probleme, seed, quantum: int = 150, T0: float = 50.0, alpha: float = 0.95):
        super().__init__(model, probleme, seed, quantum)
        self.T0 = T0
        self.alpha = alpha

    def etape(self) -> None:
        resultat = simulated_annealing(
            self.probleme,
            T0=self.T0,
            alpha=self.alpha,
            n_iter=self.quantum,
            seed=self.alea.randrange(2**32),
            solution_initiale=self.solution,
        )
        self._adopter(resultat)
        self.publier()


class AgentTabou(AgentMetaheuristique):
    nom = "tabou"

    def __init__(
        self,
        model,
        probleme,
        seed,
        quantum: int = 40,
        tabu_size: int = 20,
        neighborhood_size: int = 8,
    ):
        super().__init__(model, probleme, seed, quantum)
        self.tabu_size = tabu_size
        self.neighborhood_size = neighborhood_size

    def etape(self) -> None:
        resultat = tabu_search(
            self.probleme,
            n_iter=self.quantum,
            tabu_size=self.tabu_size,
            neighborhood_size=self.neighborhood_size,
            seed=self.alea.randrange(2**32),
            solution_initiale=self.solution,
        )
        self._adopter(resultat)
        self.publier()


class AgentGenetique(AgentMetaheuristique):
    nom = "genetique"

    def __init__(
        self,
        model,
        probleme,
        seed,
        quantum: int = 10,
        taille_population: int = 12,
        p_cross: float = 0.8,
        p_mut: float = 0.12,
    ):
        super().__init__(model, probleme, seed, quantum)
        self.taille_population = taille_population
        self.p_cross = p_cross
        self.p_mut = p_mut
        self.population: list[Solution] | None = None

    def etape(self) -> None:
        etat: dict = {}
        resultat = genetic_algorithm(
            self.probleme,
            pop_size=self.taille_population,
            n_gen=self.quantum,
            p_cross=self.p_cross,
            p_mut=self.p_mut,
            seed=self.alea.randrange(2**32),
            population_initiale=self.population,
            etat=etat,
        )
        self.population = etat["population"]
        self._adopter(resultat)
        self.publier()

    def migrer(self, solution: Solution) -> None:
        """Adopte la solution migree et l'injecte dans la population a la
        place du pire individu, pour qu'elle soit exploitee au quantum suivant."""
        super().migrer(solution)
        if self.population:
            pire = min(range(len(self.population)), key=lambda i: self.probleme.fitness(self.population[i]))
            self.population[pire] = dict(solution)

    def repartir(self, solution: Solution | None = None) -> None:
        """Redemarre : la population est reconstruite au prochain quantum."""
        super().repartir(solution)
        self.population = None


class AgentFourmis(AgentMetaheuristique):
    nom = "fourmis"

    def __init__(
        self,
        model,
        probleme,
        seed,
        quantum: int = 5,
        n_ants: int = 8,
        rho: float = 0.3,
    ):
        super().__init__(model, probleme, seed, quantum)
        self.n_ants = n_ants
        self.rho = rho
        self.pheromones: np.ndarray | None = None

    def etape(self) -> None:
        etat: dict = {}
        resultat = ant_colony_optimization(
            self.probleme,
            n_ants=self.n_ants,
            n_iter=self.quantum,
            rho=self.rho,
            seed=self.alea.randrange(2**32),
            pheromones_initiaux=self.pheromones,
            meilleure_solution_initiale=self.solution,
            etat=etat,
        )
        self.pheromones = etat["pheromones"]
        self._adopter(resultat)
        self.publier()

    def repartir(self, solution: Solution | None = None) -> None:
        """Redemarre : les pheromones sont oubliees au prochain quantum."""
        super().repartir(solution)
        self.pheromones = None


class AgentHybride(AgentMetaheuristique):
    nom = "hybride"

    def __init__(
        self,
        model,
        probleme,
        seed,
        quantum: int = 60,
        neighborhood_size: int = 8,
    ):
        super().__init__(model, probleme, seed, quantum)
        self.neighborhood_size = neighborhood_size

    def etape(self) -> None:
        resultat = tabu_simulated_annealing(
            self.probleme,
            n_iter=self.quantum,
            neighborhood_size=self.neighborhood_size,
            seed=self.alea.randrange(2**32),
            solution_initiale=self.solution,
        )
        self._adopter(resultat)
        self.publier()


AGENTS_SIMPLES = (AgentGlouton, AgentDescente, AgentAleatoire)
AGENTS_METAHEURISTIQUES = (AgentRecuit, AgentTabou, AgentGenetique, AgentFourmis, AgentHybride)
PARAMS_AGENTS_DEFAUT = {
    AgentGlouton: {},
    AgentDescente: {"voisins": 12},
    AgentAleatoire: {},
    AgentRecuit: {"quantum": 150, "T0": 50.0, "alpha": 0.95},
    AgentTabou: {"quantum": 40, "tabu_size": 20, "neighborhood_size": 8},
    AgentGenetique: {"quantum": 10, "taille_population": 12, "p_cross": 0.8, "p_mut": 0.12},
    AgentFourmis: {"quantum": 5, "n_ants": 8, "rho": 0.3},
    AgentHybride: {"quantum": 60, "neighborhood_size": 8},
}


# --------------------------------------------------------------------------
# 4. Modeles Mesa
# --------------------------------------------------------------------------

class ModeleSMA(mesa.Model):
    """Modele Mesa generique : ``types_agents`` est cycle pour creer
    ``n_agents`` chercheurs, tous coordonnes par le meme tableau noir."""

    def __init__(
        self,
        probleme: PlanningProblem,
        types_agents,
        seed: int = 0,
        n_agents: int = 6,
        params_agents: dict | None = None,
        intervalle_migration: int = 5,
        stagnation_max: int = 15,
        fraction_redemarrage: float = 0.5,
    ):
        super().__init__(rng=seed)
        self.probleme = probleme
        self.tableau_noir = TableauNoir(probleme)

        params = dict(PARAMS_AGENTS_DEFAUT)
        if params_agents:
            for classe, valeurs in params_agents.items():
                params[classe] = {**params.get(classe, {}), **valeurs}

        graines = random.Random(seed ^ 0x5EED)
        self.agents_chercheurs: list[AgentChercheur] = []
        for i in range(n_agents):
            classe = types_agents[i % len(types_agents)]
            agent = classe(self, probleme, graines.randrange(2**32), **params.get(classe, {}))
            agent.publier()
            self.agents_chercheurs.append(agent)

        self.rng_coordination = random.Random(seed ^ 0xC00D)
        self.coordinateur = Coordinateur(
            intervalle_migration=intervalle_migration,
            stagnation_max=stagnation_max,
            fraction_redemarrage=fraction_redemarrage,
        )
        self.nb_etapes = 0

    def step(self) -> None:
        """Une etape : chaque agent cherche, puis le coordinateur intervient."""
        self.nb_etapes += 1
        for agent in sorted(self.agents_chercheurs, key=lambda a: a.unique_id):
            agent.etape()
            agent.publier()
        self.coordinateur.etape(
            self.agents_chercheurs, self.tableau_noir, self.probleme, self.rng_coordination, self.nb_etapes
        )


# --------------------------------------------------------------------------
# 5. API haut niveau, alignee sur les autres methodes
# --------------------------------------------------------------------------

def _executer_sma(modele: ModeleSMA, nom: str, n_steps: int, time_budget_s: float | None) -> RunResult:
    rows: list[tuple] = []
    t0 = time.perf_counter()
    nb_steps = 0
    best_f = modele.tableau_noir.meilleure_fitness
    for k in range(n_steps):
        nb_steps = k + 1
        modele.step()
        best_f = modele.tableau_noir.meilleure_fitness
        rows.append((k, time.perf_counter() - t0, best_f, best_f))
        if _budget_atteint(t0, time_budget_s):
            break
    return _finalize(
        nom, modele.tableau_noir.meilleure_solution, best_f, rows, t0, best_f, nb_steps
    )


def systeme_multiagent(
    problem: PlanningProblem,
    n_agents: int = 6,
    n_steps: int = 60,
    intervalle_migration: int = 5,
    stagnation_max: int = 15,
    fraction_redemarrage: float = 0.5,
    params_agents: dict | None = None,
    seed: int = 0,
    time_budget_s: float | None = None,
) -> RunResult:
    """SMA d'agents simples (glouton, descente, aleatoire) cooperant par
    tableau noir et migrations."""
    modele = ModeleSMA(
        problem,
        AGENTS_SIMPLES,
        seed=seed,
        n_agents=n_agents,
        params_agents=params_agents,
        intervalle_migration=intervalle_migration,
        stagnation_max=stagnation_max,
        fraction_redemarrage=fraction_redemarrage,
    )
    return _executer_sma(modele, METHODE_SMA, n_steps, time_budget_s)


def systeme_multiagent_hybride(
    problem: PlanningProblem,
    n_agents: int = 5,
    n_steps: int = 40,
    intervalle_migration: int = 4,
    stagnation_max: int = 12,
    fraction_redemarrage: float = 0.5,
    params_agents: dict | None = None,
    seed: int = 0,
    time_budget_s: float | None = None,
) -> RunResult:
    """SMA hybride : agents metaheuristiques (recuit, tabou, genetique,
    fourmis, tabou x recuit) cooperant par tableau noir."""
    modele = ModeleSMA(
        problem,
        AGENTS_METAHEURISTIQUES,
        seed=seed,
        n_agents=n_agents,
        params_agents=params_agents,
        intervalle_migration=intervalle_migration,
        stagnation_max=stagnation_max,
        fraction_redemarrage=fraction_redemarrage,
    )
    return _executer_sma(modele, METHODE_SMA_HYBRIDE, n_steps, time_budget_s)
