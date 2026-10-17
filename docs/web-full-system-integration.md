# Intégration du moteur complet dans KYST

Branche de travail : `codex/web-full-system`, créée depuis `origin/main`.
Les calculs historiques et les artefacts de modèles restent locaux ; aucune
donnée patient n'est ajoutée au dépôt ou à l'image de l'API.

Pour présenter les changements : [résumé pour l'équipe](web-integration-summary.md)
et [parcours utilisateurs illustrés avec des patients synthétiques](web-user-stories/README.md).

## État comparé

| Domaine | Application sur `main` | Dans le moteur de recherche/simulation | Intégration sur cette branche |
| --- | --- | --- | --- |
| Prédictions | Valeurs de démonstration par spécialité/type/âge | Modèles entraînés de durée de salle et de séjour, avec artefacts locaux | Adaptateurs `AI_BACKEND=trained` pour le parcours habituel de propositions A/B ; `fixtures` reste le défaut |
| Proposition A/B | Glouton par demande, avec contrôle de vacation et de lits | Métaheuristiques pour un **ensemble** de patients/vacations | Le choix individuel reste glouton ; un aperçu optimise jusqu'à 50 demandes avec les 10 méthodes et le cadre peut publier le résultat recalculé comme propositions à confirmer |
| Capacité | Vacations, lits conventionnels et places ambulatoires persistés ; contrôle lors de la confirmation | Objectif global de vacations/lits, mais modèle de lits agrégé | L'aperçu respecte fenêtre, chirurgien, marge d'urgence et lits par unité après la recherche ; les propositions rejetées par ce contrôle sont signalées non placées |
| SMA/Mesa | Aucun appel depuis le site | Coordinateur, fermetures, replanification, simulations salle minute par minute et lits sur plusieurs jours | Aperçu salle d'une journée et aperçu multi-jours salles/lits avec agents Mesa ; réservations existantes comptées, sans changement de réservation |
| Aléas | Annulation manuelle et marge d'urgence | Fermetures et adaptation dynamique dans les moteurs | Changements de demandes, refus, annulations et ressources persistés dans une file ; actualisation manuelle ou automatique des propositions. Fermeture 10 h–12 h dans Mesa |
| Données réelles | Cas cliniques saisis dans KYST ; résultats observés enregistrables | Classeur historique, Parquet et cohortes 2022 pour évaluation | Aucun chargement des données historiques dans l'API web ; les artefacts de modèles sont fournis séparément |

## Utilisation

Le gestionnaire du bloc voit les panneaux suivants sur la page **Planning** :

1. **Optimisation de la cohorte** : prévisualisation des
   demandes en attente sur une fenêtre de 60 jours au maximum. Les vacations
   déjà réservées, les lits occupés et les capacités disponibles sont lus en
   base. Le résultat affiche les affectations réalisables et les demandes
   non placées. **Publier des propositions** relance le calcul, revérifie
   demandes, vacations et lits, puis crée les propositions en une transaction.
   Chaque confirmation clinique verrouille les ressources sur PostgreSQL et
   vérifie à nouveau la faisabilité. La publication ne réserve pas de capacité.
2. **Simulation Mesa : salles** : simulation hypothétique d'une journée, avec
   salles identiques, 08 h–17 h et 15 minutes de remise en état. Les durées
   réalisées sont les prédictions multipliées par un facteur explicite de 1 à 2.
   La simulation ne connaît pas les résultats futurs réels ; son résultat est
   agrégé et ne montre aucun identifiant d'épisode. Elle ne simule ni les lits,
   ni les spécialités, ni les vacations dans cet aperçu.
3. **Simulation Mesa : salles et lits** : sur 14 jours et 30 demandes au plus,
   les agents en attente peuvent passer au jour suivant. Les vacations
   compatibles, les minutes déjà réservées et l'occupation des lits par unité
   limitent les offres. Le temps en salle et le séjour réalisés sont des
   facteurs hypothétiques cachés à la planification. Le résultat agrégé
   montre les interventions commencées, l'attente, le dépassement et les
   jours-unité de lits en conflit si un séjour réel excède la prévision.
   Les salles Mesa sont interchangeables : leurs ordres de passage ne
   représentent pas encore les salles et vacations exactes de KYST.
4. **Actualisation des propositions** : consulte la file des changements et les
   derniers calculs, puis permet de relancer une actualisation. Les changements
   et l'historique des calculs sont persistés en base. Un calcul réussi remplace
   les propositions de la cohorte, y compris en retirant les dates désormais
   impossibles ; un échec conserve les propositions précédentes. Les réservations
   confirmées restent des engagements fixes. Les refus de dates sont conservés
   jusqu'à la modification des données cliniques de la demande.

Si un changement de ressources compromet des réservations confirmées, le panneau
**Interventions confirmées à revoir** liste les demandes et les raisons. Le cadre
peut ainsi organiser leur révision sans déplacement automatique des patients.

L'actualisation utilise par défaut la méthode de vacations
`SMA x Metaheuristiques`. Ce moteur de propositions et les simulations Mesa
sont deux composants distincts : Mesa évalue des scénarios, tandis que la
file réagit à l'état enregistré par KYST.

Pour activer le traitement automatique, configurer :

```text
AUTO_REPLAN_ENABLED=true
REPLAN_METHOD="SMA x Metaheuristiques"
REPLAN_HORIZON_DAYS=14
REPLAN_BUDGET_SECONDS=1
REPLAN_MAX_CASES=200
```

L'API doit tourner avec **un seul processus worker**. Toutes les deux secondes,
le worker regroupe les changements non traités et relit la base. Les nouveaux
changements arrivés pendant un calcul restent en file pour le suivant. Après
un redémarrage, un calcul interrompu est signalé et remis en attente. Un échec
est conservé dans l'historique ; un changement ultérieur ou une relance manuelle
réessaie le calcul. Seul le type d'erreur est enregistré. Les nouvelles tables
`PlanningChange` et `ReplanRun` sont créées au démarrage sans modifier les
colonnes des tables existantes.

Par défaut, KYST reste en mode `fixtures`. Pour exécuter les modèles entraînés,
fournir les deux fichiers non versionnés et définir :

```text
AI_BACKEND=trained
ROOM_MODEL_PATH=/chemin/absolu/surgery_duration_model.joblib
LOS_MODEL_PATH=/chemin/absolu/los_regressor.joblib
```

Dans le conteneur, `KYST_MODEL_DIR` est monté en lecture seule sur `/srv/models`.
Ne placer aucun artefact ou jeu de données patient dans l'image Docker ni dans Git.
Un fichier manquant provoque une erreur explicite ; il n'est pas remplacé en
silence par les valeurs de démonstration.

## Sensibilité des modèles aux champs disponibles

L'évaluation reproductible lit uniquement les jeux prétraités et artefacts
locaux ; elle imprime des agrégats, jamais de lignes patient :

```bash
PYTHONPATH=interface:. venv/bin/python -m api.ai.validate_web_models \
  --room-data resources/model_surgery_duration_dataset.parquet \
  --los-data resources/model_los_dataset.parquet \
  --room-model /chemin/surgery_duration_model.joblib \
  --los-model /chemin/los_regressor.joblib \
  --output artifacts/web-model-validation.json
```

Sur les splits test 2022 locaux (3 043 cas salle, 3 059 séjours), la MAE
salle passe de **14,33 min** avec tous les champs du modèle à **17,90 min**
avec les champs disponibles dans KYST et le type d'intervention renseigné,
puis **22,62 min** si ce type manque aussi. La MAE séjour passe de
**0,45** à **0,65** puis **0,83 jour**. La couverture de la borne P95 de
durée de salle tombe de **94,1 %** à **60,2 %** avec les champs KYST.
Cette expérience masque les champs absents dans des données prétraitées ;
elle ne mesure pas une saisie prospective réelle ni la performance après
réentraînement. Les empreintes des fichiers sont dans la sortie locale.

## Limites à traiter avant un usage clinique

- Le formulaire de consultation fournit âge, sexe, diagnostic principal, CCAM
  et type d'intervention. Les artefacts existants ont aussi été entraînés avec
  anesthésie et noms de praticiens, absents du formulaire. L'adaptateur encode
  ces champs comme manquants. Le contrôle de sensibilité ci-dessus montre
  une dégradation nette. Il faut réentraîner sur les champs réellement
  disponibles à la consultation, calibrer de nouvelles bornes et conduire
  une validation prospective avant d'activer ce mode en pratique clinique.
- L'optimiseur de vacations a une fonction de coût souple et des lits agrégés.
  L'adaptateur web impose les fenêtres, chirurgiens, unités réelles et capacités
  après recherche ; il peut laisser des demandes non placées. Il faut intégrer
  ces contraintes à la recherche elle-même puis comparer les méthodes sur des
  cohortes représentatives avant de produire des propositions opérationnelles.
- La publication de cohorte crée des propositions, pas des réservations
  simultanées. Les confirmations cliniques restent individuelles. Les refus,
  capacités prises et modifications cliniques déclenchent une nouvelle
  actualisation ; l'acceptation vérifie toujours la faisabilité. Les verrous
  de confirmation s'appliquent à PostgreSQL ;
  SQLite est réservé à la démonstration locale.
- La simulation multi-jours utilise des durées hypothétiques, des salles
  interchangeables et une politique d'admission simple. Elle lit les
  réservations existantes, mais ne reproduit pas leur ordre de passage et
  ne pilote pas les réservations. La file traite les événements présents
  dans KYST, mais les urgences peropératoires, retards en salle et sorties
  tardives exigent encore des observations cliniques en direct et un
  calendrier de salles minute par minute. Une salle désactivée ou une capacité
  réduite peut remettre en cause un cas déjà confirmé ; le worker préserve ce
  cas, le signale dans le panneau de conflits et le cadre organise sa révision.

Les modèles restent séparés de l'optimiseur par les contrats de `api/ai/`.
Le plan initial est toujours calculé avec les prédictions ; les durées
réalisées restent dans l'exécution Mesa, hors des requêtes du solveur.

## Vérification

- API : `PYTHONPATH=interface venv/bin/python -m pytest interface/api/tests -q`.
  34 tests réussis. Les cas couvrent publication, confirmation, invalidation des dates après
  modification clinique, refus, retrait des propositions impossibles, échec
  conservant les propositions, reprise et traitement automatique de la file.
- Simulation : attente reportée jusqu'à libération d'un lit, réservation
  existante et conflit futur provoqué par un séjour hypothétique prolongé.
  La prévision des lits utilise la présence observée et la durée prédite ;
  elle ne connaît pas la sortie future des agents déjà admis.
- Recherche : 196 tests `unittest`, dont 7 sauts selon ressources locales.
- Frontend : contrôle Svelte et construction de production réussis.
- Image API : construction et inférence des deux artefacts locaux vérifiées.
- PostgreSQL : `interface/api/tests/check_postgres_concurrency.py` a validé
  deux confirmations simultanées pour le dernier lit : une acceptation, un
  rejet et une seule réservation. Ce contrôle autonome exige une base vide
  nommée `kyst_disposable_test` avec un marqueur explicite de test ; il ne
  supprime aucune table et n'utilise pas la base SQLite des tests API.
