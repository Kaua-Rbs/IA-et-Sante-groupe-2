# hospital_sim

Simulation Mesa d'une journée de bloc opératoire, minute par minute, avec replanification par un coordinateur. KYST l'utilise pour ses deux aperçus « et si… » de la page **Planning** : salles sur une journée (`interface/api/ai/room_simulation.py`) et salles et lits sur plusieurs jours (`interface/api/ai/ward_simulation.py`). Ces aperçus ne réservent rien.

## Principe

Chaque intervention est un agent Mesa qui attend, passe en salle, puis se termine. Le planificateur ne voit que les **durées prédites** ; les **durées réalisées** (dans KYST, la prédiction multipliée par un facteur choisi par le cadre) restent dans la simulation et ne se découvrent qu'au fil de l'exécution. Quand un événement survient, par exemple la fermeture d'une salle, la politique **réactive** demande un nouveau plan au coordinateur ; la politique **figée** garde le plan initial.

Une solution affecte chaque intervention en attente à une salle. Le décodeur commun place les cas de chaque salle par durée prédite croissante, en respectant les disponibilités, la remise en état entre deux patients et les fermetures connues. Les interventions en cours ou terminées ne bougent pas. L'objectif est lexicographique : d'abord le moins d'interventions non commencées, puis le moins de dépassement horaire, puis le moins de décisions modifiées.

## Modules

| Module | Rôle |
| :--- | :--- |
| `domain.py` | Données visibles du planificateur : cas, salles, état, planning, configuration de la journée. Jamais de durée réalisée |
| `contracts.py` | Interfaces entre le coordinateur et ses adaptateurs (état, planificateur, validateur, prédicteurs) |
| `coordinator.py` | Coordinateur asynchrone : versions de l'état, rejet des résultats obsolètes, validation, acceptation explicite. Voir [le socle de coordination](../docs/coordination-core.md) |
| `simulation.py` | Exécution Mesa minute par minute (`run_day`) ; le temps simulé s'arrête pendant la planification |
| `scheduling.py` | Planificateur de référence (glouton) et validateur des plannings de salles |
| `room_problem.py` | Décodeur commun et objectif lexicographique, au format attendu par les métaheuristiques de `optimiseur` |
| `metaheuristics.py` | Neuf planificateurs (`baseline`, recuit, tabou, génétique, hybride, fourmis et trois hybrides), chacun dans un processus séparé que l'on peut arrêter à l'échéance |
| `historical_data.py` | Scénario d'une journée (`DailyScenario`) et lecture du classeur nettoyé |

## Limites

Les salles sont interchangeables : les ordres de passage ne représentent pas encore les salles et vacations exactes de KYST. La simulation ne modélise ni les équipes, ni la SSPI, ni les urgences peropératoires. Les durées réalisées sont hypothétiques : elles ne mesurent pas la performance réelle du bloc.

Les tests sont dans [`tests/`](../tests/README.md) (`test_coordination.py`, `test_historical_simulation.py`, `test_metaheuristics_mesa.py`).
