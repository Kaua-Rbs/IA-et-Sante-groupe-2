# Optimiseur de planning de bloc opératoire métaheuristiques

Programme Python qui prend en entrée deux tables **pandas** (patients, vacations)
et renvoie un planning optimisé (affectation patient → vacation) calculé par
cinq métaheuristiques : **recuit simulé**, **recherche Tabou**,
**algorithme génétique**, **hybride Tabou × Recuit** et **colonie de fourmis
(ACO)**. Fournit un jeu de données de test, des graphiques de vitesse/qualité
de convergence, une interface graphique (Tkinter) et un pont depuis les
données réelles prétraitées par le notebook EDA.

## Fichiers

| Fichier | Rôle |
|---|---|
| `optimiseur/optimizer.py` | Cœur : génération de données de test, modèle du problème (`PlanningProblem`), fonction de qualité, les 5 métaheuristiques, validation par force brute |
| `optimiseur/plotting.py` | Graphiques matplotlib : convergence, comparaison qualité/temps, planning obtenu, occupation des lits |
| `optimiseur/run_demo.py` | Démonstration en ligne de commande (sans GUI) : génère les données, lance les méthodes, sauvegarde tous les graphiques en PNG |
| `optimiseur/app_gui.py` | Interface graphique Tkinter, visuelle et interactive |
| `optimiseur/data_bridge.py` | Convertit le Parquet prétraité par le notebook EDA au schéma de l'optimiseur |
| `EDA_donees_bloc.ipynb` | Prétraitement du classeur réel (source de vérité, ne pas modifier) |
| `notebooks/guide_optimisation.ipynb` | Guide pas à pas : des données EDA aux 5 métaheuristiques |

## Structure du dépôt

```text
optimiseur/               # package : tout le code
  optimizer.py  plotting.py  data_bridge.py  run_demo.py  app_gui.py
notebooks/
  guide_optimisation.ipynb
EDA_donees_bloc.ipynb     # prétraitement (racine- dépendances)
tests/                    # suite unittest
TEST_PLAN.md              # plan de tests détaillé
resources/                # classeur réel + Parquet EDA (non versionné)
resultats/                # sorties générées : CSV + PNG (non versionné)
.opencode/skill/          # skills OpenCode auto-chargés
```

## Tests

```bash
.venv/bin/python -m unittest discover -t . -s tests -v
```

44 tests (stdlib `unittest`, ~10 s, sans affichage) : modèle et fonction de
coût, les 5 métaheuristiques (qui doivent atteindre l'optimum exact sur la
petite instance), pont de données, graphiques, CLI `optimiseur.run_demo` et
intégrité des notebooks. Les tests nécessitant le Parquet EDA réel ou tkinter
sont sautés automatiquement si la ressource est absente. Détail : `TEST_PLAN.md`.

## Installation

Le Python système est 3.14 et `ensurepip` / `python3-venv` peuvent être absents.
Créer l'environnement avec `virtualenv` puis installer les dépendances :

```bash
python3 -m virtualenv .venv          # PAS python3 -m venv
.venv/bin/pip install -r requirements.txt
```

Toujours utiliser `.venv/bin/python` (versions de fait : pandas 3.0, numpy 2.5,
matplotlib 3.11, pyarrow 25).

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

## Utilisation avec l'interface graphique

```bash
.venv/bin/python -m optimiseur.app_gui
```

- **Générer des données de test** : crée un jeu de patients/vacations aléatoire selon les paramètres (nombre de patients, jours, capacité en lits).
- **Charger données réelles (EDA)** : charge `resources/donnees_bloc_pretraitees.parquet` (produit par le notebook EDA) via `data_bridge.prepare_inputs`. Le champ « Jours » sert alors d'horizon (les N derniers jours d'intervention). Le classeur `.xlsx` n'est jamais lu directement : il doit d'abord être prétraité par le notebook.
- **Charger CSV patients / vacations** : pour utiliser vos propres données (colonnes requises listées ci-dessous).
- **Lancer l'optimisation** : exécute les cinq métaheuristiques (dans un thread séparé, l'interface reste réactive), puis affiche :
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
7 patients). C'est la seule taille où un calcul exact reste possible : au-delà,
le nombre de combinaisons explose, ce qui est précisément la raison d'être des
métaheuristiques. `run_demo` affiche automatiquement cette vérification.

## Limites connues / pistes d'amélioration

- Le modèle simplifie la compatibilité chirurgien-vacation (une vacation est
  liée à une spécialité, pas à un chirurgien précis).
- Les paramètres par défaut (nombre d'itérations, taille de population, etc.)
  sont réglés pour un jeu de ~30 patients en quelques secondes ; à augmenter
  pour de plus gros volumes ou une meilleure qualité de convergence.
- Le graphique de planning peut devenir dense au-delà d'une trentaine de
  vacations — envisager une vue filtrée par jour pour de gros volumes.
