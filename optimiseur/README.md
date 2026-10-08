# Optimiseur de planning de bloc opératoire métaheuristiques

Programme Python qui prend en entrée deux tables **pandas** (patients, vacations)
et renvoie un planning optimisé (affectation patient → vacation) calculé par
**dix méthodes** : **recuit simulé**, **recherche Tabou**, **algorithme
génétique**, **hybride Tabou × Recuit**, **colonie de fourmis (ACO)**,
**Génétique × Tabou**, **Génétique × Recuit**, **Fourmis × Tabou**, et deux
**systèmes multi-agents Mesa** (SMA d'agents simples, SMA × métaheuristiques).
Fournit un jeu de données de test, des graphiques de vitesse/qualité de
convergence, un harnais de benchmark multi-graines, un pont de re-planification
dynamique vers `hospital_sim`, une interface graphique (Tkinter) et un pont
depuis les données réelles prétraitées par le notebook EDA.

## Fichiers

| Fichier | Rôle |
|---|---|
| `optimiseur/optimizer.py` | Cœur : génération de données de test, modèle du problème (`PlanningProblem`), fonction de qualité, les 8 métaheuristiques, hooks de reprise (`solution_initiale`, `population_initiale`, `pheromones_initiaux`), budget temps, validation par force brute |
| `optimiseur/aleas.py` | Système d'aléas (urgences, annulations, indisponibilité lits, retard bloc), génération de plannings alternatifs (Date A / Date B, robustesse) et adaptation dynamique |
| `optimiseur/multiagent.py` | SMA Mesa : tableau noir, coordinateur (migration/redémarrages), agents simples et agents métaheuristiques |
| `optimiseur/coordination_bridge.py` | Pont asynchrone vers `hospital_sim` : adaptateur d'état, scheduler, validateur |
| `optimiseur/benchmark.py` | Campagnes multi-graines (petite et grande échelle), agrégats et rangs |
| `optimiseur/plotting.py` | Graphiques matplotlib : convergence, comparaison qualité/temps, planning, lits, adaptation dynamique, comparaison des alternatives, boxplots et convergence médiane multi-graines |
| `optimiseur/run_demo.py` | Démonstration en ligne de commande (sans GUI) : génère les données, lance les méthodes, sauvegarde tous les graphiques en PNG |
| `optimiseur/run_benchmark.py` | CLI de la campagne comparative (CSV + figures + métadonnées JSON) |
| `optimiseur/run_coordination_demo.py` | Démonstration de re-planification dynamique via `hospital_sim` |
| `optimiseur/app_gui.py` | Interface graphique Tkinter, visuelle et interactive (avec onglets Plannings alternatifs et Aléas & Adaptation) |
| `optimiseur/data_bridge.py` | Convertit le Parquet prétraité par le notebook EDA au schéma de l'optimiseur |
| `EDA_donees_bloc.ipynb` | Prétraitement du classeur réel (source de vérité, ne pas modifier) |
| `notebooks/guide_optimisation.ipynb` | Guide pas à pas : des données EDA aux 5 métaheuristiques historiques |

## Structure du dépôt

```text
optimiseur/               # package : tout le code
  optimizer.py  aleas.py  plotting.py  data_bridge.py  run_demo.py  app_gui.py
  multiagent.py  coordination_bridge.py  benchmark.py  run_benchmark.py
  run_coordination_demo.py
hospital_sim/             # coordinateur et simulation Mesa de salles
notebooks/
  guide_optimisation.ipynb
EDA_donees_bloc.ipynb     # prétraitement (racine- dépendances)
tests/                    # suite unittest
TEST_PLAN.md              # plan de tests détaillé
resources/                # classeur réel + Parquet EDA (non versionné)
resultats/                # sorties générées : CSV + PNG (non versionné)
rapport/                  # rapport comparatif + figures versionnées
```

## Tests

```bash
venv/bin/python -m unittest discover -t . -s tests -v
```

La suite `unittest` couvre les dix méthodes de planification de vacations,
les aléas, le pont de coordination et la simulation historique de salles.
Les tests nécessitant le Parquet EDA réel ou tkinter sont sautés si la
ressource est absente. Détail : `TEST_PLAN.md`.

## Installation

Python 3.12 ou plus récent est requis pour le dépôt assemblé avec Mesa 3.5.1.
Utiliser l'environnement existant (ici `venv/bin/python`) ou créer un environnement
avec `python3 -m venv .venv`, puis installer `requirements.txt`.

Tkinter est fourni avec la plupart des distributions Python (Windows, macOS).
Ici `python3-tk` est installé au niveau système ; si `import tkinter` échoue :

```bash
sudo apt install python3-tk
```

## Utilisation rapide (sans GUI)

```bash
.venv/bin/python -m optimiseur.run_demo --n-patients 30 --n-days 5 --out resultats
```

Génère `resultats/patients_test.csv`, `vacations_test.csv`, les 4 graphiques
PNG (convergence, comparaison, planning, occupation des lits), le planning
détaillé de la meilleure méthode en CSV, et affiche dans la console la
vérification d'optimalité sur une petite instance (comparaison à l'optimum
exact par force brute).

Pour lancer les **10 méthodes** (hybrides et SMA compris), avec un budget
temps par méthode :

```bash
.venv/bin/python -m optimiseur.run_demo --toutes --budget 2 --out resultats
```

## Benchmark comparatif

```bash
# campagne complete : 10 methodes x 20 graines, petite puis grande echelle
.venv/bin/python -m optimiseur.run_benchmark

# campagne courte pour verifier le harnais
.venv/bin/python -m optimiseur.run_benchmark --graines 3 --budget-petite 0.2 --budget-grande 0.5 \
    --n-patients 80 --n-days 8 --out /tmp/bench --figures /tmp/fig

# campagne sur les donnees reelles (Parquet EDA) au lieu du synthetique
.venv/bin/python -m optimiseur.run_benchmark --donnees-reelles --graines 20 \
    --budget-grande 4 --horizon 40 --capacite-min 600 \
    --out resultats/benchmark_reel --figures rapport/figures
```

Écrit les CSV bruts/agrégés dans `resultats/benchmark/`, les figures dans
`rapport/figures/` et un `benchmark_meta.json` (paramètres + références).
Protocole : budget temps identique pour toutes les méthodes (0,5 s petite
échelle, 3 s grande échelle par défaut), plafonds d'itération très élevés pour
que le budget soit le seul frein, même graine par méthode à chaque répétition.
Avec `--donnees-reelles`, la campagne grande échelle est remplacée par le
Parquet EDA prétraité (`--horizon` jours, `--capacite-min` par vacation).
Le rapport comparatif est dans `rapport/RAPPORT.md`.

## Re-planification dynamique (hospital_sim)

```bash
.venv/bin/python -m optimiseur.run_coordination_demo --n-patients 25 --n-days 4 --budget 1
```

Le `Coordinator` asynchrone de `hospital_sim` reçoit des événements
(indisponibilité de vacation, arrivée en urgence…), `PlanificateurOptimiseur`
tourne dans un thread et `ValidateurBloc` vérifie la faisabilité avant
acceptation explicite.

## Utilisation avec l'interface graphique

```bash
.venv/bin/python -m optimiseur.app_gui
```

- **Générer des données de test** : crée un jeu de patients/vacations aléatoire selon les paramètres (nombre de patients, jours, capacité en lits).
- **Charger données réelles (EDA)** : charge `resources/donnees_bloc_pretraitees.parquet` (produit par le notebook EDA) via `data_bridge.prepare_inputs`. Le champ « Jours » sert alors d'horizon (les N derniers jours d'intervention). Le classeur `.xlsx` n'est jamais lu directement : il doit d'abord être prétraité par le notebook.
- **Charger CSV patients / vacations** : pour utiliser vos propres données (colonnes requises listées ci-dessous).
- **Lancer l'optimisation** : exécute les dix méthodes (dans un thread séparé, l'interface reste réactive), puis affiche :
  - **Convergence** : qualité du meilleur planning trouvé en fonction du temps écoulé.
  - **Comparaison** : qualité finale et temps de calcul total, en barres.
  - **Planning** : diagramme en barres empilées de la charge de chaque vacation (méthode gagnante).
  - **Lits** : occupation des lits jour par jour vs capacité.
  - **Tableau du planning** : affectation détaillée patient → vacation, au choix pour chaque méthode.

## Utiliser les données réelles

Le notebook `EDA_donees_bloc.ipynb` nettoie le classeur source et exporte
`resources/donnees_bloc_pretraitees.parquet` (1 ligne = 1 intervention).
`optimiseur.data_bridge.prepare_inputs` convertit ensuite ce Parquet en tables
`patients` / `vacations` au format attendu par l'optimiseur :

```python
from optimiseur import data_bridge as db
patients, vacations, contexte = db.prepare_inputs(
    "resources/donnees_bloc_pretraitees.parquet", horizon_jours=5, capacite_min=480
)
```

La spécialité est un **proxy** dérivé de `ccam_1` / `ghm_code` / `interv_type`,
à valider cliniquement. Les identifiants patients/praticiens sont écartés.
Le guide `notebooks/guide_optimisation.ipynb` déroule ce pipeline pas à pas.

## Format des données d'entrée

**Table patients** (colonnes requises) :
| colonne | type | description |
|---|---|---|
| `patient_id` | int | identifiant (généré automatiquement si absent) |
| `specialite` | str | spécialité chirurgicale du patient |
| `duree_operatoire` | int | durée prévue de l'intervention (minutes) |
| `duree_sejour` | int | durée d'hospitalisation post-opératoire (jours) |

**Table vacations** (colonnes requises) :
| colonne | type | description |
|---|---|---|
| `vacation_id` | int | identifiant (généré automatiquement si absent) |
| `jour` | int | jour du planning (0, 1, 2, ...) |
| `specialite` | str | spécialité à laquelle la vacation est dédiée |
| `capacite_min` | int | capacité de la vacation en minutes (240 = 4h) |

## Les méthodes

| Méthode | Principe |
|---|---|
| Recuit simulé | accepte une dégradation avec la probabilité `exp(delta/T)`, `T` décroissante |
| Tabou | meilleur voisin non tabou, mémoire des derniers mouvements |
| Génétique | population, sélection, croisement, mutation, élitisme |
| Tabou × Recuit | voisinage filtré par la liste taboue + acceptation type recuit |
| Fourmis (ACO) | construction par phéromones `tau^alpha * eta^beta`, évaporation + dépôt |
| Génétique × Tabou | mémetique : recherche tabou sur le meilleur individu de chaque génération |
| Génétique × Recuit | mémetique : recuit simulé court sur le meilleur individu de chaque génération |
| Fourmis × Tabou | chaque itération ACO intensifie sa meilleure fourmi par recherche tabou |
| SMA | agents simples (glouton, descente, aléatoire) + tableau noir + migrations/redémarrages |
| SMA × Métaheuristiques | agents recuit/tabou/génétique/fourmis/hybride coopérant par tableau noir |

## Systèmes multi-agents (Mesa)

`optimiseur/multiagent.py` construit les deux SMA sur `mesa.Model` /
`mesa.Agent` :

- **Tableau noir** : mémoire partagée de la meilleure solution, versionnée ;
- **Coordinateur** : migration du meilleur vers les agents sous la moyenne,
  redémarrage partiel des plus faibles en cas de stagnation ;
- **Agents** : simples (`AgentGlouton`, `AgentDescente`, `AgentAleatoire`) ou
  métaheuristiques (`AgentRecuit`, `AgentTabou`, `AgentGenetique`,
  `AgentFourmis`, `AgentHybride`) qui reprennent leur état d'un quantum à
  l'autre via les hooks `solution_initiale` / `population_initiale` /
  `pheromones_initiaux`.

Le déterminisme est garanti par un `random.Random` propre à chaque agent ;
Mesa ne sert qu'au modèle et au registre d'agents. Comme les autres méthodes,
`systeme_multiagent` et `systeme_multiagent_hybride` acceptent
`time_budget_s`, et s'utilisent directement via `optimize_planning`.

## Fonction de qualité (ce que les métaheuristiques minimisent)

```
coût = w_vacation * dépassement_capacité_vacations
     + w_lits     * dépassement_capacité_lits
     + w_balance  * écart-type de la charge entre vacations
```
La fitness renvoyée est `-coût` (0 = planning parfaitement faisable et équilibré).
Les poids (`w_vacation`, `w_lits`, `w_balance`) sont réglables dans `PlanningProblem`.

## Validation de l'optimalité

`optimiseur.optimizer.exact_bruteforce()` calcule l'optimum exact par
énumération complète sur une petite instance (`small_validation_instance`,
7 patients et 2 vacations compatibles, soit 128 affectations). C'est une
petite taille où un calcul exact reste possible : au-delà,
le nombre de combinaisons explose, ce qui est précisément la raison d'être des
métaheuristiques. `run_demo` affiche automatiquement cette vérification, et
`notebooks` / le benchmark s'appuient dessus (taux d'optimum par méthode).

## Gestion des aléas & Plannings alternatifs (`optimiseur/aleas.py`)

Le bloc opératoire est soumis à une forte variabilité quotidienne. Le module `aleas.py` modélise et prend en charge quatre types d'aléas fondamentaux :

1. **Urgences** (`Urgence`) : nouveaux patients arrivant au fil de l'eau, avec spécialité, durée opératoire, durée de séjour, jour d'apparition et fenêtre temporelle autorisée (`delai_max_jours`).
2. **Annulations** (`Annulation`) : patients programmés qui annulent (contre-indication médicale, refus), libérant immédiatement du temps opératoire et des lits d'hospitalisation.
3. **Indisponibilité lits** (`IndisponibiliteLits`) : fermetures inopinées de lits (tensions RH, épidémie, maintenance) sur un intervalle de jours $[j_{\text{début}}, j_{\text{fin}}]$.
4. **Retard bloc** (`RetardBloc`) : prolongations imprévues ou incidents techniques amputant la capacité utile d'une vacation.

### Deux approches complémentaires :

- **Génération de plannings alternatifs proactive** (`generer_plannings_alternatifs`) :
  - **Nominal** : optimisation à pleine capacité.
  - **Robuste Bufferisé** : réserve de capacité bloc (buffer 15%) et lits pour absorber les imprévus sans décalage.
  - **Sécurité Lits** : forte pénalité et lissage pour prévenir les tensions d'hospitalisation.
  - **Alternatif Diversifié (Date B)** : fournit pour chaque patient une paire **Date A / Date B** via `extraire_options_date_a_b` pour guider le choix du praticien lors de la consultation préopératoire.

- **Adaptation dynamique réactive** (`adapter_planning`) :
  - **Gel temporel** : sanctuarisation des interventions passées ($j < j_{\text{courant}}$).
  - **Insertion prioritaire des urgences** dans leur fenêtre clinique ; une
    urgence sans vacation compatible dans sa fenêtre est refusée explicitement.
  - **Principe de moindre perturbation** : minimisation du nombre de patients futurs déplacés ($\min \text{perturbation}$ et pénalité accrue pour les changements de jour).
  - Production d'un rapport décisionnel complet (`rapport`) avec détail des arbitrages.

Les profils et adaptations sont des **propositions**. Le résultat expose les
dépassements de capacité bloc et lits ainsi qu'un indicateur de faisabilité ;
un profil alternatif peut rester infaisable.

## Limites connues / pistes d'amélioration

- Le modèle simplifie la compatibilité chirurgien-vacation (une vacation est
  liée à une spécialité, pas à un chirurgien précis).
- Les paramètres par défaut (nombre d'itérations, taille de population, etc.)
  sont réglés pour un jeu de ~30 patients en quelques secondes ; à augmenter
  pour de plus gros volumes ou une meilleure qualité de convergence. En
  benchmark, les plafonds d'itération sont volontairement très élevés et le
  budget temps est le seul frein.
- `time_budget_s` arrête les méthodes à la fin de l'itération courante : le
  dépassement reste de l'ordre du coût d'une itération.
- Le pont `hospital_sim` suppose un modèle simplifié (pas d'engagement fixe,
  pas de contrainte chirurgien) : `fixed_commitments` est un point d'extension.
- Le graphique de planning peut devenir dense au-delà d'une trentaine de
  vacations — envisager une vue filtrée par jour pour de gros volumes.

## Couplage Mesa

Le [guide de couplage](../docs/metaheuristics-mesa-assembly.md) décrit le modèle
de salles, son objectif distinct et les budgets communs. Les algorithmes acceptent
aussi `initial_solution` et un `SearchControl` optionnels; les appels historiques
conservent leur comportement.
Les trois nouveaux hybrides utilisent désormais le même décodeur de salles et
les mêmes limites d'évaluations que les cinq méthodes initiales. Les deux SMA
de ce module cherchent des affectations de vacations et ne simulent pas des
patients ni des lits. Voir le [guide des deux modèles](../docs/combined-optimization-simulation.md).
