# Tests

Le projet a trois suites :

| Suite | Code testé | Commande |
| :--- | :--- | :--- |
| Moteurs (ce dossier) | `prediction/`, `optimiseur/`, `hospital_sim/` | `python -m unittest discover -t . -s tests`, depuis la racine |
| API | `interface/api/` | `cd interface/api && just test` |
| Front | `interface/app/` | `cd interface/app && pnpm check` |

La CI ([`.github/workflows/ci.yaml`](../.github/workflows/ci.yaml)) lance les trois à chaque push. Aucune ne lit de donnée confidentielle : les tests utilisent des données synthétiques, et ceux qui auraient besoin d'un fichier de `resources/` s'ignorent s'il est absent.

## Lancer les tests des moteurs

Installer d'abord les dépendances de [`requirements.txt`](../requirements.txt) (Python 3.12 ou plus récent), puis, depuis la racine du dépôt :

```bash
python -m unittest discover -t . -s tests -v       # toute la suite
python -m unittest tests.test_optimizer -v          # un module
python -m unittest tests.test_optimizer.TestFitness # une classe
```

Toute régression doit se traduire par un test en échec, pas par une inspection manuelle.

## Ce qui est couvert

### Prédiction

- `test_surgery_duration.py` : découpage chronologique et disjoint par patient (patients répétés ou absents refusés, calibration postérieure à la sélection), références médianes apprises sur l'entraînement seul avec repli sur la médiane globale, catégories rares définies sur l'entraînement seul, calibration conforme, inférence sur données brutes, bornes P80/P95 ordonnées.
- `test_final_models.py` : variables « consultation » (liste blanche, aucune fuite des champs de sortie, valeurs manquantes), chargement des modèles de séjour à cible directe ou logarithmique, contrôle de la largeur d'intervalle, bornes P80/P95.

### Optimiseur de vacations

- `test_optimizer.py` : génération des données de test, modèle du problème (options compatibles avec la spécialité, voisins valides), fonction de coût vérifiée à la main, occupation des lits, optimum exact par énumération, **les métaheuristiques atteignent l'optimum exact** sur la petite instance, déterminisme par graine, conversion en tableau.
- `test_hybrides.py` : les trois hybrides atteignent l'optimum exact ; reprise depuis une solution, une population ou des phéromones ; budget de temps ; sélecteur de méthodes ; détection des dépassements.
- `test_multiagent.py` (ignoré sans Mesa) : les deux SMA atteignent l'optimum exact, déterminisme, tableau noir, migrations et redémarrages, budget de temps.

### Simulation et coordination

- `test_coordination.py` : acceptation explicite et revalidation, regroupement des événements et rejet des résultats périmés, propositions infaisables non exposées, mauvaise version rejetée, événements invalides ou en double, délais et annulation, isolation des données entre composants. Il utilise les adaptateurs synthétiques de `coordination_fixtures.py`.
- `test_historical_simulation.py` : lecture des horaires, exclusions et confidentialité des données sources, agents Mesa sans durée réalisée visible du planificateur, conservation des cas, remise en état et fermeture, replanification réactive après une panne de salle, validateur.
- `test_metaheuristics_mesa.py` : décodeur commun et objectif lexicographique comparés à la référence exacte (`room_instances.py`), budget d'évaluations et échéance, processus de recherche arrêtés proprement à l'échéance ou à l'annulation.

## Vérifications manuelles

- Pertinence clinique des prédictions et des poids de la fonction de coût : validation métier requise.
- Exécution complète des [notebooks](../notebooks/README.md) sur le classeur source (lente) : la faire une fois avec `jupyter nbconvert --execute`, puis vérifier les Parquet produits.
