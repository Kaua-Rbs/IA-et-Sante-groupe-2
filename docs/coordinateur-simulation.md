# Socle de coordination

Le coordinateur (`hospital_sim/coordinator.py`) est l'infrastructure asynchrone qui fait le lien entre les événements d'une journée, un planificateur et un validateur. Il est utilisé par la [simulation Mesa des salles](../hospital_sim/README.md), donc par les aperçus de simulation de KYST. Ce n'est pas un optimiseur multi-agents complet, et il n'est pas branché sur les réservations réelles de KYST : l'actualisation des propositions de l'application passe par une file persistante en base (voir [l'intégration](kyst-integration.md#actualisation-des-propositions)).

## Interfaces

Les interfaces sont définies dans `hospital_sim/contracts.py`. Des implémentations synthétiques, utilisées par les tests, sont dans `tests/coordination_fixtures.py`.

| Interface | Responsabilité | Implémentation dans la simulation |
| :--- | :--- | :--- |
| `StateAdapter` | Appliquer les événements et extraire les engagements fixes | `ObservationAdapter` (`scheduling.py`) |
| `Scheduler` | Proposer, de façon asynchrone, un planning lié à la version de l'état reçu | `BaselineScheduler`, `MetaheuristicScheduler` |
| `Validator` | Dire si un planning est faisable, avec ses raisons | `RoomValidator` |
| `LOSPredictor` | Prédire la durée de séjour totale, en jours calendaires inclusifs, avec bornes éventuelles | Aucune : les durées prédites arrivent déjà dans les cas. KYST a ses propres interfaces, de mêmes unités, dans `interface/api/ai/contracts.py` |
| `RoomDurationPredictor` | Prédire le temps de salle de l'entrée à la sortie, sans remise en état | Idem |

L'état, les plannings, les entrées de prédiction et les engagements fixes appartiennent aux adaptateurs : le coordinateur n'impose aucune représentation. Les objets qui traversent ces frontières doivent supporter `copy.deepcopy` ; les modèles, connexions et processus restent dans les adaptateurs, pas dans les instantanés de l'état.

Les prédicteurs sont synchrones et ne sont pas appelés par le coordinateur : c'est au planificateur de décider quand rafraîchir les prédictions et de vérifier leurs unités.

`SchedulingRequest` contient un instantané (avec le planning accepté), les engagements fixes et une échéance absolue en `time.monotonic()`. `Proposal.base_version` doit correspondre à la requête. Un planificateur renvoie `None` s'il ne trouve rien, ce qui ne prouve pas qu'aucune solution n'existe.

## Cycle de vie

Le coordinateur s'utilise dans une seule boucle d'événements asyncio. L'application des événements et la validation sont synchrones et doivent rester rapides.

1. `submit(event, replan=True)` applique un événement, incrémente la version de l'état, retire la proposition exposée et signale que le planning accepté est à revoir. `replan=False` enregistre une observation sans lancer de nouveau calcul ; une requête déjà en attente est conservée.
2. Un seul calcul tourne à la fois. Les événements suivants mettent l'état à jour immédiatement et sont regroupés en une requête unique sur le dernier état.
3. Les résultats périmés sont écartés avant validation ; une proposition portant une mauvaise version est rejetée.
4. Une proposition faisable et à jour est exposée dans `coordinator.proposal`, sans modifier le planning accepté.
5. `accept(expected_version)` vérifie la fraîcheur et revalide. En cas de succès, la proposition devient le planning accepté et la version est incrémentée. Cette étape explicite représente la validation humaine.

Les types d'événements sont : arrivée en urgence, annulation, dépassement d'intervention, sortie retardée et indisponibilité d'une ressource. Les identifiants d'événements sont uniques par coordinateur et les horodatages simulés sont finis, positifs et croissants (les égalités suivent l'ordre de soumission). Un événement en double est refusé ; un échec pendant son application laisse l'état inchangé.

## Échecs et mesures

- Résultats possibles : `stale`, `invalid_result`, `no_proposal`, `rejected`, `failed`, `timeout`, `proposal_ready`, `acceptance_stale`, `acceptance_rejected`, `accepted`.
- Garder un planning accepté après une perturbation ne garantit pas qu'il reste faisable : consulter `schedule_needs_review` et l'état de la proposition.
- Chaque résultat garde les versions, le temps de calcul et les raisons de validation. La latence événement → proposition part du dernier événement de la requête ; elle n'inclut pas le temps de décision humaine.
- `metrics` compte les événements appliqués, les résultats périmés, les dépassements de délai et les rejets. Tout reste en mémoire.
- Un échec n'est pas relancé indéfiniment : un nouvel état en attente déclenche sa requête, sinon l'appelant décide de la suite.
- Un résultat d'exception ne contient que le type de l'exception. Les raisons du validateur doivent être affichables et ne contenir aucun identifiant de patient ou de personnel.
- `wait_idle()` attend la fin du travail en cours. `close()`, ou la sortie d'un `async with`, annule le travail et refuse les nouveaux événements.

Les délais et l'arrêt reposent sur l'annulation coopérative d'asyncio. Les calculs lourds tournent hors de la boucle : `MetaheuristicScheduler` lance chaque recherche dans un processus séparé, arrêté à l'échéance. Le temps simulé et le temps de calcul sont distincts.
