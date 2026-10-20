# optimiseur

Métaheuristiques qui affectent un ensemble de patients à des vacations (créneaux de salle attribués à une spécialité). KYST les utilise pour **optimiser la cohorte** des demandes en attente et pour **actualiser les propositions** après un changement ; `hospital_sim` les réutilise pour planifier les salles dans la simulation Mesa.

| Module | Rôle |
| :--- | :--- |
| `optimizer.py` | Modèle du problème (`PlanningProblem`), fonction de coût, huit métaheuristiques, budget de temps, référence exacte par énumération |
| `multiagent.py` | Deux systèmes multi-agents Mesa : agents simples, et agents qui exécutent chacun une métaheuristique |
| `search_control.py` | Budget d'évaluations et échéance communs, pour comparer les méthodes à effort égal |

Dans l'API, `interface/api/ai/cohort.py` construit les tables d'entrée à partir de la base, puis revérifie après la recherche les règles que le modèle ne connaît pas (fenêtre de la demande, chirurgien, lits par unité, marge d'urgence) : une demande qui ne les respecte pas reste non placée.

## Les méthodes

`optimize_planning(patients, vacations, methodes=...)` lance une ou plusieurs méthodes (`TOUTES_METHODES`) :

| Méthode | Principe |
| :--- | :--- |
| Recuit simulé | Accepte une dégradation avec la probabilité `exp(delta/T)`, `T` décroissante |
| Tabou | Meilleur voisin non tabou, mémoire des derniers mouvements |
| Génétique | Population, sélection, croisement, mutation, élitisme |
| Tabou × Recuit | Voisinage filtré par la liste tabou, acceptation de type recuit |
| Fourmis (ACO) | Construction guidée par des phéromones, évaporation et dépôt |
| Génétique × Tabou | Recherche tabou sur le meilleur individu de chaque génération |
| Génétique × Recuit | Recuit court sur le meilleur individu de chaque génération |
| Fourmis × Tabou | Chaque itération ACO intensifie sa meilleure fourmi par recherche tabou |
| SMA | Agents simples (glouton, descente, aléatoire), tableau noir, migrations et redémarrages |
| SMA × Métaheuristiques | Agents recuit, tabou, génétique, fourmis et hybride qui coopèrent par tableau noir (méthode par défaut de l'actualisation dans KYST) |

Dans les systèmes multi-agents, le **tableau noir** garde la meilleure solution commune ; le **coordinateur** la diffuse aux agents sous la moyenne et relance les plus faibles quand la recherche stagne. Chaque agent a son propre générateur aléatoire : à graine égale, le résultat est identique.

## Données d'entrée

**Patients** : `patient_id`, `specialite`, `duree_operatoire` (minutes), `duree_sejour` (jours d'hospitalisation après l'intervention).

**Vacations** : `vacation_id`, `jour` (0, 1, 2…), `specialite`, `capacite_min` (240 = 4 h).

Un patient ne peut être placé que dans une vacation de sa spécialité.

## Fonction de coût

```text
coût = w_vacation × dépassement des vacations
     + w_lits     × dépassement des lits
     + w_balance  × écart-type de la charge entre vacations
```

Les poids par défaut sont 5, 3 et 0,05. La fitness vaut `-coût` : 0 correspond à un planning faisable et parfaitement équilibré. `exact_bruteforce()` calcule l'optimum exact par énumération sur la petite instance de validation (7 patients, 128 affectations) ; les tests vérifient que chaque méthode l'atteint.

## Limites

- La compatibilité est vérifiée par spécialité, pas par chirurgien : c'est l'adaptateur de l'API qui l'impose ensuite.
- Les lits sont agrégés (une capacité par jour), sans distinguer les unités.
- `time_budget_s` arrête une méthode à la fin de l'itération en cours : le dépassement est de l'ordre d'une itération.

Les tests sont dans [`tests/`](../tests/README.md) (`test_optimizer.py`, `test_hybrides.py`, `test_multiagent.py`).
